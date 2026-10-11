from pathlib import Path

import pytest

from agentforge.config import AgentConfig, derive_project_id, resolve_provider, validate_redis_url
from agentforge.exceptions import ConfigurationError


@pytest.mark.parametrize(
    "settings",
    [
        {"token_budget": 0},
        {"max_retries": -1},
        {"max_steps": 0},
        {"fallback_threshold": 1},
        {"model_context_limit": 0},
        {"context_compression": True},
        {"project_id": " "},
    ],
)
def test_invalid_settings(settings):
    with pytest.raises(ConfigurationError):
        AgentConfig("fake", **settings).validate_settings()


def test_derived_project_and_secret_repr(tmp_path):
    config = AgentConfig(
        "fake", api_key="mock-secret", redis_url="mock-url", codebase_path=tmp_path
    )
    config.validate_settings()
    assert config.project_id == derive_project_id(tmp_path, Path.cwd())
    assert "mock-secret" not in repr(config) and "mock-url" not in repr(config)
    assert derive_project_id(tmp_path, Path.cwd()) != derive_project_id(
        tmp_path / "other", Path.cwd()
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "redis://u:p@example.com:6379",
        "rediss://example.com:6379",
        "rediss://u:p@example.com:6379?ssl_cert_reqs=none",
    ],
)
def test_redis_requires_tls_not_rest(url):
    with pytest.raises(ConfigurationError, match="TCP/TLS"):
        validate_redis_url(url)


def test_redis_url_precedence_and_only_when_enabled(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "rediss://mock:mock@example.com:6379")
    config = AgentConfig("fake", memory=True, memory_backend="redis")
    config.validate_settings()
    assert config.redis_url.startswith("rediss:")
    config = AgentConfig("fake", memory_backend="redis", redis_url="bad")
    config.validate_settings()


def test_provider_resolution_preserves_identifiers():
    assert resolve_provider("claude-anything") == "anthropic"
    assert resolve_provider("custom", "openai") == "openai"
    with pytest.raises(ConfigurationError):
        resolve_provider("ambiguous")
