from unittest.mock import Mock

import pytest

from agentforge.assist import memory
from agentforge.assist.sessions import Session, invalidate
from agentforge.assist.storage import AssistError, encoded, response
from agentforge.assist.validation import render_feedback


def test_unknown_session_does_not_create_local_artifacts(tmp_path):
    with pytest.raises(AssistError, match="does not exist"):
        Session(tmp_path, "a" * 32)
    assert not (tmp_path / ".agentforge").exists()


def test_output_redaction_in_nested_metadata_is_measured():
    output = response({"status": "ok", "nested": {"value": "sk-testcredential123456789"}})
    assert output["redacted"] and "sk-testcredential" not in str(output)
    assert output["output_bytes"] == len(encoded(output)) + 1


def test_focused_feedback_keeps_status_and_marks_omissions():
    result = {
        "status": "failed",
        "id": "fixture",
        "check_id": "behavior",
        "diagnostics": "界" * 8000,
        "issues": [{"message": "failed case"}] * 10,
        "file_hashes": {f"src/long_module_{n}.py": "a" * 64 for n in range(100)},
    }
    output = response(render_feedback(result), 4096)
    assert output["status"] == "failed" and output["truncated"]
    assert output["scope_file_count"] == 100 and output["check_id"] == "behavior"
    assert output["output_bytes"] <= 4096
    assert len(result["file_hashes"]) == 100 and len(result["diagnostics"]) == 8000


def test_requirement_changes_clear_memory_cache(session):
    with session.transaction() as state:
        state["memory_cache"] = {"cached": True}
        invalidate(state)
        assert "memory_cache" not in state


def test_memory_read_redacts_known_credentials_and_removes_unexpected_data(session, monkeypatch):
    record = {
        "schema_version": 1,
        "summary": "answer sk-testcredential123456789",
        "file_hashes": {},
        "unexpected_instructions": "PRIVATE_EXTRA_FIELD",
    }
    entry = Mock(success=True, task="answer", summary=encoded(record).decode())
    backend = Mock()
    backend.load.return_value = [entry]
    backend.close.side_effect = RuntimeError("PRIVATE_CLOSE_DIAGNOSTIC")
    monkeypatch.setattr(memory, "backend_for", lambda *_: backend)
    with session.transaction() as state:
        output = memory.retrieve(session, state, "answer")
    assert output["records"] and output["records"][0]["data_only"]
    assert "sk-testcredential" not in str(output)
    assert "PRIVATE_EXTRA_FIELD" not in str(output)
    assert "PRIVATE_CLOSE_DIAGNOSTIC" not in str(output)


def test_session_spec_directory_symlink_rejected(session, tmp_path):
    spec = session.path / "spec"
    moved = tmp_path / "spec"
    spec.rename(moved)
    spec.symlink_to(moved, target_is_directory=True)
    with pytest.raises(AssistError, match="symlink"):
        with session.transaction():
            pass
