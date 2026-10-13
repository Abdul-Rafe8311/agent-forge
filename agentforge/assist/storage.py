"""Private bounded storage, complete JSON responses, and project path boundaries."""

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path


class AssistError(ValueError):
    def __init__(self, message, code="invalid_input"):
        super().__init__(message)
        self.code = code


def encoded(value) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def private_dir(path: Path):
    missing = []
    for parent in [*reversed(path.parents), path]:
        if parent.is_symlink():
            raise AssistError("Private storage must not contain symlinks", "unsafe_path")
        if not parent.exists():
            missing.append(parent)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        for parent in missing:
            parent.chmod(0o700)
        path.chmod(0o700)


def write_private(path: Path, data: bytes, *, immutable=False):
    private_dir(path.parent)
    if path.is_symlink():
        raise AssistError("Refusing a storage symlink", "unsafe_path")
    if immutable:
        with path.open("xb") as stream:
            if os.name != "nt":
                os.fchmod(stream.fileno(), 0o600)
            stream.write(data)
        return
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read_bytes(path: Path, limit=1048576):
    if path.is_symlink() or not path.is_file():
        raise AssistError("Input must be a regular file", "unsafe_path")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise AssistError("Input exceeds its byte limit; nothing was truncated", "overflow")
    return data


def read_json(path: Path, limit=1048576):
    return json.loads(read_bytes(path, limit))


def safe_path(root: Path, relative: str, *, must_exist=True):
    path = Path(relative)
    if path.is_absolute() or not path.parts or any(p in (".", "..") for p in path.parts):
        raise AssistError("Use a project-relative path without traversal", "unsafe_path")
    denied = {
        "credentials.json",
        "secrets.json",
        "memory",
        "local-memory",
        "node_modules",
        "build",
        "dist",
        "env",
        "venv",
        "generated",
        "output",
    }
    if (
        any(p.startswith(".") or p in denied for p in path.parts)
        or path.suffix
        in (
            ".pem",
            ".key",
            ".pyc",
            ".sqlite3",
            ".env",
        )
        or re.search(r"\.env(?:\.|$)", path.name)
    ):
        raise AssistError("Path excluded from helper access", "excluded_path")
    candidate = root / path
    if any((root.joinpath(*path.parts[:i])).is_symlink() for i in range(1, len(path.parts) + 1)):
        raise AssistError("Source symlinks are excluded", "unsafe_path")
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise AssistError("Path escapes the project", "unsafe_path")
    if must_exist and not candidate.is_file():
        raise AssistError("Requested source file is missing", "missing_file")
    return candidate


def fingerprint(root: Path, paths):
    result = {}
    for relative in sorted(set(paths)):
        path = safe_path(root, relative, must_exist=False)
        result[relative] = digest(read_bytes(path)) if path.is_file() else "missing"
    return result


def response(value: dict, limit=20480):
    """Measured serialized bytes, including newline; never emit partial JSON."""
    value = dict(value)

    def clean(item):
        if isinstance(item, str):
            return redact(item)
        if isinstance(item, list):
            return [clean(part) for part in item]
        if isinstance(item, dict):
            return {redact(key): clean(part) for key, part in item.items()}
        return item

    cleaned = clean(value)
    if cleaned != value:
        cleaned["redacted"] = True
    value = cleaned
    value.setdefault("truncated", False)
    value["output_bytes"] = 0
    for _ in range(8):
        count = len(encoded(value)) + 1
        if count == value["output_bytes"]:
            break
        value["output_bytes"] = count
    if value["output_bytes"] > limit:
        return response(
            {
                "status": "overflow",
                "truncated": True,
                "message": "Response exceeds its byte limit; use paged retrieval",
                "limit_bytes": limit,
            },
            limit,
        )
    return value


def secret_present(text: str):
    return bool(
        re.search(
            r"(?:sk-(?:ant-)?[A-Za-z0-9_-]{8,}|pypi-[A-Za-z0-9_-]{30,}|"
            r"rediss?://[^\s/@]+:[^\s@]+@|gh[pousr]_[A-Za-z0-9]{30,}|"
            r"github_pat_[A-Za-z0-9_]{30,}|-----BEGIN .*PRIVATE KEY-----)",
            text,
        )
    )


def redact(text):
    from ..utils import redact_sensitive_text

    text = redact_sensitive_text(text)
    text = re.sub(
        r"(?:pypi-[A-Za-z0-9_-]{30,}|gh[pousr]_[A-Za-z0-9]{30,}|"
        r"github_pat_[A-Za-z0-9_]{30,})",
        "[REDACTED]",
        text,
    )
    return re.sub(
        r"-----BEGIN .*PRIVATE KEY-----.*?(?:-----END .*PRIVATE KEY-----|$)",
        "[REDACTED PRIVATE KEY]",
        text,
        flags=re.DOTALL,
    )
