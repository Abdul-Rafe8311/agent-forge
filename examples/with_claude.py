"""Opt-in real integration; run only after authorizing remote calls. Install .[anthropic]."""

import os

from agentforge import AgentWrapper
from agentforge.exceptions import ConfigurationError


def main():
    """Require explicit user setup; this example was verified with mocks only."""
    required = ("ANTHROPIC_API_KEY", "AGENTFORGE_MODEL", "AGENTFORGE_CONTEXT_LIMIT")
    if any(not os.environ.get(name) for name in required):
        raise ConfigurationError(
            "Set ANTHROPIC_API_KEY, AGENTFORGE_MODEL and AGENTFORGE_CONTEXT_LIMIT "
            "privately; install .[anthropic]"
        )
    print("Live API integration has not been tested during this build.")
    with AgentWrapper(
        os.environ["AGENTFORGE_MODEL"],
        provider="anthropic",
        model_context_limit=int(os.environ["AGENTFORGE_CONTEXT_LIMIT"]),
        error_loop=True,
    ) as agent:
        result = agent.run("Create a Python greeting module")
    print(result.to_dict())


if __name__ == "__main__":
    main()
