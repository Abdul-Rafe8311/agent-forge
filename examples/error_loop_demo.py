"""One rejected syntax candidate, one accepted repair, one shared ledger."""

import json

from agentforge import AgentWrapper, FakeProvider


def output(code):
    return json.dumps(
        {
            "artifacts": [{"path": "hello.py", "language": "python", "content": code}],
            "explanation": "OFFLINE DEMO fixture",
        }
    )


provider = FakeProvider(
    [output("def hello(:\n    pass\n"), output('def hello():\n    return "Hello!"\n')]
)
with AgentWrapper(
    "fake", provider="fake", provider_instance=provider, error_loop=True, max_retries=1
) as agent:
    result = agent.run("Create hello")
assert result.success
attempts = result.steps[0].attempts
print("attempts:", len(attempts), "tokens:", result.tokens_used)
print("first validation:", attempts[0].validation)
print(result.code)
print(*result.warnings, sep="\n")
