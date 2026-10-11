import pytest

from agentforge.artifacts import (
    merge_artifacts,
    render_code,
    validate_artifact_path,
    write_artifacts,
)
from agentforge.exceptions import ArtifactPathError
from agentforge.types import CodeArtifact


@pytest.mark.parametrize(
    "path",
    [
        "../a",
        "/tmp/a",
        "a/../b",
        "C:/a",
        "a\\b",
        "//host/path",
        "a\x00",
        "a//b",
        "./a",
        "CON.py",
        "a:stream",
        "trailing.",
    ],
)
def test_unsafe_paths(path):
    with pytest.raises(ArtifactPathError):
        validate_artifact_path(path)


def test_merge_duplicate_collision_and_deterministic_render():
    a = CodeArtifact("a.py", "x=1")
    b = CodeArtifact("b.py", "y=2")
    assert merge_artifacts([a], [b, CodeArtifact("a.py", "x=3")])[0].content == "x=3"
    assert render_code([a]) == "x=1" and render_code([b, a]).startswith("# --- a.py ---")
    for artifacts in (
        [a, a],
        [a, CodeArtifact("a.py/b.py", "x=2")],
        [a, CodeArtifact("A.py", "x=2")],
    ):
        with pytest.raises(ArtifactPathError):
            merge_artifacts([], artifacts)


def test_write_preflight_overwrite_and_symlink(tmp_path):
    root = tmp_path / "out"
    root.mkdir()
    (root / "existing.py").write_text("original")
    artifacts = [CodeArtifact("new.py", "x=1"), CodeArtifact("existing.py", "x=2")]
    with pytest.raises(ArtifactPathError):
        write_artifacts(artifacts, root)
    assert not (root / "new.py").exists()
    write_artifacts(artifacts, root, True)
    assert (root / "existing.py").read_text() == "x=2"
    (root / "link").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ArtifactPathError):
        write_artifacts([CodeArtifact("link/escape.py", "x=1")], root)
