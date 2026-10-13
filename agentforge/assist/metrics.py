"""Prepare comparisons and collect existing logs; never launch Codex or any model."""

import math
import statistics
from pathlib import Path
from uuid import uuid4

from .storage import (
    AssistError,
    digest,
    encoded,
    private_dir,
    read_bytes,
    secret_present,
    write_private,
)

FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")
SETTINGS = ("agent_version", "model", "reasoning", "sandbox", "approval_policy", "network", "tools")


def prepare_benchmark(tasks, settings, directory: Path, replicates=1):
    if not tasks or len(tasks) > 100 or replicates < 1 or replicates > 5:
        raise AssistError("Use 1-100 tasks and 1-5 repetitions")
    if any(key not in settings for key in SETTINGS):
        raise AssistError(
            "Record agent version, model, reasoning, sandbox, approvals, network and tools"
        )
    if any(key not in (*SETTINGS, "memory_seed", "usage_semantics") for key in settings):
        raise AssistError(
            "Unknown benchmark setting; credentials and auth configuration are not accepted"
        )
    if secret_present(encoded(settings).decode()):
        raise AssistError("Credential-like benchmark settings refused")
    private_dir(directory)
    experiment = uuid4().hex
    configuration_hash = digest(encoded(settings))
    runs = []
    ids = set()
    for task in tasks:
        if set(task) != {"id", "prompt_file", "base_commit", "acceptance_criteria"}:
            raise AssistError(
                "Each benchmark task needs id, prompt_file, base_commit, acceptance_criteria"
            )
        if not isinstance(task["id"], str) or not task["id"].isidentifier() or task["id"] in ids:
            raise AssistError("Benchmark task IDs must be unique identifiers")
        ids.add(task["id"])
        if (
            not task["base_commit"]
            or not isinstance(task["acceptance_criteria"], list)
            or not task["acceptance_criteria"]
        ):
            raise AssistError("Base revision and frozen acceptance criteria are required")
        data = read_bytes(Path(task["prompt_file"]))
        if secret_present(data.decode("utf-8")):
            raise AssistError(
                "Credential-like benchmark prompt refused; replace secrets with private references"
            )
        snapshot = directory / (task["id"] + ".prompt.txt")
        write_private(snapshot, data, immutable=True)
        for replicate in range(1, replicates + 1):
            for arm in ("A", "B", "C"):
                run_id = f"{task['id']}-{replicate}-{arm}"
                manifest = {
                    "schema_version": 1,
                    "experiment": experiment,
                    "run_id": run_id,
                    "task_id": task["id"],
                    "replicate": replicate,
                    "arm": arm,
                    "base_commit": task["base_commit"],
                    "prompt_hash": digest(data),
                    "prompt_file": str(snapshot.resolve()),
                    "acceptance_criteria": task["acceptance_criteria"],
                    "settings": settings,
                    "settings_hash": configuration_hash,
                    "treatment": {"helpers": arm != "A", "decomposition": arm == "C"},
                    "status": "prepared_not_run",
                    "agent_runs_launched": 0,
                }
                write_private(
                    directory / (run_id + ".manifest.json"), encoded(manifest), immutable=True
                )
                runs.append(run_id)
    return {
        "status": "ok",
        "experiment": experiment,
        "manifests": len(runs),
        "run_ids": runs,
        "directory": str(directory),
        "agent_runs_launched": 0,
        "notice": "Coding runs need authorization; isolate states and counterbalance order",
    }


def collect_usage(paths, semantics="unknown"):
    if semantics not in ("unknown", "per_turn", "cumulative"):
        raise AssistError("Usage semantics must be unknown, per_turn or cumulative")
    totals = {field: 0 for field in FIELDS}
    available = {field: 0 for field in FIELDS}
    complete_events = starts = failures = invalid = threads = 0
    seen_files, seen_events = set(), set()
    duplicate_files = 0
    source_hashes = []
    item_counts: dict[str, int] = {}
    seen_items = set()
    failed_commands = 0
    for path in paths:
        data = read_bytes(Path(path), 33554432)
        checksum = digest(data)
        if checksum in seen_files:
            duplicate_files += 1
            continue
        seen_files.add(checksum)
        source_hashes.append(checksum)
        thread = checksum
        for ordinal, line in enumerate(data.splitlines()):
            try:
                import json

                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError()
            except (ValueError, UnicodeError):
                invalid += 1
                continue
            kind = event.get("type")
            if kind == "thread.started":
                threads += 1
                thread = event.get("thread_id", checksum)
            if kind == "turn.started":
                starts += 1
            if kind in ("turn.failed", "error"):
                failures += 1
            if kind == "item.completed" and isinstance(event.get("item"), dict):
                item = event["item"]
                item_id = (thread, item.get("id")) if item.get("id") else (checksum, ordinal)
                if item_id not in seen_items:
                    seen_items.add(item_id)
                    item_type = item.get("type")
                    if item_type in (
                        "command_execution",
                        "file_change",
                        "mcp_tool_call",
                        "web_search",
                        "agent_message",
                        "reasoning",
                        "plan_update",
                    ):
                        item_counts[item_type] = item_counts.get(item_type, 0) + 1
                    if item_type == "command_execution" and (
                        item.get("status") == "failed"
                        or type(item.get("exit_code")) is int
                        and item["exit_code"] != 0
                    ):
                        failed_commands += 1
            if kind != "turn.completed":
                continue
            identity = (
                (thread, event.get("turn_id")) if event.get("turn_id") else (checksum, ordinal)
            )
            if identity in seen_events:
                continue
            seen_events.add(identity)
            complete_events += 1
            usage = event.get("usage", {})
            if not isinstance(usage, dict):
                invalid += 1
                continue
            for subset, total in (
                ("cached_input_tokens", "input_tokens"),
                ("reasoning_output_tokens", "output_tokens"),
            ):
                if type(usage.get(subset)) is int and type(usage.get(total)) is int:
                    if usage[subset] > usage[total]:
                        invalid += 1
            for field in FIELDS:
                value = usage.get(field)
                if type(value) is int and value >= 0:
                    totals[field] += value
                    available[field] += 1
    full = (
        complete_events > 0
        and invalid == 0
        and failures == 0
        and starts == complete_events
        and threads > 0
    )
    coverage = {
        field: "complete"
        if full and available[field] == complete_events
        else "partial"
        if available[field]
        else "unavailable"
        for field in FIELDS
    }
    derived = None
    if semantics == "per_turn" and all(
        coverage[k] == "complete" for k in ("input_tokens", "output_tokens")
    ):
        derived = totals["input_tokens"] + totals["output_tokens"]
    return {
        "source": "client_reported_events",
        "usage_semantics": semantics,
        "source_hashes": source_hashes,
        "completed_turn_events": complete_events,
        "turn_starts": starts,
        "failure_events": failures,
        "invalid_lines": invalid,
        "duplicate_files_skipped": duplicate_files,
        "coverage": coverage,
        "reported_field_sums": {k: totals[k] if available[k] else None for k in FIELDS},
        "input_plus_output_tokens": derived,
        "quota_usage": None,
        "dollar_cost": None,
        "activity": {
            "completed_items": item_counts,
            "tool_calls_observed": sum(
                item_counts.get(kind, 0)
                for kind in ("command_execution", "file_change", "mcp_tool_call", "web_search")
            ),
            "failed_command_executions_observed": failed_commands,
            "repair_attempts": None,
            "notice": "Items are observable tools, not internal model turns or inferred repairs",
        },
        "notice": "Cache/reasoning not added again; incomplete/unknown data has no derived total",
    }


def collect_helpers(path):
    import json

    totals = {key: 0.0 for key in ("output_bytes", "files_read", "bytes_read", "elapsed_ms")}
    events, invalid, truncated = 0, 0, False
    seen = set()
    for line in read_bytes(path, 4194304).splitlines():
        try:
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError()
            if event.get("operation") == "history_truncated":
                truncated = True
                continue
            if event.get("id") in seen:
                continue
            if not event.get("id"):
                raise ValueError()
            seen.add(event["id"])
            values = {key: event[key] for key in totals}
            for value in values.values():
                if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                    raise ValueError()
            for key, value in values.items():
                totals[key] += value
            events += 1
        except (ValueError, TypeError, KeyError):
            invalid += 1
    return {
        "calls_observed": events,
        **totals,
        "coverage": "partial" if invalid or truncated else "complete",
        "invalid_events": invalid,
        "history_truncated": truncated,
        "notice": "Helper bytes are measured local output, not Codex token usage",
    }


def collect_run(manifest, paths, outcome, helper_log=None):
    required = {
        "final_status",
        "mandatory_passed",
        "mandatory_total",
        "regressions",
        "failed_checks",
        "repair_rounds",
        "reopened_tasks",
        "integration_fixes",
        "operator_interventions",
        "elapsed_seconds",
    }
    if set(outcome) != required or outcome["final_status"] not in ("accepted", "failed", "blocked"):
        raise AssistError("Outcome needs the complete frozen correctness/rework schema")
    optional = {"repair_rounds", "reopened_tasks", "integration_fixes", "operator_interventions"}
    for key in required - {"final_status"}:
        value = outcome[key]
        if value is None and key in optional:
            continue
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or value < 0
            or key != "elapsed_seconds"
            and type(value) is not int
        ):
            raise AssistError("Outcome counts must be nonnegative integers; durations finite")
    if outcome["mandatory_passed"] > outcome["mandatory_total"]:
        raise AssistError("Requirement counts are inconsistent")
    if outcome["final_status"] == "accepted" and (
        outcome["mandatory_passed"] != outcome["mandatory_total"] or outcome["regressions"]
    ):
        raise AssistError("Accepted outcome contradicts mandatory correctness/regressions")
    return {
        "schema_version": 1,
        "manifest": manifest,
        "usage": collect_usage(
            paths, manifest.get("settings", {}).get("usage_semantics", "unknown")
        ),
        "helpers": collect_helpers(helper_log) if helper_log else {"coverage": "unavailable"},
        "outcome": outcome,
        "outcome_source": "operator_supplied; not a model grader",
    }


def compare(runs):
    groups: dict[tuple, dict] = {}
    for run in runs:
        manifest = run["manifest"]
        if manifest["settings_hash"] != digest(encoded(manifest["settings"])):
            raise AssistError("Manifest settings hash does not match its actual settings")
        key = (manifest["experiment"], manifest["task_id"], manifest["replicate"])
        group = groups.setdefault(key, {})
        if manifest["arm"] in group:
            raise AssistError("Duplicate arm in a paired trial")
        group[manifest["arm"]] = run
    pairs: list[dict] = []
    deltas: dict[str, list] = {"B-A": [], "C-B": [], "C-A": []}
    for key, arms in groups.items():
        reference = next(iter(arms.values()))["manifest"]
        for run in arms.values():
            manifest = run["manifest"]
            if any(
                manifest[k] != reference[k]
                for k in ("settings_hash", "base_commit", "prompt_hash", "acceptance_criteria")
            ):
                raise AssistError(
                    "Paired trials have different prompts/settings/revisions/acceptance"
                )
        row = {
            "task": key[1],
            "replicate": key[2],
            "outcomes": {arm: run["outcome"] for arm, run in arms.items()},
            "token_differences": {},
            "saving_percent": {},
            "correctness_comparable": {},
        }
        for treatment, baseline in (("B", "A"), ("C", "B"), ("C", "A")):
            label = treatment + "-" + baseline
            t = arms.get(treatment, {}).get("usage", {}).get("input_plus_output_tokens")
            b = arms.get(baseline, {}).get("usage", {}).get("input_plus_output_tokens")
            delta = t - b if t is not None and b is not None else None
            row["token_differences"][label] = delta
            row["saving_percent"][label] = (
                (b - t) / b * 100 if (t is not None and b is not None and b > 0) else None
            )
            row["correctness_comparable"][label] = all(
                arm in arms
                and arms[arm]["outcome"]["final_status"] == "accepted"
                and arms[arm]["outcome"]["mandatory_total"] > 0
                and arms[arm]["outcome"]["mandatory_passed"]
                == arms[arm]["outcome"]["mandatory_total"]
                and arms[arm]["outcome"]["regressions"] == 0
                for arm in (treatment, baseline)
            )
            if delta is not None:
                deltas[label].append(delta)
        pairs.append(row)
    return {
        "status": "ok",
        "paired_trials": pairs,
        "median_observed_token_differences": {
            key: statistics.median(values) if values else None for key, values in deltas.items()
        },
        "notice": "Include failures and judge correctness/rework. No quota or savings guarantee.",
        "benchmark_runs_launched": 0,
    }
