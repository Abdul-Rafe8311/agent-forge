import builtins
import importlib
import runpy
import tomllib
from pathlib import Path

from agentforge import __version__


def test_metadata_exports_marker_and_extra_consistency():
    root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((root / "pyproject.toml").read_text())
    assert metadata["project"]["name"] == "agentforge-coding"
    assert metadata["project"]["version"] == __version__
    assert metadata["project"]["requires-python"] == ">=3.11"
    assert (root / "agentforge" / "py.typed").exists()
    extras = metadata["project"]["optional-dependencies"]
    assert set(extras["all"]) == set(
        extras["openai"] + extras["anthropic"] + extras["redis"] + extras["server"]
    )
    assert metadata["project"]["scripts"]["agentforge"] == "agentforge.cli:main"


def test_distribution_checks_select_renamed_exact_version_artifacts(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/check_distribution.py"
    find_artifacts = runpy.run_path(str(script))["find_artifacts"]
    for name in (
        "agentforge-0.1.0-py3-none-any.whl",
        "agentforge-0.1.0.tar.gz",
        "agentforge_coding-0.0.9-py3-none-any.whl",
        "agentforge_coding-0.1.0-py3-none-any.whl",
        "agentforge_coding-0.1.0.tar.gz",
    ):
        (tmp_path / name).touch()
    wheel, source = find_artifacts(tmp_path, {"name": "agentforge-coding", "version": "0.1.0"})
    assert wheel.name == "agentforge_coding-0.1.0-py3-none-any.whl"
    assert source.name == "agentforge_coding-0.1.0.tar.gz"


def test_distribution_checks_reject_ambiguous_or_missing_artifacts(tmp_path):
    import pytest

    script = Path(__file__).resolve().parents[1] / "scripts/check_distribution.py"
    find_artifacts = runpy.run_path(str(script))["find_artifacts"]
    project = {"name": "agentforge-coding", "version": "0.1.0"}
    with pytest.raises(ValueError):
        find_artifacts(tmp_path, project)
    for name in (
        "agentforge_coding-0.1.0-py3-none-any.whl",
        "agentforge_coding-0.1.0-py2.py3-none-any.whl",
        "agentforge_coding-0.1.0.tar.gz",
    ):
        (tmp_path / name).touch()
    with pytest.raises(ValueError):
        find_artifacts(tmp_path, project)


def test_root_import_without_optional_dependencies_or_filesystem_side_effects(
    monkeypatch, tmp_path
):
    original = builtins.__import__

    def without_optional(name, *args, **kwargs):
        if name.split(".")[0] in ("openai", "anthropic", "redis", "fastapi", "uvicorn"):
            raise ImportError("offline optional dependency missing")
        return original(name, *args, **kwargs)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(builtins, "__import__", without_optional)
    import agentforge

    importlib.reload(agentforge)
    assert not list(tmp_path.iterdir())
    assert agentforge.AgentWrapper("fake").run("demo").success


def test_missing_sdk_and_redis_errors_use_distribution_name(monkeypatch):
    import pytest

    from agentforge.exceptions import ConfigurationError
    from agentforge.memory import RedisMemoryBackend
    from agentforge.providers.anthropic import AnthropicProvider
    from agentforge.providers.openai import OpenAIProvider
    from agentforge.types import Message, ProviderRequest

    original = builtins.__import__

    def without_optional(name, *args, **kwargs):
        if name in ("openai", "anthropic", "redis"):
            raise ImportError("mocked missing extra")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_optional)
    request = ProviderRequest("mock-model", [Message("user", "demo")], 100)
    for provider, extra in (
        (OpenAIProvider("mock-placeholder"), "openai"),
        (AnthropicProvider("mock-placeholder"), "anthropic"),
    ):
        with pytest.raises(ConfigurationError) as caught:
            provider.generate(request)
        assert f"agentforge-coding[{extra}]" in str(caught.value)
    with pytest.raises(ConfigurationError) as caught:
        RedisMemoryBackend("rediss://mock:placeholder@localhost:6380").load("demo")
    assert "agentforge-coding[redis]" in str(caught.value)
