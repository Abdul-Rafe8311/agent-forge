"""Stateless context retrieval: no prompt registry, task plan, memory or network."""

from pathlib import Path

from .contracts import Limits, RelevantFile
from .retrieval import Repository
from .storage import AssistError, encoded


def context(
    root: Path,
    query: str,
    files: list[str] | None = None,
    *,
    max_bytes: int = 4096,
    max_chunks: int = 3,
    start_line: int | None = None,
    end_line: int | None = None,
):
    files = files or []
    if not root.is_dir():
        raise AssistError("Project must be an existing directory")
    if not query.strip() or len(query) > 512:
        raise AssistError("Use a nonempty query of at most 512 characters")
    if not 1024 <= max_bytes <= 16384 or not 1 <= max_chunks <= 6 or len(files) > 20:
        raise AssistError("Use 1024-16384 reply bytes, 1-6 chunks and at most 20 files")
    if (start_line is not None or end_line is not None) and (
        len(files) != 1
        or start_line is None
        or start_line < 1
        or (end_line is not None and end_line < start_line)
    ):
        raise AssistError("A line range needs one --file and a positive --start-line")
    requested = [RelevantFile(path=f, start_line=start_line, end_line=end_line) for f in files]
    limits = Limits(code_bytes=max_bytes - 384, max_chunks=max_chunks)
    window_lines = min(20, max(1, (max_bytes - 384) // 80))
    result = Repository(root, limits).retrieve(
        query, requested, window_lines=window_lines, source_only=True
    )
    # Keep provenance and incomplete flags; omit scoring and redundant per-chunk policy.
    for chunk in result["chunks"]:
        chunk.pop("score", None)
        chunk.pop("data_only", None)
        if not chunk.get("redacted"):
            chunk.pop("redacted", None)
    for key in ("scanned_entries", "files_read", "bytes_read"):
        result.pop(key)
    result["status"] = "ok"
    while len(encoded(result)) + 100 > max_bytes and result["chunks"]:
        result["chunks"].pop()
        result["omitted_chunks"] += 1
        result["truncated"] = True
        result["incomplete_reasons"] = sorted(
            set(result["incomplete_reasons"]) | {"context_output_limit"}
        )
    result["context_missing"] = not result["chunks"]
    return result
