"""Versioned locked local JSON and lazy TLS Redis project memory."""

import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from filelock import FileLock
from platformdirs import user_data_path
from pydantic import TypeAdapter

from .config import validate_redis_url
from .exceptions import ConfigurationError, MemoryBackendError
from .types import AgentResult, CodeArtifact, MemoryEntry
from .utils import estimate_tokens, redact_sensitive_text, stable_project_key

_ENTRY = TypeAdapter(MemoryEntry)


def _encode(entry: MemoryEntry, max_bytes: int) -> str:
    value = json.dumps(asdict(entry), ensure_ascii=False)
    if len(value.encode()) > max_bytes:
        raise MemoryBackendError("Memory entry exceeds byte limit")
    return value


def _decode(value: str | bytes, max_bytes: int = 262144) -> MemoryEntry:
    if len(value.encode() if isinstance(value, str) else value) > max_bytes:
        raise ValueError("Oversized memory entry")
    return _ENTRY.validate_json(value, strict=True)


class MemoryBackend(Protocol):
    def load(self, project_id: str, limit: int = 20) -> list[MemoryEntry]: ...
    def append(self, entry: MemoryEntry) -> None: ...
    def clear(self, project_id: str) -> None: ...
    def close(self) -> None: ...


class LocalMemoryBackend:
    def __init__(
        self, base_path: Path | None = None, retention: int = 100, max_bytes: int = 262144
    ):
        """Retain limits/path without creating storage; all updates are filelocked and atomic."""
        self.base_path = base_path or user_data_path("agentforge") / "memory"
        if (
            type(retention) is not int
            or retention < 1
            or type(max_bytes) is not int
            or max_bytes < 512
        ):
            raise ConfigurationError(
                "Memory retention must be positive and entry limit at least 512"
            )
        self.retention, self.max_bytes = retention, max_bytes

    def _path(self, project_id: str) -> Path:
        return self.base_path / (stable_project_key(project_id) + ".json")

    def _read(self, path: Path) -> list[MemoryEntry]:
        if not path.exists():
            return []
        try:
            if path.stat().st_size > self.retention * self.max_bytes + 65536:
                raise ValueError("Oversized memory storage")
            data = json.loads(path.read_text(encoding="utf-8"))
            if data["version"] != 1 or not isinstance(data["entries"], list):
                raise ValueError()
            return [_decode(json.dumps(item), self.max_bytes) for item in data["entries"]]
        except Exception as exc:
            raise MemoryBackendError("Local memory is corrupt or unreadable") from exc

    def load(self, project_id: str, limit: int = 20) -> list[MemoryEntry]:
        """Return newest entries in oldest-to-newest order; corruption raises without deletion."""
        if limit < 1:
            raise ConfigurationError("Memory load limit must be positive")
        path = self._path(project_id)
        if not self.base_path.exists():
            return []
        try:
            with FileLock(str(path) + ".lock", timeout=10):
                return self._read(path)[-limit:]
        except MemoryBackendError:
            raise
        except Exception as exc:
            raise MemoryBackendError("Local memory read failed") from exc

    def append(self, entry: MemoryEntry) -> None:
        """Synchronize read-modify-write and replace a complete versioned file atomically."""
        _encode(entry, self.max_bytes)
        path = self._path(entry.project_id)
        try:
            self.base_path.mkdir(parents=True, exist_ok=True)
            with FileLock(str(path) + ".lock", timeout=10):
                entries = (self._read(path) + [entry])[-self.retention :]
                fd, temp = tempfile.mkstemp(dir=self.base_path)
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as stream:
                        json.dump({"version": 1, "entries": [asdict(e) for e in entries]}, stream)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temp, path)
                finally:
                    Path(temp).unlink(missing_ok=True)
        except MemoryBackendError:
            raise
        except Exception as exc:
            raise MemoryBackendError("Local memory append failed") from exc

    def clear(self, project_id: str) -> None:
        """Remove only one project while holding its lock."""
        if not self.base_path.exists():
            return
        path = self._path(project_id)
        try:
            with FileLock(str(path) + ".lock", timeout=10):
                path.unlink(missing_ok=True)
        except Exception as exc:
            raise MemoryBackendError("Local memory clear failed") from exc

    def close(self) -> None:
        """No persistent file handle is retained."""


class RedisMemoryBackend:
    def __init__(
        self,
        redis_url: str | None = None,
        *,
        client: Any = None,
        retention: int = 100,
        max_bytes: int = 262144,
    ):
        """Retain a TLS URL or borrowed mock/client; never connect during construction."""
        self._url = (
            validate_redis_url(redis_url or os.environ.get("REDIS_URL")) if client is None else None
        )
        self._client, self._owns = client, client is None
        if (
            type(retention) is not int
            or retention < 1
            or type(max_bytes) is not int
            or max_bytes < 512
        ):
            raise ConfigurationError(
                "Memory retention must be positive and entry limit at least 512"
            )
        self.retention, self.max_bytes = retention, max_bytes

    def _get(self):
        if self._client is None:
            try:
                import redis
            except ImportError as exc:
                raise ConfigurationError('Install "agentforge-coding[redis]"') from exc
            self._client = redis.Redis.from_url(
                self._url or "",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                ssl_cert_reqs="required",
                ssl_check_hostname=True,
            )
        return self._client

    def _key(self, project_id: str) -> str:
        return "agentforge:v1:memory:" + stable_project_key(project_id)

    def load(self, project_id: str, limit: int = 20) -> list[MemoryEntry]:
        """Read bounded records; underlying diagnostics never expose connection strings."""
        if limit < 1:
            raise ConfigurationError("Memory load limit must be positive")
        try:
            return [
                _decode(v, self.max_bytes)
                for v in self._get().lrange(self._key(project_id), -min(limit, self.retention), -1)
            ]
        except ConfigurationError:
            raise
        except Exception as exc:
            raise MemoryBackendError("Redis memory read failed") from exc

    def append(self, entry: MemoryEntry) -> None:
        """Atomically append and retain the newest bounded list with a transaction."""
        encoded = _encode(entry, self.max_bytes)
        try:
            with self._get().pipeline(transaction=True) as pipe:
                pipe.rpush(self._key(entry.project_id), encoded)
                pipe.ltrim(self._key(entry.project_id), -self.retention, -1)
                pipe.execute()
        except ConfigurationError:
            raise
        except Exception as exc:
            raise MemoryBackendError("Redis memory append failed") from exc

    def clear(self, project_id: str) -> None:
        """Delete only the hashed project key."""
        try:
            self._get().delete(self._key(project_id))
        except ConfigurationError:
            raise
        except Exception as exc:
            raise MemoryBackendError("Redis memory clear failed") from exc

    def close(self) -> None:
        """Release owned connections, retaining borrowed-client ownership."""
        if self._owns and self._client is not None:
            self._client.close()
            self._client = None


def build_memory_context(entries: list[MemoryEntry], task: str, token_limit: int) -> str:
    """Pack relevant/recent complete records; failure entries never establish working artifacts."""
    terms = set(task.lower().split())
    ranked = sorted(
        enumerate(entries),
        key=lambda pair: (len(terms & set(pair[1].task.lower().split())), pair[0]),
        reverse=True,
    )
    chosen: list[dict[str, Any]] = []
    for _, entry in ranked:
        record = asdict(entry)
        if not entry.success:
            record["artifacts"] = []
        candidate = json.dumps(chosen + [record], ensure_ascii=False)
        if estimate_tokens(candidate) <= token_limit:
            chosen.append(record)
    return json.dumps(chosen, ensure_ascii=False) if chosen else ""


def make_memory_entry(task: str, result: AgentResult, max_bytes: int = 262144) -> MemoryEntry:
    """Keep bounded outcome metadata and only whole artifacts; mark any omitted code."""
    task = redact_sensitive_text(task)[:512]
    summary = redact_sensitive_text(result.status + "; " + "; ".join(result.errors))[:512]
    entry = MemoryEntry(
        str(uuid4()),
        result.project_id,
        result.session_id,
        datetime.now(timezone.utc).isoformat(),
        task,
        summary,
        [],
        result.success,
    )
    kept: list[CodeArtifact] = []
    omitted = []
    for artifact in result.artifacts:
        candidate = MemoryEntry(
            entry.id,
            entry.project_id,
            entry.session_id,
            entry.created_at,
            entry.task,
            entry.summary,
            kept + [artifact],
            entry.success,
        )
        if len(json.dumps(asdict(candidate)).encode()) <= max_bytes - 128:
            kept.append(artifact)
        else:
            omitted.append(artifact.path)
    summary += ("; artifact content omitted: " + ", ".join(omitted)) if omitted else ""
    entry = MemoryEntry(
        entry.id,
        entry.project_id,
        entry.session_id,
        entry.created_at,
        task,
        summary[:512],
        kept,
        entry.success,
    )
    while len(json.dumps(asdict(entry)).encode()) > max_bytes:
        if kept:
            kept.pop()
        else:
            if not task and not summary:
                raise MemoryBackendError("Memory identity metadata exceeds entry byte limit")
            task = task[: len(task) // 2]
            summary = summary[: len(summary) // 2]
        entry = MemoryEntry(
            entry.id,
            entry.project_id,
            entry.session_id,
            entry.created_at,
            task,
            summary,
            kept,
            entry.success,
        )
    return entry
