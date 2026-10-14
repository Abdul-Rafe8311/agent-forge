import json
from copy import deepcopy
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from agentforge.assist.metrics import (
    collect_helpers,
    collect_run,
    collect_usage,
    compare,
    prepare_benchmark,
)
from agentforge.assist.storage import AssistError, digest, encoded, read_json
from agentforge.cli import app

SETTINGS = {
    "agent_version": "fixture-version",
    "model": "fixture-model",
    "reasoning": "medium",
    "sandbox": "workspace",
    "approval_policy": "on-request",
    "network": "offline",
    "tools": ["terminal"],
    "usage_semantics": "per_turn",
}
OUTCOME = {
    "final_status": "accepted",
    "mandatory_passed": 2,
    "mandatory_total": 2,
    "regressions": 0,
    "failed_checks": 0,
    "repair_rounds": 0,
    "reopened_tasks": 0,
    "integration_fixes": 0,
    "operator_interventions": 0,
    "elapsed_seconds": 10,
}


def log(path, inputs=100, outputs=20, cache=50, reasoning=5):
    events = [
        {"type": "thread.started", "thread_id": "fixture"},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"text": "PRIVATE_TRANSCRIPT_NOT_FOR_OUTPUT"}},
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": inputs,
                "output_tokens": outputs,
                "cached_input_tokens": cache,
                "reasoning_output_tokens": reasoning,
            },
        },
    ]
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return path


def manifests(tmp_path):
    prompt = tmp_path / "task.md"
    prompt.write_text("Implement original requirements.")
    directory = tmp_path / "benchmark"
    result = prepare_benchmark(
        [
            {
                "id": "task",
                "prompt_file": str(prompt),
                "base_commit": "fixture-commit",
                "acceptance_criteria": ["behavior", "compatibility"],
            }
        ],
        SETTINGS,
        directory,
    )
    return directory, result


def test_three_arms_prepared_no_agent_or_model_calls(tmp_path, monkeypatch):
    monkeypatch.setattr("subprocess.Popen", Mock(side_effect=AssertionError("No coding runs")))
    directory, result = manifests(tmp_path)
    assert result["manifests"] == 3 and result["agent_runs_launched"] == 0
    arms = [read_json(directory / f"task-1-{arm}.manifest.json") for arm in "ABC"]
    assert len({a["prompt_hash"] for a in arms}) == len({a["settings_hash"] for a in arms}) == 1
    assert [a["treatment"] for a in arms] == [
        {"helpers": False, "decomposition": False},
        {"helpers": True, "decomposition": False},
        {"helpers": True, "decomposition": True},
    ]


def test_context_comparison_prepares_only_matched_a_b_without_launch(tmp_path, monkeypatch):
    monkeypatch.setattr("subprocess.Popen", Mock(side_effect=AssertionError("No coding runs")))
    prompt = tmp_path / "task.md"
    original = b"Original requirements.\r\nAcceptance checks remain authoritative.\r\n"
    prompt.write_bytes(original)
    tasks = [
        {
            "id": "task",
            "prompt_file": str(prompt),
            "base_commit": "fixed",
            "acceptance_criteria": ["Frozen evaluator passes"],
        }
    ]
    directory = tmp_path / "matched"
    result = prepare_benchmark(tasks, SETTINGS, directory, workflow="context")
    assert result["manifests"] == 2 and result["agent_runs_launched"] == 0
    arms = [read_json(directory / f"task-1-{a}.manifest.json") for a in "AB"]
    assert (directory / "task.prompt.txt").read_bytes() == original
    assert all(a["status"] == "prepared_not_run" for a in arms)
    for key in ("base_commit", "prompt_hash", "settings_hash", "acceptance_criteria"):
        assert arms[0][key] == arms[1][key]
    assert [a["treatment"]["workflow"] for a in arms] == ["ordinary", "context"]
    assert all(not a["treatment"]["decomposition"] for a in arms)
    assert not (directory / "task-1-C.manifest.json").exists()
    tasks_file, settings_file = tmp_path / "tasks.json", tmp_path / "settings.json"
    tasks_file.write_text(json.dumps(tasks))
    settings_file.write_text(json.dumps(SETTINGS))
    cli = CliRunner().invoke(
        app,
        [
            "assist",
            "benchmark",
            "prepare",
            "--workflow",
            "context",
            "--tasks-file",
            str(tasks_file),
            "--settings-file",
            str(settings_file),
            "--output-dir",
            str(tmp_path / "cli-matched"),
        ],
    )
    assert cli.exit_code == 0, cli.output
    assert json.loads(cli.stdout)["manifests"] == 2
    with pytest.raises(AssistError):
        prepare_benchmark(tasks, SETTINGS, tmp_path / "invalid", workflow="unknown")


def test_reported_usage_not_double_counted_and_private_text_not_returned(tmp_path):
    file = log(tmp_path / "run.jsonl")
    value = collect_usage([file, file], "per_turn")
    assert value["input_plus_output_tokens"] == 120
    assert value["reported_field_sums"]["cached_input_tokens"] == 50
    assert value["duplicate_files_skipped"] == 1
    assert value["quota_usage"] is None and value["dollar_cost"] is None
    assert "PRIVATE_TRANSCRIPT" not in str(value)
    assert collect_usage([file])["input_plus_output_tokens"] is None
    assert collect_usage([file], "cumulative")["input_plus_output_tokens"] is None


def test_failed_launch_with_empty_log_has_unavailable_tokens(tmp_path):
    directory, _ = manifests(tmp_path)
    empty = tmp_path / "failed-launch.jsonl"
    empty.write_bytes(b"")
    usage = collect_usage([empty], "per_turn")
    assert usage["turn_starts"] == usage["completed_turn_events"] == 0
    assert all(value is None for value in usage["reported_field_sums"].values())
    assert all(value == "unavailable" for value in usage["coverage"].values())
    assert usage["input_plus_output_tokens"] is None
    assert usage["activity"]["tool_calls_observed"] == 0
    failed = {**OUTCOME, "final_status": "blocked", "mandatory_passed": 0}
    runs = [
        collect_run(read_json(directory / f"task-1-{arm}.manifest.json"), [empty], failed)
        for arm in "AB"
    ]
    paired = compare(runs)["paired_trials"][0]
    assert paired["saving_percent"]["B-A"] is None
    assert paired["token_differences"]["B-A"] is None
    assert not paired["correctness_comparable"]["B-A"]


def test_observed_tools_and_failed_commands_are_not_inferred_repairs(tmp_path):
    file = log(tmp_path / "tools.jsonl")
    with file.open("a") as stream:
        event = {
            "type": "item.completed",
            "item": {"id": "cmd", "type": "command_execution", "exit_code": 1},
        }
        stream.write(json.dumps(event) + "\n" + json.dumps(event) + "\n")
    activity = collect_usage([file], "per_turn")["activity"]
    assert activity["tool_calls_observed"] == 1
    assert activity["failed_command_executions_observed"] == 1
    assert activity["repair_attempts"] is None


def test_unavailable_rework_is_not_fabricated_zero_and_nonfinite_refused(tmp_path):
    directory, _ = manifests(tmp_path)
    manifest = read_json(directory / "task-1-A.manifest.json")
    outcome = {**OUTCOME, "repair_rounds": None, "integration_fixes": None}
    assert collect_run(manifest, [], outcome)["outcome"]["repair_rounds"] is None
    with pytest.raises(Exception, match="finite"):
        collect_run(manifest, [], {**outcome, "elapsed_seconds": float("nan")})


def test_impossible_subset_counts_and_malformed_helper_events_are_partial(tmp_path):
    file = log(tmp_path / "bad-counts.jsonl", inputs=10, cache=11)
    assert collect_usage([file], "per_turn")["input_plus_output_tokens"] is None
    helper = tmp_path / "helpers.jsonl"
    helper.write_text("[]\n")
    result = collect_helpers(helper)
    assert result["coverage"] == "partial" and result["invalid_events"] == 1


@pytest.mark.parametrize(
    "events",
    [
        [],
        [{"type": "turn.completed", "usage": {"input_tokens": 10}}],
        [{"type": "turn.started"}, {"type": "turn.failed"}],
        [{"type": "thread.started"}, {"type": "turn.started"}],
    ],
)
def test_partial_or_unavailable_usage_not_zero(tmp_path, events):
    path = tmp_path / "incomplete.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events))
    result = collect_usage([path], "per_turn")
    assert result["input_plus_output_tokens"] is None
    assert result["coverage"]["output_tokens"] == "unavailable"


def test_failed_runs_included_and_mismatched_settings_refused(tmp_path):
    directory, _ = manifests(tmp_path)
    results = []
    for arm, inputs in zip("ABC", [100, 90, 110]):
        outcome = dict(OUTCOME)
        if arm == "C":
            outcome.update(final_status="failed", mandatory_passed=1, repair_rounds=2)
        result = collect_run(
            read_json(directory / f"task-1-{arm}.manifest.json"),
            [log(tmp_path / f"{arm}.jsonl", inputs=inputs)],
            outcome,
        )
        results.append(result)
    compared = compare(results)
    assert compared["median_observed_token_differences"] == {"B-A": -10, "C-B": 20, "C-A": 10}
    assert compared["paired_trials"][0]["saving_percent"]["C-A"] < 0
    assert not compared["paired_trials"][0]["correctness_comparable"]["C-A"]
    assert compared["paired_trials"][0]["outcomes"]["C"]["final_status"] == "failed"
    assert compared["benchmark_runs_launched"] == 0
    altered = deepcopy(results)
    altered[1]["manifest"]["settings"]["model"] = "different"
    with pytest.raises(AssistError, match="settings hash"):
        compare(altered)
    altered[1]["manifest"]["settings_hash"] = digest(encoded(altered[1]["manifest"]["settings"]))
    with pytest.raises(AssistError, match="different"):
        compare(altered)


def test_helper_counters_and_truncation_unknown(tmp_path):
    path = tmp_path / "helper.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "event",
                "output_bytes": 100,
                "files_read": 2,
                "bytes_read": 50,
                "elapsed_ms": 10,
            }
        )
        + "\n"
        + json.dumps({"operation": "history_truncated"})
    )
    result = collect_helpers(path)
    assert result["output_bytes"] == 100 and result["coverage"] == "partial"
    assert result["history_truncated"]


def test_inconsistent_correctness_and_credentials_refused(tmp_path):
    directory, _ = manifests(tmp_path)
    manifest = read_json(directory / "task-1-A.manifest.json")
    with pytest.raises(AssistError, match="contradicts"):
        collect_run(manifest, [], {**OUTCOME, "mandatory_passed": 1})
    with pytest.raises(AssistError, match="Unknown benchmark"):
        prepare_benchmark([{}], {**SETTINGS, "api_key": "PRIVATE"}, tmp_path / "extra")


def test_benchmark_cli_prepare_collect_compare_without_coding_runs(tmp_path):
    runner = CliRunner()
    prompt = tmp_path / "task.md"
    prompt.write_text("Implement task.")
    tasks = tmp_path / "tasks.json"
    tasks.write_text(
        json.dumps(
            [
                {
                    "id": "task",
                    "prompt_file": str(prompt),
                    "base_commit": "fixture",
                    "acceptance_criteria": ["behavior"],
                }
            ]
        )
    )
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps(SETTINGS))
    outcome = tmp_path / "outcome.json"
    outcome.write_text(json.dumps(OUTCOME))
    folder = tmp_path / "benchmark"
    result = runner.invoke(
        app,
        [
            "assist",
            "benchmark",
            "prepare",
            "--tasks-file",
            str(tasks),
            "--settings-file",
            str(settings),
            "--output-dir",
            str(folder),
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["agent_runs_launched"] == 0
    output = tmp_path / "result.json"
    usage = log(tmp_path / "usage.jsonl")
    result = runner.invoke(
        app,
        [
            "assist",
            "benchmark",
            "collect",
            "--manifest-file",
            str(folder / "task-1-A.manifest.json"),
            "--outcome-file",
            str(outcome),
            "--output-file",
            str(output),
            "--log",
            str(usage),
        ],
    )
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["assist", "benchmark", "compare", "--result", str(output)])
    assert result.exit_code == 0, result.output
