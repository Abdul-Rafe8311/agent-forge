"""Pure dependency/coverage validation, handoffs and original-spec final review."""

import time

from ..decomposer import parse_plan
from ..exceptions import PlanningFailedError
from . import memory
from .contracts import Completion, Plan, Requirement
from .requirements import active_requirements
from .storage import AssistError, digest, encoded, fingerprint, redact, secret_present
from .validation import evidence_current


def requirements(state):
    return active_requirements([Requirement(**r) for r in state["requirements"]])


def task_for(state, task_id):
    tasks = {t.id: t for t in Plan(**state["plan"]).tasks}
    if task_id not in tasks:
        raise AssistError("Unknown task ID")
    return tasks[task_id]


def check_plan(state, value):
    plan = Plan(**value)
    if secret_present(encoded(plan.model_dump()).decode()):
        raise AssistError("Credential-like plan data refused; use private configuration references")
    if plan.spec_hash != state["spec_hash"]:
        raise AssistError("Plan specification hash is stale", "spec_changed")
    if len(plan.tasks) > 1 and plan.planning_mode == "unsplit":
        raise AssistError(
            "Split plans must label deterministic scaffolding or agent-model planning"
        )
    try:
        ordered = parse_plan(
            encoded(
                {
                    "steps": [
                        {
                            "id": t.id,
                            "title": t.objective,
                            "instruction": t.objective,
                            "depends_on": t.depends_on,
                            "kind": t.kind,
                        }
                        for t in plan.tasks
                    ]
                }
            ).decode(),
            9,
        )
    except PlanningFailedError as error:
        raise AssistError("Plan dependencies/integration are invalid") from error
    reqs = {r.id: r for r in requirements(state)}
    covered = {r.id for r in reqs.values() if r.scope == "all_tasks"}
    checks = {c["id"] for c in state["checks"]}
    for task in plan.tasks:
        if not task.objective.strip() or len(set(task.requirement_ids)) != len(
            task.requirement_ids
        ):
            raise AssistError("Task objective/requirements are invalid")
        if any(r not in reqs for r in task.requirement_ids):
            raise AssistError("Task references an unknown or superseded requirement")
        if not task.acceptance_check_ids or any(c not in checks for c in task.acceptance_check_ids):
            raise AssistError("Every task needs registered acceptance checks")
        required_checks = {
            c
            for r in reqs.values()
            if r.id in task.requirement_ids or r.scope == "all_tasks"
            for c in r.acceptance_check_ids
        }
        if not required_checks.issubset(set(task.acceptance_check_ids)):
            raise AssistError("Task does not include its requirements' acceptance checks")
        if any(
            r.clarification_status == "needs_clarification"
            for r in reqs.values()
            if r.id in task.requirement_ids or r.scope == "all_tasks"
        ):
            raise AssistError("Resolve requirement clarification before installing this plan")
        covered.update(task.requirement_ids)
    if covered != set(reqs):
        raise AssistError("Plan leaves original requirements uncovered")
    by_id = {t.id: t for t in plan.tasks}
    plan.tasks = [by_id[t.id] for t in ordered.steps]
    state["plan"] = plan.model_dump()
    state["plan_version"] += 1
    state["completions"], state["evidence"], state["original_review"] = {}, {}, None
    state.pop("memory_cache", None)
    return plan


def completion_current(session, state, task_id):
    completed = state["completions"].get(task_id)
    if not completed:
        return False
    task = task_for(state, task_id)
    for check_id in task.acceptance_check_ids:
        evidence = state["evidence"].get(task.id + ":" + check_id)
        if (
            not evidence
            or evidence["status"] != "passed"
            or not evidence_current(session, state, evidence)
        ):
            return False
    for dependency in task.depends_on:
        if not completion_current(session, state, dependency):
            return False
        if completed.get("dependency_hashes", {}).get(dependency) != digest(
            encoded(state["completions"][dependency])
        ):
            return False
    return (
        completed["handoff"]["spec_hash"] == state["spec_hash"]
        and completed["handoff"]["plan_version"] == state["plan_version"]
        and completed["file_hashes"] == fingerprint(session.root, completed["file_hashes"])
    )


def task_status(session, state, task):
    if any(not completion_current(session, state, dep) for dep in task.depends_on):
        return "blocked"
    if task.id in state["completions"]:
        return "complete" if completion_current(session, state, task.id) else "stale"
    return "ready"


def complete(session, state, task, value):
    completion = Completion(**value)
    if (
        completion.spec_hash != state["spec_hash"]
        or completion.plan_version != state["plan_version"]
    ):
        raise AssistError("Completion refers to stale requirements/plan")
    if len(encoded(completion.model_dump())) > 2048:
        raise AssistError("Completion handoff exceeds 2 KiB; shorten the summary", "overflow")
    if completion.unresolved_questions:
        raise AssistError("Unresolved questions cannot be marked complete")
    if any(
        r.clarification_status != "resolved"
        for r in requirements(state)
        if r.id in task.requirement_ids or r.scope == "all_tasks"
    ):
        raise AssistError("Review and resolve applicable original requirements before completion")
    if task_status(session, state, task) == "blocked":
        raise AssistError("Task dependencies have not passed")
    for check_id in task.acceptance_check_ids:
        evidence = state["evidence"].get(task.id + ":" + check_id)
        if (
            not evidence
            or evidence["status"] != "passed"
            or not evidence_current(session, state, evidence)
        ):
            raise AssistError("Required acceptance check is missing, failed or stale")
    if task.manual_acceptance_criteria and not any(
        c["kind"] == "manual" and c["id"] in task.acceptance_check_ids for c in state["checks"]
    ):
        raise AssistError("Manual acceptance criteria need an explicit manual check")
    hashes = fingerprint(session.root, completion.changed_files)
    handoff = completion.model_dump()
    handoff = {
        **handoff,
        "summary": redact(handoff["summary"]),
        "decisions": [redact(x) for x in handoff["decisions"]],
        "next_task_implications": [redact(x) for x in handoff["next_task_implications"]],
    }
    state["completions"][task.id] = {
        "handoff": handoff,
        "file_hashes": hashes,
        "timestamp": time.time(),
        "dependency_hashes": {
            dep: digest(encoded(state["completions"][dep])) for dep in task.depends_on
        },
    }
    state["original_review"] = None
    state.pop("memory_cache", None)
    warning = memory.save(session, state, task, completion, hashes)
    return {"status": "complete", "task_id": task.id, "handoff": handoff, "warning": warning}


def final_review(session, state, *, reviewed=False, note=""):
    statuses = {t.id: task_status(session, state, t) for t in Plan(**state["plan"]).tasks}
    evidence = {
        key: {
            "status": e["status"] if evidence_current(session, state, e) else "stale",
            "scope": e.get("scope", e.get("source", "configured check")),
        }
        for key, e in state["evidence"].items()
    }
    if reviewed:
        if not note.strip():
            raise AssistError("Original-spec review needs an explicit note")
        state["original_review"] = {
            "spec_hash": state["spec_hash"],
            "plan_version": state["plan_version"],
            "note": redact(note)[:1000],
            "source": "agent_or_operator_attested",
        }
    pending = []
    coverage = []
    for req in requirements(state):
        owners = [
            t
            for t in Plan(**state["plan"]).tasks
            if req.id in t.requirement_ids or req.scope == "all_tasks"
        ]
        checks_passed = all(
            all(
                evidence.get(t.id + ":" + c, {}).get("status") == "passed"
                for c in t.acceptance_check_ids
            )
            for t in owners
        )
        passed = (
            bool(owners) and checks_passed and all(statuses[t.id] == "complete" for t in owners)
        )
        status = "passed" if passed and req.clarification_status == "resolved" else "blocked"
        if status != "passed":
            pending.append(req.id)
        coverage.append(
            {
                "requirement_id": req.id,
                "status": status,
                "tasks": [t.id for t in owners],
                "source_document": req.document,
                "source_lines": [req.start_line, req.end_line],
            }
        )
    review = state["original_review"]
    ready = not pending and all(v == "complete" for v in statuses.values()) and review is not None
    return {
        "status": "accepted" if ready else "review_required",
        "spec_hash": state["spec_hash"],
        "plan_version": state["plan_version"],
        "tasks": statuses,
        "requirements": coverage,
        "evidence": evidence,
        "original_review": review,
        "pending_requirements": pending,
        "notice": "Coverage and manual attestations do not prove semantic correctness",
        "original_documents": [{"id": d["id"], "hash": d["hash"]} for d in state["documents"]],
    }
