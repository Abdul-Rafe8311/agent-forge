"""Concise v1 handoffs using existing storage; local by default, Redis explicit only."""

import json
import re
from contextlib import suppress
from datetime import datetime, timezone
from uuid import uuid4

from ..memory import LocalMemoryBackend, RedisMemoryBackend
from ..types import MemoryEntry
from ..utils import stable_project_key
from .storage import AssistError, encoded, fingerprint, private_dir, redact


def backend_for(session, state):
    if state["memory_backend"] == "redis":
        return RedisMemoryBackend(retention=100, max_bytes=2048)
    path = session.root / ".agentforge" / "memory" / "assist-v1"
    private_dir(path)
    key_path = path / (stable_project_key(project_key(session)) + ".json")
    if key_path.is_symlink():
        raise AssistError("Memory file symlink refused", "unsafe_path")
    return LocalMemoryBackend(path, retention=100, max_bytes=2048)


def project_key(session):
    return "assist-v1:" + stable_project_key(str(session.root))


def retrieve(session, state, query, limit=2048):
    backend = None
    try:
        backend = backend_for(session, state)
        entries = backend.load(project_key(session), limit=20)
    except Exception:
        return {
            "records": [],
            "warning": "Project memory unavailable; work can continue",
            "truncated": False,
        }
    finally:
        if backend:
            with suppress(Exception):
                backend.close()
    terms = set(re.findall(r"\w+", query.lower()))
    ranked = sorted(
        enumerate(entries),
        key=lambda pair: (
            -len(terms & set(re.findall(r"\w+", (pair[1].task + pair[1].summary).lower()))),
            -pair[0],
        ),
    )
    chosen: list[dict] = []
    omitted = 0
    for _, entry in ranked:
        if not entry.success:
            continue
        try:
            record = json.loads(entry.summary)
            if not isinstance(record, dict) or record.get("schema_version") != 1:
                continue
            if not isinstance(record.get("file_hashes", {}), dict):
                continue
            stale = fingerprint(session.root, record.get("file_hashes", {})) != record.get(
                "file_hashes", {}
            )
        except (ValueError, TypeError, AssistError, OSError):
            continue
        if not terms.intersection(
            re.findall(r"\w+", entry.task.lower() + " " + entry.summary.lower())
        ):
            continue
        allowed = {
            "schema_version",
            "task_id",
            "spec_hash",
            "summary",
            "decisions",
            "next_task_implications",
            "file_hashes",
            "evidence_status",
        }

        def clean(value):
            if isinstance(value, str):
                return redact(value)
            if isinstance(value, list):
                return [clean(item) for item in value]
            if isinstance(value, dict):
                return {redact(key): clean(item) for key, item in value.items()}
            return value

        record = {key: clean(value) for key, value in record.items() if key in allowed}
        record.update(stale=stale, data_only=True)
        if len(chosen) >= 5 or len(encoded(chosen + [record])) > limit:
            omitted += 1
            continue
        chosen.append(record)
    return {"records": chosen, "truncated": bool(omitted), "omitted_records": omitted}


def save(session, state, task, completion, file_hashes):
    record = {
        "schema_version": 1,
        "task_id": task.id,
        "spec_hash": state["spec_hash"],
        "summary": redact(completion.summary),
        "decisions": [redact(x) for x in completion.decisions],
        "next_task_implications": [redact(x) for x in completion.next_task_implications],
        "file_hashes": file_hashes,
        "evidence_status": "checks_passed",
    }
    entry = MemoryEntry(
        uuid4().hex,
        project_key(session),
        session.id,
        datetime.now(timezone.utc).isoformat(),
        redact(task.objective),
        encoded(record).decode(),
        [],
        True,
    )
    backend = None
    try:
        backend = backend_for(session, state)
        backend.append(entry)
    except Exception:
        return (
            "Completion saved locally; optional project memory write failed or exceeded its limit"
        )
    finally:
        if backend:
            with suppress(Exception):
                backend.close()
    return None
