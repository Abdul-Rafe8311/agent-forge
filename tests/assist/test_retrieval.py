import pytest

from agentforge.assist.contracts import Limits, RelevantFile
from agentforge.assist.retrieval import Repository
from agentforge.assist.storage import AssistError, encoded, safe_path


def test_nested_ignore_negations_explicit_policy_and_no_padding(tmp_path):
    (tmp_path / ".gitignore").write_text("ignored.py\n*.json\n")
    (tmp_path / "ignored.py").write_text("answer=42")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / ".gitignore").write_text("!allowed.json\n")
    (sub / "allowed.json").write_text('{"answer":42}')
    (sub / "other.json").write_text('{"answer":0}')
    (tmp_path / "unrelated.py").write_text("unrelated=1")
    repository = Repository(tmp_path, Limits())
    result = repository.retrieve("answer")
    assert {c["path"] for c in result["chunks"]} == {"sub/allowed.json"}
    with pytest.raises(AssistError):
        Repository(tmp_path, Limits()).retrieve("answer", [RelevantFile(path="ignored.py")])


@pytest.mark.parametrize(
    "path",
    [
        "../outside.py",
        "/tmp/out.py",
        ".env",
        "a.env",
        "secrets.json",
        "private.key",
        "memory/data.json",
        ".agentforge/log.txt",
    ],
)
def test_secret_and_escape_paths_excluded(tmp_path, path):
    with pytest.raises(AssistError):
        safe_path(tmp_path, path, must_exist=False)


def test_source_symlink_excluded(tmp_path):
    (tmp_path / "app.py").write_text("answer=42")
    (tmp_path / "alias.py").symlink_to(tmp_path / "app.py")
    with pytest.raises(AssistError):
        safe_path(tmp_path, "alias.py")


def test_aggregate_read_and_reply_limits_reported(tmp_path):
    for i in range(10):
        (tmp_path / f"app{i}.py").write_text("answer='" + "x" * 400 + "'\n")
    limits = Limits(scan_bytes=1000, file_bytes=1000, code_bytes=256)
    result = Repository(tmp_path, limits).retrieve("answer")
    assert result["bytes_read"] <= 1000
    assert result["truncated"] and "aggregate_read_limit" in result["incomplete_reasons"]
    assert result["omitted_chunks"] > 0 and len(encoded(result["chunks"])) <= 256


def test_explicit_ranges_and_long_chunk_provenance(tmp_path):
    (tmp_path / "app.py").write_text("".join(f"value_{i}={i}\n" for i in range(150)))
    result = Repository(tmp_path, Limits()).retrieve(
        "no-match", [RelevantFile(path="app.py", start_line=10, end_line=100)]
    )
    assert all(c["end_line"] - c["start_line"] < 60 for c in result["chunks"])
    assert all(c["file_hash"] and c["complete_for_line_range"] for c in result["chunks"])
    assert result["chunks"][0]["start_line"] == 10


def test_missing_target_and_source_redaction(tmp_path):
    missing = Repository(tmp_path, Limits()).retrieve("new", [RelevantFile(path="new.py")])
    assert missing["context_missing"] and "requested_file_missing" in missing["incomplete_reasons"]
    (tmp_path / "app.py").write_text('url="rediss://user:private-secret@example.invalid:6379"')
    result = Repository(tmp_path, Limits()).retrieve("url")
    assert result["chunks"][0]["redacted"]
    assert "private-secret" not in str(result)


def test_file_count_limit_and_binary_skip(tmp_path):
    for i in range(8):
        (tmp_path / f"app{i}.py").write_text("answer=42")
    result = Repository(tmp_path, Limits(max_files=3)).retrieve("answer")
    assert result["scanned_entries"] == 3 and result["truncated"]
    (tmp_path / "binary.py").write_bytes(b"answer\x00")
    result = Repository(tmp_path, Limits()).retrieve("answer", [RelevantFile(path="binary.py")])
    assert not result["chunks"] and "binary_file" in result["incomplete_reasons"]
