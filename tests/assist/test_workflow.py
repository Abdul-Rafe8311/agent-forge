import sys
from copy import deepcopy
from unittest.mock import Mock

import pytest

from agentforge.assist.packets import prepare
from agentforge.assist.planning import check_plan, complete, final_review, task_for, task_status
from agentforge.assist.storage import AssistError
from agentforge.assist.validation import register_checks, validate


def summary(state):
    return {
        "spec_hash": state["spec_hash"],
        "plan_version": state["plan_version"],
        "summary": "answer verified",
        "changed_files": ["app.py"],
    }


def split_plan(state):
    first = deepcopy(state["plan"]["tasks"][0])
    first["id"] = "build"
    first["requirement_ids"] = ["R1"]
    final = {**deepcopy(first), "id": "integration", "kind": "integrate", "depends_on": ["build"]}
    return {
        "spec_hash": state["spec_hash"],
        "planning_mode": "agent_model",
        "tasks": [final, first],
    }


def test_local_end_to_end_current_evidence_and_final_attestation(session, monkeypatch):
    monkeypatch.setenv("REDIS_URL", "private-do-not-read")
    monkeypatch.setattr(
        "agentforge.assist.memory.RedisMemoryBackend", Mock(side_effect=AssertionError())
    )
    with session.transaction() as state:
        task = task_for(state, "task")
        packet = prepare(session, state, task)
        assert packet["code"]["chunks"] and packet["limits_are_helper_bytes_not_codex_tokens"]
        assert packet["instructions"]["acceptance_checks"][0]["id"] == "syntax"
        assert packet["instructions"]["acceptance_checks"][0]["data_only"]
        assert any(r["scope"] == "all_tasks" for r in packet["instructions"]["requirements"])
        evidence = validate(session, state, task, "syntax")
        assert evidence["status"] == "passed" and "not behavioral" in evidence["scope"]
        done = complete(session, state, task, summary(state))
        assert done["status"] == "complete" and not done["warning"]
        assert final_review(session, state)["status"] == "review_required"
        assert (
            final_review(session, state, reviewed=True, note="Reviewed every original requirement")[
                "status"
            ]
            == "accepted"
        )
    assert session.root.joinpath(".agentforge/memory/assist-v1").is_dir()


def test_dependency_order_and_completion_handoffs(session):
    with session.transaction() as state:
        plan = check_plan(state, split_plan(state))
        assert [t.id for t in plan.tasks] == ["build", "integration"]
        assert task_status(session, state, task_for(state, "integration")) == "blocked"
        with pytest.raises(AssistError, match="dependencies"):
            complete(session, state, task_for(state, "integration"), summary(state))
        validate(session, state, task_for(state, "build"), "syntax")
        complete(session, state, task_for(state, "build"), summary(state))
        packet = prepare(session, state, task_for(state, "integration"))
        assert packet["predecessor_handoffs"][0]["summary"] == "answer verified"
        assert "original prompt" not in str(packet["predecessor_handoffs"])


def test_changed_predecessor_evidence_blocks_completed_dependents(session):
    with session.transaction() as state:
        check_plan(state, split_plan(state))
        build, integration = task_for(state, "build"), task_for(state, "integration")
        validate(session, state, build, "syntax")
        complete(session, state, build, summary(state))
        validate(session, state, integration, "syntax")
        complete(session, state, integration, summary(state))
        assert task_status(session, state, integration) == "complete"
        state["evidence"]["build:syntax"]["status"] = "failed"
        assert task_status(session, state, integration) == "blocked"
        with pytest.raises(AssistError, match="dependencies"):
            complete(session, state, integration, summary(state))
        validate(session, state, build, "syntax")
        replacement = summary(state)
        replacement["summary"] = "Updated predecessor decisions"
        complete(session, state, build, replacement)
        assert task_status(session, state, integration) == "stale"


@pytest.mark.parametrize(
    "mutation", ["cycle", "unknown", "duplicate", "no_final", "stale_hash", "missing_check"]
)
def test_bad_plans_rejected(session, mutation):
    with session.transaction() as state:
        value = split_plan(state)
        if mutation == "cycle":
            value["tasks"][1]["depends_on"] = ["integration"]
        if mutation == "unknown":
            value["tasks"][1]["depends_on"] = ["absent"]
        if mutation == "duplicate":
            value["tasks"][0]["id"] = "build"
        if mutation == "no_final":
            value["tasks"][0]["kind"] = "execute"
        if mutation == "stale_hash":
            value["spec_hash"] = "stale"
        if mutation == "missing_check":
            value["tasks"][0]["acceptance_check_ids"] = ["absent"]
        with pytest.raises(AssistError):
            check_plan(state, value)


def test_missing_coverage_check_and_unreviewed_requirements(session):
    with session.transaction() as state:
        state["requirements"][1]["scope"] = "selected_tasks"
        value = split_plan(state)
        with pytest.raises(AssistError, match="uncovered"):
            check_plan(state, value)
        state["requirements"][1]["scope"] = "all_tasks"
        state["requirements"][1]["acceptance_check_ids"] = ["behavior"]
        with pytest.raises(AssistError, match="acceptance"):
            check_plan(state, value)
        state["requirements"][1]["acceptance_check_ids"] = []
        state["requirements"][0]["clarification_status"] = "unreviewed"
        validate(session, state, task_for(state, "task"), "syntax")
        with pytest.raises(AssistError, match="Review and resolve"):
            complete(session, state, task_for(state, "task"), summary(state))


def test_changed_files_invalidate_checks_and_final_review(session):
    with session.transaction() as state:
        task = task_for(state, "task")
        validate(session, state, task, "syntax")
        (session.root / "app.py").write_text("answer=43")
        with pytest.raises(AssistError, match="stale"):
            complete(session, state, task, summary(state))
        validate(session, state, task, "syntax")
        complete(session, state, task, summary(state))
        final_review(session, state, reviewed=True, note="Reviewed original")
        (session.root / "app.py").write_text("answer=44")
        assert final_review(session, state)["status"] == "review_required"


def test_mandatory_overflow_no_dropping_and_memory_read_cache(session, monkeypatch):
    with session.transaction() as state:
        state["requirements"][0]["interpretation"] = "a" * 512
        state["limits"] = {"instruction_bytes": 512}
        packet = prepare(session, state, task_for(state, "task"))
        assert packet["status"] == "overflow" and packet["truncated"]
        state["limits"] = {}
        retrieve = Mock(return_value={"records": [], "truncated": False})
        monkeypatch.setattr("agentforge.assist.memory.retrieve", retrieve)
        prepare(session, state, task_for(state, "task"))
        prepare(session, state, task_for(state, "task"))
        retrieve.assert_called_once()
        (session.root / "app.py").write_text("answer=43")
        prepare(session, state, task_for(state, "task"))
        assert retrieve.call_count == 2


def test_corrupt_memory_warns_but_does_not_stop_packet(session, monkeypatch):
    backend = Mock()
    backend.load.side_effect = RuntimeError("private diagnostic")
    monkeypatch.setattr("agentforge.assist.memory.backend_for", lambda *_: backend)
    with session.transaction() as state:
        packet = prepare(session, state, task_for(state, "task"))
        assert packet["status"] == "ready"
        assert "unavailable" in packet["memory"]["warning"]
        assert "private diagnostic" not in str(packet)


def test_optional_redis_is_mocked_explicit_and_closed(session, monkeypatch):
    backend = Mock()
    backend.load.return_value = []
    factory = Mock(return_value=backend)
    monkeypatch.setattr("agentforge.assist.memory.RedisMemoryBackend", factory)
    with session.transaction() as state:
        state["memory_backend"] = "redis"
        prepare(session, state, task_for(state, "task"))
        factory.assert_called_once()
        backend.close.assert_called_once()


def test_command_checks_opt_in_bounded_redacted_repository_context(session):
    script = session.root / "check.py"
    script.write_text(
        "import os\nassert os.path.isfile('app.py')\nassert 'REDIS_URL' not in os.environ\n"
        "print('x' * 10000)\n"
    )
    with session.transaction() as state:
        checks = [
            {
                "id": "repo_test",
                "kind": "command",
                "argv": [sys.executable, "check.py"],
                "files": ["app.py"],
            }
        ]
        with pytest.raises(AssistError, match="approve"):
            register_checks(state, checks)
        register_checks(state, checks, approve_commands=True)
        task = task_for(state, "task")
        assert validate(session, state, task, "repo_test")["status"] == "not_run"
        result = validate(session, state, task, "repo_test", execute=True)
        assert result["status"] == "passed" and result["truncated"]
        assert len((session.path / "logs" / (result["log_id"] + ".txt")).read_bytes()) <= 16385


def test_timeout_and_manual_criteria_are_honest(session):
    with session.transaction() as state:
        register_checks(
            state,
            [
                {
                    "id": "slow",
                    "kind": "command",
                    "files": ["app.py"],
                    "argv": [sys.executable, "-c", "import time;time.sleep(3)"],
                    "timeout_seconds": 1,
                },
                {"id": "human", "kind": "manual", "files": ["app.py"]},
            ],
            approve_commands=True,
        )
        task = task_for(state, "task")
        result = validate(session, state, task, "slow", execute=True)
        assert result["status"] == "failed" and result["timeout"]
        assert validate(session, state, task, "human")["status"] == "manual_review"
        result = validate(
            session, state, task, "human", manual_status="passed", note="Reviewed actual interface"
        )
        assert result["not_automatically_verified"]


def test_completed_memory_has_stale_source_provenance(session):
    from agentforge.assist.memory import retrieve

    with session.transaction() as state:
        task = task_for(state, "task")
        validate(session, state, task, "syntax")
        complete(session, state, task, summary(state))
        assert retrieve(session, state, "answer")["records"][0]["stale"] is False
        (session.root / "app.py").write_text("answer=45")
        assert retrieve(session, state, "answer")["records"][0]["stale"] is True


def test_required_secret_and_oversize_summary_blocked(session):
    with session.transaction() as state:
        state["requirements"][0]["interpretation"] = "rediss://user:private@example.invalid:6379"
        assert prepare(session, state, task_for(state, "task"))["status"] == "blocked"
        state["requirements"][0]["interpretation"] = "answer behavior"
        validate(session, state, task_for(state, "task"), "syntax")
        value = summary(state)
        value["decisions"] = ["x" * 1000] * 4
        with pytest.raises(AssistError, match="2 KiB"):
            complete(session, state, task_for(state, "task"), value)
