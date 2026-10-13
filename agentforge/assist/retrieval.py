"""Lexical, source-linked retrieval with bounded I/O and explicit incomplete results."""

import os
import time
from dataclasses import asdict
from pathlib import Path

import pathspec

from ..compressor import _SUFFIX, ContextCompressor, chunks_from_text
from .contracts import Limits, RelevantFile
from .storage import AssistError, digest, encoded, redact, safe_path


class Repository:
    def __init__(self, root: Path, limits: Limits):
        self.root, self.limits = root.resolve(), limits
        self.started = time.monotonic()
        self.examined = self.files_read = self.bytes_read = 0
        self.reasons: set[str] = set()
        self.rules: dict[Path, list] = {}
        self.hashes: dict[str, str] = {}
        self.cache: dict[Path, str] = {}

    def within_deadline(self):
        if time.monotonic() - self.started > self.limits.scan_seconds:
            self.reasons.add("scan_deadline")
            return False
        return True

    def read(self, path):
        if path in self.cache:
            return self.cache[path]
        if not self.within_deadline():
            return None
        try:
            size = path.stat().st_size
            if size > self.limits.file_bytes:
                self.reasons.add("file_byte_limit")
                return None
            if self.bytes_read + size > self.limits.scan_bytes:
                self.reasons.add("aggregate_read_limit")
                return None
            if path.is_symlink():
                raise AssistError("Source symlinks are excluded")
            # Count every byte actually read, including a growth-detection sentinel.
            capacity = min(self.limits.file_bytes + 1, self.limits.scan_bytes - self.bytes_read)
            with path.open("rb") as stream:
                data = stream.read(capacity)
                grew_past_read = os.fstat(stream.fileno()).st_size > len(data)
            self.bytes_read += len(data)
            self.files_read += 1
            if len(data) > self.limits.file_bytes or grew_past_read:
                self.reasons.add("unreadable_or_changed_file")
                return None
            if b"\x00" in data:
                self.reasons.add("binary_file")
                return None
            text = data.decode("utf-8")
        except (OSError, UnicodeError, AssistError):
            self.reasons.add("unreadable_or_changed_file")
            return None
        self.cache[path] = text
        if path.name not in (".gitignore", ".agentforgeignore"):
            self.hashes[path.relative_to(self.root).as_posix()] = digest(data)
        return text

    def load_rules(self, base):
        if base not in self.rules:
            rules: list = []
            for name in (".gitignore", ".agentforgeignore"):
                path = base / name
                if path.is_file() and not path.is_symlink():
                    text = self.read(path)
                    if text is None:
                        raise AssistError("Ignore policy could not be read; retrieval stopped")
                    rules.extend(
                        pathspec.PathSpec.from_lines("gitwildmatch", text.splitlines()).patterns
                    )
            self.rules[base] = rules
        return self.rules[base]

    def ignored(self, path, directory=False):
        result = False
        bases = [self.root]
        parent = path.parent
        if parent != self.root:
            bases.extend(
                reversed(
                    [
                        p
                        for p in [parent, *parent.parents]
                        if p != self.root and p.is_relative_to(self.root)
                    ]
                )
            )
        for base in bases:
            relative = path.relative_to(base).as_posix() + ("/" if directory else "")
            for pattern in self.load_rules(base):
                if pattern.include is not None and pattern.match_file(relative):
                    result = bool(pattern.include)
        return result

    def allowed(self, path):
        try:
            relative = path.relative_to(self.root).as_posix()
            safe_path(self.root, relative)
        except (AssistError, ValueError):
            return False
        return path.suffix in _SUFFIX and not self.ignored(path)

    def discover(self):
        found = []

        def walk(base, depth):
            if not self.within_deadline():
                return
            self.load_rules(base)
            entries = []
            with os.scandir(base) as iterator:
                for entry in iterator:
                    if self.examined >= self.limits.max_files:
                        self.reasons.add("examined_file_limit")
                        break
                    self.examined += 1
                    entries.append(entry)
            for entry in sorted(entries, key=lambda e: e.name):
                path = Path(entry.path)
                if entry.is_symlink() or entry.name.startswith("."):
                    continue
                if entry.is_dir(follow_symlinks=False):
                    try:
                        safe_path(
                            self.root, path.relative_to(self.root).as_posix(), must_exist=False
                        )
                    except AssistError:
                        continue
                    if depth >= self.limits.max_depth:
                        self.reasons.add("depth_limit")
                    elif not self.ignored(path, directory=True):
                        walk(path, depth + 1)
                elif self.allowed(path):
                    found.append(path)
                if not self.within_deadline():
                    return

        try:
            walk(self.root, 0)
        except OSError:
            self.reasons.add("unreadable_directory")
        return found

    def retrieve(self, query, requested: list[RelevantFile] | None = None, *, metadata_only=False):
        requested = requested or []
        explicit = {r.path: r for r in requested}
        files = []
        for selection in requested:
            path = safe_path(self.root, selection.path, must_exist=False)
            if not path.is_file():
                self.reasons.add("requested_file_missing")
                continue
            if not self.allowed(path):
                raise AssistError("Requested file is ignored or excluded")
            files.append(path)
        if not requested:
            files = self.discover()
        chunks = []
        for path in files:
            text = self.read(path)
            if text is None:
                continue
            relative = path.relative_to(self.root).as_posix()
            request = explicit.get(relative)
            if request and request.start_line:
                lines = text.splitlines(keepends=True)
                end = request.end_line or min(request.start_line + 59, len(lines))
                if end < request.start_line or end > len(lines):
                    raise AssistError("Requested source range is invalid")
                from ..types import ContextChunk

                for at in range(request.start_line, end + 1, 60):
                    stop = min(at + 59, end)
                    chunks.append(ContextChunk(relative, at, stop, "".join(lines[at - 1 : stop])))
            else:
                chunks.extend(chunks_from_text(relative, text))
        ranked = ContextCompressor(self.root).score_chunks(query, chunks)
        selected: list[dict] = []
        relevant = [c for c in ranked if c.score > 0 or c.path in explicit]
        limit = 4096 if metadata_only else self.limits.code_bytes
        omitted = 0
        for chunk in relevant:
            item = asdict(chunk)
            original = item.pop("content")
            item["file_hash"] = self.hashes[chunk.path]
            item["data_only"] = True
            if not metadata_only:
                item["content"] = redact(original)
                item["redacted"] = item["content"] != original
                item["complete_for_line_range"] = True
            if len(selected) >= self.limits.max_chunks or len(encoded(selected + [item])) > limit:
                omitted += 1
                continue
            selected.append(item)
        if omitted:
            self.reasons.add("context_output_limit")
        return {
            "chunks": selected,
            "omitted_chunks": omitted,
            "truncated": bool(self.reasons),
            "incomplete_reasons": sorted(self.reasons),
            "scanned_entries": self.examined,
            "files_read": self.files_read,
            "bytes_read": self.bytes_read,
            "context_missing": not selected,
            "data_only": True,
        }
