"""Validated local settings; remote keys are resolved lazily by provider adapters."""

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .exceptions import ConfigurationError, UnsupportedProviderError
from .utils import stable_project_key


def derive_project_id(codebase_path: Path | None, cwd: Path) -> str:
    """Hash the resolved project root; explicit IDs override this default."""
    return stable_project_key(str((codebase_path or cwd).resolve()))


def resolve_provider(model: str, provider: str | None = None) -> str:
    """Infer recognized families without changing the model ID."""
    if provider is not None:
        if provider not in ("fake", "openai", "anthropic"):
            raise UnsupportedProviderError("Use provider=fake, openai, or anthropic")
        return provider
    if model == "fake":
        return "fake"
    if model.startswith("claude-"):
        return "anthropic"
    if model.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"
    raise UnsupportedProviderError("Ambiguous model; supply provider explicitly")


def validate_redis_url(url: str | None) -> str:
    """Require Upstash TLS/TCP; REST URLs and TLS query overrides are rejected."""
    try:
        parsed = urlsplit(url or "")
        if (
            parsed.scheme != "rediss"
            or not parsed.hostname
            or not parsed.port
            or not parsed.username
            or not parsed.password
            or parse_qs(parsed.query)
        ):
            raise ValueError()
    except ValueError as exc:
        raise ConfigurationError(
            "Use the Upstash read/write rediss://username:password@host:port "
            "TCP/TLS URL, not its HTTPS REST URL/token; no query overrides"
        ) from exc
    return url or ""


@dataclass
class AgentConfig:
    model: str
    provider: str | None = None
    api_key: str | None = field(default=None, repr=False)
    memory: bool = False
    memory_backend: str = "local"
    project_id: str | None = None
    memory_path: Path | None = None
    redis_url: str | None = field(default=None, repr=False)
    task_decompose: bool = False
    max_steps: int = 10
    error_loop: bool = False
    max_retries: int = 3
    token_budget: int = 50000
    fallback_model: str | None = None
    fallback_provider: str | None = None
    fallback_threshold: float = 0.8
    context_compression: bool = False
    codebase_path: Path | None = None
    context_token_budget: int = 8000
    max_output_tokens: int = 4096
    memory_token_budget: int = 4000
    timeout_seconds: float = 60.0
    strict_budget: bool = False
    model_context_limit: int | None = None
    fallback_context_limit: int | None = None
    memory_retention_entries: int = 100
    memory_entry_max_bytes: int = 262144

    def validate_settings(self) -> None:
        """Validate without model calls, client construction, or directory creation."""
        for name in ("model", "project_id", "fallback_model"):
            value = getattr(self, name)
            if (name == "model" or value is not None) and (
                not isinstance(value, str) or not value.strip()
            ):
                raise ConfigurationError(f"{name} must be nonblank")
        for name in (
            "max_steps",
            "token_budget",
            "context_token_budget",
            "max_output_tokens",
            "memory_token_budget",
            "memory_retention_entries",
            "memory_entry_max_bytes",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ConfigurationError(f"{name} must be a positive integer")
        if self.memory_entry_max_bytes < 512:
            raise ConfigurationError("memory_entry_max_bytes must be at least 512")
        if type(self.max_retries) is not int or self.max_retries < 0:
            raise ConfigurationError("max_retries must be nonnegative")
        if (
            not math.isfinite(self.fallback_threshold)
            or not 0 < self.fallback_threshold < 1
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise ConfigurationError("Invalid threshold or timeout")
        for limit in (self.model_context_limit, self.fallback_context_limit):
            if limit is not None and (type(limit) is not int or limit < 1):
                raise ConfigurationError("Context limits must be positive integers")
        if self.provider is not None:
            resolve_provider(self.model, self.provider)
        if self.fallback_provider is not None:
            resolve_provider(self.fallback_model or "", self.fallback_provider)
        if self.memory_backend not in ("local", "redis"):
            raise ConfigurationError("memory_backend must be local or redis")
        if self.codebase_path is not None:
            self.codebase_path = Path(self.codebase_path)
        if self.memory_path is not None:
            self.memory_path = Path(self.memory_path)
        if self.context_compression and (
            self.codebase_path is None
            or not self.codebase_path.is_dir()
            or not os.access(self.codebase_path, os.R_OK)
        ):
            raise ConfigurationError("Context requires a readable codebase_path")
        if self.memory and self.memory_backend == "redis":
            self.redis_url = validate_redis_url(self.redis_url or os.environ.get("REDIS_URL"))
        self.project_id = self.project_id or derive_project_id(self.codebase_path, Path.cwd())
