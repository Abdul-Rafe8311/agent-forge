import json
from pathlib import Path

from typer.testing import CliRunner

from agentforge.assist.sessions import Session
from agentforge.cli import app

runner = CliRunner()


def invoke(arguments, expected=0):
    result = runner.invoke(app, arguments)
    assert result.exit_code == expected, result.output
    value = json.loads(result.stdout)
    assert len(result.stdout.encode()) == value["output_bytes"]
    return value


def test_actual_cli_start_review_prepare_validate_complete(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.py").write_text("answer=42")
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Implement answer behavior.")
    base = ["assist", "--project", str(project)]
    started = invoke(base + ["start", "--prompt-file", str(prompt)])
    session_id = started["session"]
    args = base + ["--session", session_id]
    reviewed = invoke(args + ["requirements", "--reviewed"])
    assert "requirements" not in reviewed and reviewed["requirements_updated"] > 0
    checks_file = tmp_path / "checks.json"
    checks_file.write_text(json.dumps([{"id": "syntax", "kind": "syntax"}]))
    catalog = invoke(args + ["checks", "--file", str(checks_file)])
    assert catalog["checks_registered"] == 1 and "checks" not in catalog
    assert invoke(args + ["checks"])["checks"][0]["id"] == "syntax"
    plan = invoke(args + ["plan-check"])["plan"]
    plan["tasks"][0]["relevant_files"] = [{"path": "app.py"}]
    plan["tasks"][0]["context_queries"] = ["answer"]
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan))
    installed = invoke(args + ["plan-check", "--plan-file", str(plan_file)])
    assert "plan" not in installed and installed["ordered_task_ids"] == ["task"]
    packet = invoke(args + ["prepare"])
    assert packet["code"]["chunks"]
    invoke(args + ["validate"])
    completion = {
        "spec_hash": reviewed["spec_hash"],
        "plan_version": installed["plan_version"],
        "summary": "answer verified",
        "changed_files": ["app.py"],
    }
    file = tmp_path / "completion.json"
    file.write_text(json.dumps(completion))
    saved = invoke(args + ["complete", "--summary-file", str(file)])
    assert saved["handoff_saved"] and "handoff" not in saved
    assert (
        invoke(args + ["complete", "--show"])["completion"]["handoff"]["summary"]
        == "answer verified"
    )
    invoke(args + ["final-check"], expected=1)
    assert (
        invoke(args + ["final-check", "--review-original", "--note", "Checked original"])["status"]
        == "accepted"
    )
    events = Session(project, session_id).path / "helper-events.jsonl"
    assert len(events.read_text().splitlines()) >= 8


def test_schema_and_invalid_json_never_echo_secrets(tmp_path):
    assert "tasks" in invoke(["assist", "schema", "--kind", "plan"])["schema"]["properties"]
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Implement answer.")
    started = invoke(["assist", "--project", str(tmp_path), "start", "--prompt-file", str(prompt)])
    bad = tmp_path / "bad.json"
    bad.write_text('{"private-secret": invalid}')
    value = invoke(
        [
            "assist",
            "--project",
            str(tmp_path),
            "--session",
            started["session"],
            "plan-check",
            "--plan-file",
            str(bad),
        ],
        expected=2,
    )
    assert "private-secret" not in str(value)
    session = Session(tmp_path, started["session"])
    events = [
        json.loads(line) for line in (session.path / "helper-events.jsonl").read_text().splitlines()
    ]
    assert events[-1]["status"] == "error"
    assert "private-secret" not in str(events)


def test_schema_error_names_safe_fields_without_input_values(tmp_path):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Implement answer.")
    started = invoke(["assist", "--project", str(tmp_path), "start", "--prompt-file", str(prompt)])
    args = ["assist", "--project", str(tmp_path), "--session", started["session"]]
    plan = invoke(args + ["plan-check"])["plan"]
    plan["tasks"][0]["objective"] = 123
    plan["tasks"][0]["private-secret-field"] = "PRIVATE_VALUE"
    path = tmp_path / "bad-plan.json"
    path.write_text(json.dumps(plan))
    result = invoke(args + ["plan-check", "--plan-file", str(path)], expected=2)
    assert result["code"] == "invalid_schema"
    assert ["tasks", 0, "objective"] in [issue["field"] for issue in result["validation_issues"]]
    assert "PRIVATE_VALUE" not in str(result) and "private-secret-field" not in str(result)


def test_packaged_skill_install_idempotent_preserves_customizations(tmp_path):
    destination = tmp_path / "skill"
    args = ["assist", "install-skill", "--destination", str(destination)]
    invoke(args)
    invoke(args)
    assert (destination / "SKILL.md").is_file()
    (destination / "SKILL.md").write_text("custom")
    invoke(args, expected=2)
    assert (destination / "SKILL.md").read_text() == "custom"
    source = Path(__file__).resolve().parents[2] / "agentforge/assist/skill"
    for path in source.rglob("*"):
        if path.is_file():
            mirrored = (
                source.parents[2] / ".agents/skills/agentforge-coding" / path.relative_to(source)
            )
            assert mirrored.read_bytes() == path.read_bytes()


def test_explicit_skill_upgrade_preserves_unrelated_files_and_rejects_symlink(tmp_path):
    destination = tmp_path / "skill"
    args = ["assist", "install-skill", "--destination", str(destination)]
    invoke(args)
    (destination / "SKILL.md").write_text("previous package version")
    (destination / "custom.txt").write_text("unrelated extension")
    invoke(args + ["--replace-existing"])
    assert (destination / "custom.txt").read_text() == "unrelated extension"
    assert "previous package version" not in (destination / "SKILL.md").read_text()
    (destination / "references/workflow.md").unlink()
    (destination / "references/workflow.md").symlink_to(tmp_path / "outside.md")
    invoke(args + ["--replace-existing"], expected=2)
    assert not (tmp_path / "outside.md").exists()


def test_existing_cli_commands_preserved():
    assert (
        runner.invoke(
            app, ["run", "--provider", "fake", "--model", "fake", "--task", "fixture", "--json"]
        ).exit_code
        == 0
    )
    assert runner.invoke(app, ["serve", "--help"]).exit_code == 0
