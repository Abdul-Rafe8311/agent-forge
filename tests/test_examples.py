import runpy
from pathlib import Path

import pytest

from agentforge.exceptions import ConfigurationError


@pytest.mark.parametrize(
    "name", ["basic", "decorator_demo", "multi_step_project", "error_loop_demo"]
)
def test_offline_example(name, capsys):
    runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "examples" / f"{name}.py"), run_name="__main__"
    )
    assert "OFFLINE DEMO" in capsys.readouterr().out


@pytest.mark.parametrize("name", ["with_openai", "with_claude"])
def test_real_example_requires_explicit_setup(name):
    with pytest.raises(ConfigurationError, match="privately"):
        runpy.run_path(
            str(Path(__file__).resolve().parents[1] / "examples" / f"{name}.py"),
            run_name="__main__",
        )
