"""Safe artifact identity, merges, and explicit per-file atomic export."""

import os
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath

from .exceptions import ArtifactPathError
from .types import CodeArtifact


def validate_artifact_path(path: str) -> str:
    """Require a safe cross-platform relative POSIX destination."""
    if (
        not isinstance(path, str)
        or not path
        or "\\" in path
        or PurePosixPath(path).is_absolute()
        or PureWindowsPath(path).drive
        or any(p in ("", ".", "..") for p in path.split("/"))
        or any(ord(c) < 32 or c in ':*?"<>|' for c in path)
    ):
        raise ArtifactPathError("Unsafe artifact path")
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    if any(p.upper().split(".")[0] in reserved or p.endswith((".", " ")) for p in path.split("/")):
        raise ArtifactPathError("Unsafe cross-platform artifact path")
    return path


def merge_artifacts(
    existing: list[CodeArtifact], incoming: list[CodeArtifact]
) -> list[CodeArtifact]:
    """Replace same paths only; validate combined file/directory identity."""
    for artifacts in (existing, incoming):
        paths = [validate_artifact_path(a.path) for a in artifacts]
        if len(set(paths)) != len(paths):
            raise ArtifactPathError("Duplicate artifact path")
    by_path = {a.path: a for a in existing}
    by_path.update({a.path: a for a in incoming})
    names = sorted(by_path)
    if len({n.casefold() for n in names}) != len(names):
        raise ArtifactPathError("Case-insensitive path collision")
    if any(a != b and b.casefold().startswith(a.casefold() + "/") for a in names for b in names):
        raise ArtifactPathError("Artifact file/directory collision")
    return [by_path[n] for n in names]


def render_code(artifacts: list[CodeArtifact]) -> str:
    """Single artifact content, otherwise deterministic filename comments."""
    ordered = sorted(artifacts, key=lambda a: a.path)
    if len(ordered) == 1:
        return ordered[0].content
    return "\n\n".join(f"# --- {a.path} ---\n{a.content}" for a in ordered)


def write_artifacts(
    artifacts: list[CodeArtifact], output_dir: Path, overwrite: bool = False
) -> list[Path]:
    """Preflight all paths; writes are atomic per file, not across the entire file set."""
    artifacts = merge_artifacts([], artifacts)
    root = output_dir.absolute()
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ArtifactPathError("Output directory contains a symlink")
    targets = [root / a.path for a in artifacts]
    for target in targets:
        for part in (target, *target.parents):
            if part.is_symlink():
                raise ArtifactPathError("Output path contains a symlink")
            if part != target and part.exists() and not part.is_dir():
                raise ArtifactPathError("Output parent is not a directory")
        if target.exists() and (not overwrite or not target.is_file()):
            raise ArtifactPathError("Output exists; explicit overwrite is required")
    for artifact, target in zip(artifacts, targets):
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=target.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(artifact.content)
            if overwrite:
                os.replace(temporary, target)
            else:
                os.link(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return targets
