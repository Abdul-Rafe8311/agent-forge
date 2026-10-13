"""Explicit repository checks with scoped evidence and bounded private diagnostics."""

import os
import signal
import subprocess
import threading
import time
from copy import deepcopy
from uuid import uuid4

from ..types import CodeArtifact
from ..validator import PythonSyntaxValidator
from .contracts import Check
from .storage import (
    AssistError,
    digest,
    encoded,
    fingerprint,
    read_bytes,
    redact,
    safe_path,
    secret_present,
    write_private,
)


def evidence_current(session, state, evidence):
    checks = {c["id"]: c for c in state["checks"]}
    return (
        evidence["spec_hash"] == state["spec_hash"]
        and evidence["plan_version"] == state["plan_version"]
        and evidence["check_id"] in checks
        and evidence["check_hash"] == digest(encoded(checks[evidence["check_id"]]))
        and evidence["file_hashes"] == fingerprint(session.root, evidence["file_hashes"])
    )


def render_feedback(result, limit=4096):
    """Return focused feedback; the complete scoped hashes stay in private evidence."""
    value = deepcopy(result)
    hashes = value.pop("file_hashes", {})
    value["scope_file_count"] = len(hashes)
    value["scope_files"] = list(hashes)
    value["full_evidence_id"] = value.get("id")
    value["omitted_scope_files"] = value["omitted_issues"] = 0
    while len(encoded(value)) + 100 > limit:
        value["truncated"] = True
        if len(value.get("diagnostics", "")) > 80:
            value["diagnostics"] = value["diagnostics"][: len(value["diagnostics"]) // 2]
        elif len(value.get("note", "")) > 80:
            value["note"] = value["note"][: len(value["note"]) // 2]
        elif len(value.get("issues", [])) > 1:
            value["issues"].pop()
            value["omitted_issues"] += 1
        elif value["scope_files"]:
            value["scope_files"].pop()
            value["omitted_scope_files"] += 1
        else:
            break
    return value


def register_checks(state, values, *, approve_commands=False):
    checks = [Check(**v) for v in values]
    if len({c.id for c in checks}) != len(checks):
        raise AssistError("Check IDs must be unique")
    for check in checks:
        if any(secret_present(argument) for argument in check.argv):
            raise AssistError("Credential-like check arguments are forbidden")
        if check.kind == "command" and (not check.argv or not check.files):
            raise AssistError("Command checks need argv and an explicit source-file scope")
        if check.kind != "command" and check.argv:
            raise AssistError("Only command checks may contain argv")
    if any(c.kind == "command" for c in checks) and not approve_commands:
        raise AssistError("Command catalog needs explicit --approve-commands")
    state["checks"] = [c.model_dump() for c in checks]
    state["commands_approved"] = approve_commands
    state["evidence"], state["completions"], state["original_review"] = {}, {}, None
    state["plan_version"] += 1


def run_command(session, check):
    if any(
        secret_flag in argument.lower()
        for argument in check.argv
        for secret_flag in ("--api-key", "--password", "--token", "--authorization")
    ):
        raise AssistError("Credential-bearing check arguments are forbidden")
    env = {
        key: os.environ[key]
        for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
        if key in os.environ
    }
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    buffers = [bytearray(), bytearray()]
    counts = [0, 0]
    try:
        process = subprocess.Popen(
            check.argv,
            cwd=session.root,
            env=env,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            if os.name == "nt"
            else 0,
            start_new_session=os.name != "nt",
        )
    except OSError:
        return {
            "status": "failed",
            "issues": [{"kind": "command", "message": "Check could not start"}],
        }

    def drain(stream, index):
        try:
            while chunk := stream.read(4096):
                counts[index] += len(chunk)
                buffers[index].extend(chunk[: max(0, 8192 - len(buffers[index]))])
        finally:
            stream.close()

    threads = [
        threading.Thread(target=drain, args=(stream, i), daemon=True)
        for i, stream in enumerate((process.stdout, process.stderr))
    ]
    for thread in threads:
        thread.start()
    timed_out = False
    try:
        process.wait(timeout=check.timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
    # Clean up the owned process group, including descendants holding output pipes.
    if os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif timed_out:
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False
        )
    if timed_out:
        process.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=1)
    text = redact((bytes(buffers[0]) + b"\n" + bytes(buffers[1])).decode(errors="replace"))
    log_id = uuid4().hex
    log_bytes = text.encode()
    write_private(
        session.path / "logs" / (log_id + ".txt"),
        log_bytes[:16384].decode("utf-8", errors="ignore").encode(),
    )
    capture_complete = not any(thread.is_alive() for thread in threads)
    lines = list(dict.fromkeys(line for line in text.splitlines() if line.strip()))
    issues = (
        []
        if process.returncode == 0 and not timed_out
        else [
            {
                "kind": "timeout" if timed_out else "command",
                "message": "Check timed out" if timed_out else f"Check exit {process.returncode}",
            }
        ]
    )
    return {
        "status": "passed" if not issues else "failed",
        "issues": issues,
        "exit_code": process.returncode,
        "log_id": log_id,
        "diagnostics": "\n".join(lines)[:2000],
        "truncated": any(n > 8192 for n in counts)
        or len("\n".join(lines)) > 2000
        or len(log_bytes) > 16384
        or not capture_complete,
        "output_capture_complete": capture_complete,
        "output_bytes_observed": sum(counts),
        "timeout": timed_out,
    }


def validate(
    session, state, task, check_id, *, execute=False, files=None, manual_status=None, note=""
):
    checks = {c["id"]: Check(**c) for c in state["checks"]}
    if check_id not in checks:
        raise AssistError("Unknown check ID")
    check = checks[check_id]
    selected = files or check.files or [f.path for f in task.relevant_files]
    hashes = fingerprint(session.root, selected)
    started = time.monotonic()
    if check.kind == "command":
        if not execute or not state["commands_approved"]:
            return {
                "status": "not_run",
                "check_id": check_id,
                "message": "Use --execute for an approved check",
                "argv": [redact(a) for a in check.argv],
                "data_only": True,
            }
        if files and set(files) != set(check.files):
            raise AssistError("Command scope is fixed by the approved catalog")
        result = run_command(session, check)
    elif check.kind == "manual":
        if manual_status not in ("passed", "failed") or not note.strip():
            return {
                "status": "manual_review",
                "check_id": check_id,
                "message": "Explicit status and note required",
            }
        result = {
            "status": manual_status,
            "issues": [],
            "note": redact(note)[:1000],
            "source": "agent_or_operator_attested",
            "not_automatically_verified": True,
        }
    else:
        artifacts = []
        for path in selected:
            data = read_bytes(safe_path(session.root, path), 262144)
            artifacts.append(CodeArtifact(path, data.decode("utf-8")))
        result = PythonSyntaxValidator().validate(artifacts)
        result = {
            "status": ("passed" if result.passed else "failed") if artifacts else "not_run",
            "issues": [vars(issue) for issue in result.issues[:10]],
            "truncated": len(result.issues) > 10,
            "diagnostics": redact(result.diagnostics),
            "scope": "syntax/structure only; not behavioral correctness",
        }
    result = {
        **result,
        "id": uuid4().hex,
        "task_id": task.id,
        "check_id": check_id,
        "spec_hash": state["spec_hash"],
        "plan_version": state["plan_version"],
        "check_hash": digest(encoded(check.model_dump())),
        "file_hashes": hashes,
        "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
    }
    # Changes during a check invalidate its evidence even if the command exited successfully.
    if hashes != fingerprint(session.root, selected):
        result["status"] = "stale"
    state["evidence"][task.id + ":" + check_id] = result
    state["original_review"] = None
    return result
