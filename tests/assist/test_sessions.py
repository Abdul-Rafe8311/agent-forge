import os

import pytest

from agentforge.assist.contracts import Limits, Requirement
from agentforge.assist.packets import spec_page
from agentforge.assist.sessions import Session, amend, start, update_requirements
from agentforge.assist.storage import AssistError, encoded, response


def test_verbatim_unicode_crlf_private_spec_and_default_unsplit(tmp_path):
    prompt = tmp_path / "prompt.md"
    data = "需求\r\n\r\n- Keep compatibility.\r\n".encode()
    prompt.write_bytes(data)
    session = start(tmp_path, prompt)
    assert (session.path / "spec/original.md").read_bytes() == data
    if os.name != "nt":
        assert (session.path / "spec/original.md").stat().st_mode & 0o777 == 0o600
        assert session.path.stat().st_mode & 0o777 == 0o700
    with session.transaction() as state:
        assert state["plan"]["planning_mode"] == "unsplit"
        assert len(state["plan"]["tasks"]) == 1
        assert state["memory_backend"] == "local"


def test_amendment_retains_original_invalidates_evidence(session, tmp_path):
    original = (session.path / "spec/original.md").read_bytes()
    amendment = tmp_path / "amendment.md"
    amendment.write_text("Return 43 instead.\n")
    with session.transaction() as state:
        old_hash = state["spec_hash"]
        state["completions"] = {"task": {"dummy": True}}
        state["evidence"] = {"task:syntax": {"dummy": True}}
        amend(session, state, amendment)
        assert state["spec_hash"] != old_hash
        assert not state["evidence"] and not state["completions"]
        assert len(state["documents"]) == 2
    assert (session.path / "spec/original.md").read_bytes() == original


def test_spec_tampering_fails_closed(session):
    (session.path / "spec/original.md").write_text("changed")
    with pytest.raises(AssistError, match="hash changed"):
        with session.transaction():
            pass


@pytest.mark.parametrize("invalid", ["../outside", "A" * 32, "abc"])
def test_session_ids_cannot_escape_storage(tmp_path, invalid):
    with pytest.raises(AssistError):
        Session(tmp_path, invalid)


def test_source_spans_cannot_erase_requirement_lines(session):
    with session.transaction() as state:
        with pytest.raises(AssistError, match="cannot disappear"):
            update_requirements(session, state, state["requirements"][:1])
        values = [dict(r) for r in state["requirements"]]
        values[0]["end_line"] = 999
        with pytest.raises(AssistError, match="range"):
            update_requirements(session, state, values)


def test_supersession_cycles_rejected(session):
    with session.transaction() as state:
        values = [dict(r) for r in state["requirements"]]
        values[0]["supersedes"] = ["R2"]
        values[1]["supersedes"] = ["R1"]
        with pytest.raises(AssistError, match="cycle"):
            update_requirements(session, state, values)


def test_long_spec_pages_reassemble_without_loss(tmp_path):
    prompt = tmp_path / "long.md"
    original = "界" * 10000 + "\nLast requirement.\n"
    prompt.write_text(original)
    session = start(tmp_path, prompt)
    pieces, offset = [], 0
    with session.transaction() as state:
        while True:
            page = spec_page(session, state, offset=offset)
            assert len(encoded(page)) + 1 == page["output_bytes"] <= 8192
            pieces.append(page["text"])
            if page["next_offset"] is None:
                break
            assert page["truncated"] and page["next_offset"] > offset
            offset = page["next_offset"]
    assert "".join(pieces) == original


def test_secret_spec_preserved_but_output_redacted(tmp_path):
    prompt = tmp_path / "secret.md"
    original = "Use rediss://user:private-secret@example.invalid:6379 safely."
    prompt.write_text(original)
    session = start(tmp_path, prompt)
    with session.transaction() as state:
        page = spec_page(session, state)
        assert "private-secret" not in page["text"] and page["redacted"]
    assert (session.path / "spec/original.md").read_text() == original


def test_complete_json_overflow_and_bad_limits():
    value = response({"status": "ok", "content": "x" * 5000}, 1024)
    assert value["status"] == "overflow" and value["truncated"]
    assert len(encoded(value)) + 1 == value["output_bytes"] <= 1024
    with pytest.raises(ValueError):
        Limits(packet_bytes=20)
    with pytest.raises(ValueError):
        Requirement(id="R1", document="original", start_line=0, end_line=1)
