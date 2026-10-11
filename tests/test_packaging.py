import builtins
import importlib
import tomllib
from pathlib import Path

from agentforge import __version__


def test_metadata_exports_marker_and_extra_consistency():
    root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((root / "pyproject.toml").read_text())
    assert metadata["project"]["version"] == __version__
    assert metadata["project"]["requires-python"] == ">=3.11"
    assert (root / "agentforge" / "py.typed").exists()
    extras = metadata["project"]["optional-dependencies"]
    assert set(extras["all"]) == set(
        extras["openai"] + extras["anthropic"] + extras["redis"] + extras["server"]
    )
    assert metadata["project"]["scripts"]["agentforge"] == "agentforge.cli:main"


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
