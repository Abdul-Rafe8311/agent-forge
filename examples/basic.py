"""Base-install offline example: fixture generation without credentials or network."""

from agentforge import AgentWrapper

with AgentWrapper("fake", provider="fake") as agent:
    result = agent.run("Create a greeting module")
print(result.code)
print("status:", result.status, "steps:", result.steps_taken, "tokens:", result.tokens_used)
print(*result.warnings, sep="\n")
