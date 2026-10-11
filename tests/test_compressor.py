from agentforge.compressor import ContextCompressor
from agentforge.utils import estimate_tokens


def test_gitignore_secrets_binaries_oversize_symlinks_and_provenance(tmp_path):
    (tmp_path / "auth.py").write_text("def authenticate(user):\n    return user\n")
    (tmp_path / ".gitignore").write_text("ignored.py\nprivate/\n")
    for name in ("ignored.py", ".env", "credentials.json", "secret.key"):
        (tmp_path / name).write_text("PRIVATE_SECRET")
    (tmp_path / "private").mkdir()
    (tmp_path / "private" / "secret.py").write_text("PRIVATE_SECRET")
    (tmp_path / "binary.py").write_bytes(b"\x00")
    (tmp_path / "large.py").write_text("x" * 1000)
    (tmp_path / "linked.py").symlink_to(tmp_path / "auth.py")
    compressor = ContextCompressor(tmp_path, max_bytes=100)
    context = compressor.compress("authenticate user", 500)
    assert "authenticate" in context.text and "PRIVATE_SECRET" not in context.text
    assert all(c.start_line >= 1 and c.end_line >= c.start_line for c in context.chunks)
    assert estimate_tokens(context.text) <= 500 and context.skipped_files


def test_whole_chunks_are_not_silently_truncated(tmp_path):
    (tmp_path / "app.py").write_text("x='" + ("a" * 100) + "'\n")
    assert ContextCompressor(tmp_path).compress("x", 20).chunks == []
