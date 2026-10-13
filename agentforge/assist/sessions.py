"""Immutable private specifications and locked local session transactions."""

import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from filelock import FileLock

from .contracts import Plan, Requirement, TaskCard
from .requirements import active_requirements, excerpt, scaffold
from .storage import AssistError, digest, encoded, private_dir, read_bytes, read_json, write_private


class Session:
    def __init__(self, project: Path, session_id: str, *, create=False):
        if len(session_id) != 32 or any(c not in "0123456789abcdef" for c in session_id):
            raise AssistError("Invalid session ID")
        self.root = project.resolve()
        self.path = self.root / ".agentforge" / "sessions" / session_id
        self.id = session_id
        if not create and not (self.path / "state.json").is_file():
            raise AssistError("Session does not exist")
        private_dir(self.path)

    @contextmanager
    def transaction(self):
        with FileLock(str(self.path / "state.lock"), timeout=10):
            state = read_json(self.path / "state.json", 4194304)
            if state.get("schema_version") != 1 or state.get("project") != str(self.root):
                raise AssistError("Session schema or project mismatch")
            self.documents(state)  # Always check authoritative hashes before using derived data.
            yield state
            write_private(self.path / "state.json", encoded(state))

    def documents(self, state):
        if (self.path / "spec").is_symlink():
            raise AssistError("Specification directory symlink refused", "unsafe_path")
        result = {}
        for document in state["documents"]:
            data = read_bytes(self.path / "spec" / (document["id"] + ".md"))
            if digest(data) != document["hash"]:
                raise AssistError("Authoritative specification hash changed", "spec_changed")
            result[document["id"]] = data.decode("utf-8")
        return result

    def event(self, operation, output, *, elapsed_ms=0, files_read=0, bytes_read=0):
        event = {
            "schema_version": 1,
            "id": uuid4().hex,
            "operation": operation,
            "session": self.id,
            "timestamp": time.time(),
            "output_bytes": output["output_bytes"],
            "elapsed_ms": elapsed_ms,
            "files_read": files_read,
            "bytes_read": bytes_read,
            "source_io_scope": "context_retrieval_only",
            "status": output.get("status"),
            "truncated": output.get("truncated", False),
        }
        path = self.path / "helper-events.jsonl"
        with FileLock(str(self.path / "events.lock"), timeout=10):
            if path.is_symlink():
                raise AssistError("Event log symlink refused", "unsafe_path")
            with path.open("ab") as stream:
                stream.write(encoded(event) + b"\n")
            if path.stat().st_size > 2097152:
                # Keep a bounded history; expose measurement incompleteness, not a false total.
                data = read_bytes(path, 4194304).splitlines(keepends=True)
                marker = encoded({"schema_version": 1, "operation": "history_truncated"}) + b"\n"
                write_private(path, marker + b"".join(data[-1000:]))
            if path.exists():
                import os

                if os.name != "nt":
                    path.chmod(0o600)


def spec_hash(documents, requirements):
    return digest(encoded({"documents": documents, "requirements": requirements}))


def default_plan(state):
    ids = [r.id for r in active_requirements([Requirement(**r) for r in state["requirements"]])]
    return Plan(
        spec_hash=state["spec_hash"],
        tasks=[
            TaskCard(
                id="task",
                objective="Implement the authoritative specification and review all requirements",
                requirement_ids=ids,
            )
        ],
        planning_mode="unsplit",
    ).model_dump()


def start(project: Path, prompt: Path, *, memory_backend="local", limits=None):
    if memory_backend not in ("local", "redis"):
        raise AssistError("Memory backend must be local or redis")
    root = project.resolve()
    if not root.is_dir():
        raise AssistError("Project must be a directory")
    data = read_bytes(prompt)
    text = data.decode("utf-8")
    requirements = [r.model_dump() for r in scaffold(text)]
    session = Session(root, uuid4().hex, create=True)
    write_private(session.path / "spec" / "original.md", data, immutable=True)
    documents = [{"id": "original", "hash": digest(data), "source": str(prompt.resolve())}]
    state = {
        "schema_version": 1,
        "project": str(root),
        "documents": documents,
        "requirements": requirements,
        "spec_hash": spec_hash(documents, requirements),
        "spec_version": 1,
        "plan_version": 1,
        "completions": {},
        "evidence": {},
        "checks": [
            {
                "id": "syntax",
                "kind": "syntax",
                "files": [],
                "argv": [],
                "timeout_seconds": 30,
                "description": "Python syntax only",
            }
        ],
        "commands_approved": False,
        "memory_backend": memory_backend,
        "limits": limits or {},
        "original_review": None,
    }
    state["plan"] = default_plan(state)
    state.pop("memory_cache", None)
    write_private(session.path / "state.json", encoded(state))
    return session


def update_requirements(session, state, values):
    requirements = [Requirement(**value) for value in values]
    ids = [r.id for r in requirements]
    if len(ids) != len(set(ids)) or not ids:
        raise AssistError("Requirement IDs must be unique and nonempty")
    documents = session.documents(state)
    for req in requirements:
        if req.document not in documents:
            raise AssistError("Unknown source document")
        excerpt(req, documents)
        if any(old not in ids or old == req.id for old in req.supersedes):
            raise AssistError("Invalid supersession reference")
    # Reject supersession cycles and require every nonblank original line to remain represented.
    graph = {r.id: r.supersedes for r in requirements}

    def visit(item, trail):
        if item in trail:
            raise AssistError("Requirement supersession cycle")
        for dependency in graph[item]:
            visit(dependency, trail | {item})

    for item in graph:
        visit(item, set())
    for document, text in documents.items():
        represented = {
            n
            for r in requirements
            if r.document == document
            for n in range(r.start_line, r.end_line + 1)
        }
        if any(
            line.strip() and n not in represented for n, line in enumerate(text.splitlines(), 1)
        ):
            raise AssistError("Nonblank original requirements cannot disappear from the registry")
    state["requirements"] = [r.model_dump() for r in requirements]
    invalidate(state)


def invalidate(state):
    state["spec_hash"] = spec_hash(state["documents"], state["requirements"])
    state["spec_version"] += 1
    state["plan_version"] += 1
    state["completions"], state["evidence"], state["original_review"] = {}, {}, None
    state["plan"] = default_plan(state)
    state.pop("memory_cache", None)


def amend(session, state, prompt):
    data = read_bytes(prompt)
    number = len(state["documents"])
    name = f"amendment-{number}"
    first = 1 + max(int(r["id"][1:]) for r in state["requirements"])
    additions = scaffold(data.decode("utf-8"), name, first)
    write_private(session.path / "spec" / (name + ".md"), data, immutable=True)
    state["documents"].append({"id": name, "hash": digest(data), "source": str(prompt.resolve())})
    state["requirements"].extend(r.model_dump() for r in additions)
    invalidate(state)
