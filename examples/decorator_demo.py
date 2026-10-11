"""Opaque return preservation and separately controlled structured calls."""

from agentforge import AgentCallContext, AgentCallResult, FakeProvider, Message, optimize


@optimize(model="metadata-only")
def opaque(task: str, suffix: str = "!"):
    return {"task": task, "suffix": suffix}


print("Opaque pass-through (no routing or token enforcement):", opaque(task="hello"))


@optimize(
    model="fake",
    provider="fake",
    structured=True,
    provider_instance=FakeProvider(["fixture answer"]),
    token_budget=1000,
)
def structured(task: str, *, agentforge_context: AgentCallContext) -> AgentCallResult:
    response = agentforge_context.generate([Message("user", task)])
    return AgentCallResult(response.text, response.usage)


result = structured("hello")
print("OFFLINE DEMO routed output:", result.output, "usage:", result.usage)
