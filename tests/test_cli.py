import builtins
import json
from unittest.mock import patch

from typer.testing import CliRunner

from agentforge.cli import app

runner = CliRunner()


def test_help_version_and_offline_json():
    assert runner.invoke(app, ["--help"]).exit_code == 0
    assert "0.1.0" in runner.invoke(app, ["--version"]).stdout
    result = runner.invoke(
        app, ["run", "--provider", "fake", "--model", "fake", "--task", "demo", "--json"]
    )
    assert result.exit_code == 0 and json.loads(result.stdout)["success"]
    assert "OFFLINE DEMO" in result.stderr


def test_input_budget_context_and_export_exit_codes(tmp_path):
    assert runner.invoke(app, ["run", "--model", "fake"]).exit_code == 2
    response = runner.invoke(
        app, ["run", "--model", "fake", "--task", "demo", "--json", "--token-budget", "1"]
    )
    assert response.exit_code == 3 and json.loads(response.stdout)["status"] == "budget_exceeded"
    output = tmp_path / "out"
    response = runner.invoke(
        app, ["run", "--model", "fake", "--task", "demo", "--output-dir", str(output)]
    )
    assert response.exit_code == 0 and (output / "hello.py").exists()
    response = runner.invoke(
        app, ["run", "--model", "fake", "--task", "demo", "--output-dir", str(output), "--json"]
    )
    assert response.exit_code == 5 and json.loads(response.stdout)["success"]
    assert "export failed" in response.stderr


def test_task_file_and_mutual_exclusion(tmp_path):
    task = tmp_path / "task.txt"
    task.write_text("demo")
    assert runner.invoke(app, ["run", "--model", "fake", "--task-file", str(task)]).exit_code == 0
    assert (
        runner.invoke(
            app, ["run", "--model", "fake", "--task-file", str(task), "--task", "x"]
        ).exit_code
        == 2
    )


def test_serve_token_required_and_argument_mapping_mocked(monkeypatch):
    with patch("uvicorn.run") as run:
        assert runner.invoke(app, ["serve", "--model", "fake"]).exit_code == 2
        run.assert_not_called()
        monkeypatch.setenv("AGENTFORGE_SERVER_TOKEN", "offline-test-token")
        result = runner.invoke(
            app,
            [
                "serve",
                "--provider",
                "fake",
                "--model",
                "fake",
                "--project-id",
                "demo",
                "--decompose",
                "--error-loop",
                "--port",
                "9001",
            ],
        )
        assert result.exit_code == 0, result.stderr
        assert run.call_args.kwargs == {
            "host": "127.0.0.1",
            "port": 9001,
            "workers": 1,
            "reload": False,
        }


def test_missing_server_extra_is_actionable_and_help_still_works(monkeypatch):
    original = builtins.__import__

    def no_uvicorn(name, *args, **kwargs):
        if name == "uvicorn":
            raise ImportError("mock missing extra")
        return original(name, *args, **kwargs)

    monkeypatch.setenv("AGENTFORGE_SERVER_TOKEN", "offline-test-token")
    monkeypatch.setattr(builtins, "__import__", no_uvicorn)
    assert runner.invoke(app, ["--help"]).exit_code == 0
    result = runner.invoke(app, ["serve", "--model", "fake"])
    assert result.exit_code == 2 and "agentforge-coding[server]" in result.stderr
