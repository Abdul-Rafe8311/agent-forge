"""Bounded lexical source retrieval with gitignore support and line provenance."""

import ast
import os
import re
from dataclasses import replace
from pathlib import Path

import pathspec

from .exceptions import ConfigurationError
from .types import ContextBundle, ContextChunk
from .utils import estimate_tokens

_SKIP = {
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "build",
    "dist",
    "__pycache__",
    ".agentforge",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".wheel-check",
}
_SUFFIX = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".json",
    ".md",
    ".toml",
    ".sql",
    ".html",
    ".css",
    ".go",
    ".rs",
}


def chunks_from_text(relative_path: str, text: str) -> list[ContextChunk]:
    """Pure line/AST windows, reusable when a caller already performed a bounded read."""
    lines = text.splitlines(keepends=True)
    boundaries = []
    if relative_path.endswith(".py"):
        try:
            tree = ast.parse(text)
            boundaries = [
                (node.lineno, getattr(node, "end_lineno", node.lineno)) for node in tree.body
            ]
        except SyntaxError:
            pass
    if not boundaries:
        boundaries = [(i + 1, min(i + 60, len(lines))) for i in range(0, len(lines), 60)]
    windows = [
        (at, min(at + 59, end)) for start, end in boundaries for at in range(start, end + 1, 60)
    ]
    return [ContextChunk(relative_path, a, b, "".join(lines[a - 1 : b])) for a, b in windows]


class ContextCompressor:
    def __init__(
        self,
        codebase_path: Path,
        *,
        max_files: int = 2000,
        max_bytes: int = 262144,
        max_depth: int = 12,
    ):
        """Configure bounded source reads; no scan occurs at import/construction."""
        self.root = Path(codebase_path).resolve()
        if not self.root.is_dir():
            raise ConfigurationError("Codebase must be a readable directory")
        if any(type(n) is not int or n < 1 for n in (max_files, max_bytes, max_depth)):
            raise ConfigurationError("Source scan limits must be positive integers")
        self.max_files, self.max_bytes, self.max_depth = max_files, max_bytes, max_depth
        self.skipped: list[str] = []

    def scan_files(self) -> list[Path]:
        """Enumerate deterministic safe files respecting root and nested ignore rules."""
        self.skipped = []
        found: list[Path] = []
        specs = []
        scanned = 0
        for directory, dirs, names in os.walk(self.root, followlinks=False):
            base = Path(directory)
            relative = base.relative_to(self.root)
            for ignore in (base / ".gitignore", base / ".agentforgeignore"):
                if (
                    ignore.is_file()
                    and not ignore.is_symlink()
                    and ignore.stat().st_size <= self.max_bytes
                ):
                    specs.append(
                        (
                            base,
                            pathspec.PathSpec.from_lines(
                                "gitwildmatch", ignore.read_text(encoding="utf-8").splitlines()
                            ),
                        )
                    )
            dirs[:] = sorted(
                d
                for d in dirs
                if d not in _SKIP
                and not d.startswith(".")
                and not (base / d).is_symlink()
                and len(relative.parts) < self.max_depth
            )
            for name in sorted(names):
                scanned += 1
                if scanned > self.max_files:
                    return found
                path = base / name
                rel = path.relative_to(self.root).as_posix()
                if (
                    path.is_symlink()
                    or name.startswith(".")
                    or path.suffix in (".pem", ".key")
                    or name in ("credentials.json", "secrets.json")
                    or path.suffix not in _SUFFIX
                    or any(
                        path.is_relative_to(folder)
                        and spec.match_file(path.relative_to(folder).as_posix())
                        for folder, spec in specs
                    )
                ):
                    self.skipped.append(rel)
                    continue
                found.append(path)
        return found

    def extract_chunks(self, path: Path) -> list[ContextChunk]:
        """Read at most the byte cap; use Python boundaries or bounded 60-line windows."""
        if path.is_symlink() or not path.resolve().is_relative_to(self.root):
            return []
        try:
            if path.stat().st_size > self.max_bytes:
                raise ValueError()
            with path.open("rb") as stream:
                data = stream.read(self.max_bytes + 1)
            if len(data) > self.max_bytes or b"\x00" in data:
                raise ValueError()
            text = data.decode("utf-8")
        except (OSError, ValueError, UnicodeError):
            self.skipped.append(path.relative_to(self.root).as_posix())
            return []
        return chunks_from_text(path.relative_to(self.root).as_posix(), text)

    def score_chunks(self, task: str, chunks: list[ContextChunk]) -> list[ContextChunk]:
        """Rank lexical overlap, then use stable filename/line tie breaks."""
        terms = set(re.findall(r"\w+", task.lower()))
        scored = [
            replace(
                c,
                score=float(
                    len(terms & set(re.findall(r"\w+", c.content.lower())))
                    + 4 * len(terms & set(re.findall(r"\w+", c.path.lower())))
                ),
            )
            for c in chunks
        ]
        return sorted(scored, key=lambda c: (-c.score, c.path, c.start_line))

    def compress(self, task: str, token_limit: int) -> ContextBundle:
        """Pack complete chunks under a documented estimator; no remote summarization."""
        chunks = [c for path in self.scan_files() for c in self.extract_chunks(path)]
        chosen = []
        text = ""
        for chunk in self.score_chunks(task, chunks):
            candidate = (
                text
                + f"\n--- {chunk.path}:{chunk.start_line}-{chunk.end_line} ---\n"
                + chunk.content
            )
            if estimate_tokens(candidate) <= token_limit:
                text = candidate
                chosen.append(chunk)
        return ContextBundle(text, chosen, estimate_tokens(text), self.skipped)
