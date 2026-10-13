import pytest

from agentforge.assist.sessions import start, update_requirements


@pytest.fixture
def session(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.py").write_text("def answer():\n    return 42\n")
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Implement answer behavior.\n\nPreserve existing interfaces.\n")
    session = start(project, prompt)
    with session.transaction() as state:
        values = state["requirements"]
        for req in values:
            req["clarification_status"] = "resolved"
        values[-1]["scope"] = "all_tasks"
        values[-1]["category"] = "shared_constraint"
        update_requirements(session, state, values)
        state["plan"]["tasks"][0]["relevant_files"] = [
            {"path": "app.py", "reason": "implementation"}
        ]
        state["plan"]["tasks"][0]["context_queries"] = ["answer"]
    return session
