"""Shared accepted artifacts and final integration with a deterministic provider."""

import json

from agentforge import AgentWrapper, FakeProvider


def output(path, code):
    return json.dumps(
        {
            "artifacts": [{"path": path, "language": "python", "content": code}],
            "explanation": "OFFLINE DEMO fixture",
        }
    )


plan = {
    "steps": [
        {
            "id": "lib",
            "title": "Library",
            "instruction": "Write a greeting",
            "depends_on": [],
            "kind": "execute",
        },
        {
            "id": "integrate",
            "title": "Integration",
            "instruction": "Add an entry point",
            "depends_on": ["lib"],
            "kind": "integrate",
        },
    ]
}
provider = FakeProvider(
    [
        json.dumps(plan),
        output("greeting.py", 'def greet(name):\n    return "Hello, " + name\n'),
        output("main.py", 'from greeting import greet\nprint(greet("world"))\n'),
    ]
)
# Real substitution: configure provider/model/context limits; remove provider_instance.
with AgentWrapper(
    "fake", provider="fake", provider_instance=provider, task_decompose=True, max_steps=2
) as agent:
    result = agent.run("Create a greeting library and entry point")
assert result.success and len(result.artifacts) == 2
assert "greeting.py" in provider.requests[-1].messages[1].content
print(result.code)
print("steps:", result.steps_taken, "shared-ledger tokens:", result.tokens_used)
print(*result.warnings, sep="\n")
