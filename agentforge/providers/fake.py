"""Explicit deterministic offline fixture provider."""

import json
from collections import deque
from collections.abc import Sequence

from ..exceptions import ProviderError
from ..types import ProviderCapabilities, ProviderRequest, ProviderResponse, TokenUsage
from ..utils import estimate_tokens


class FakeProvider:
    def __init__(self, responses: Sequence[ProviderResponse | Exception | str]):
        """Queue synthetic responses; strings receive deterministic synthetic usage."""
        self.responses = deque(responses)
        self.requests: list[ProviderRequest] = []
        self.count_requests: list[ProviderRequest] = []
        self.closed = False

    def capabilities(self, model: str) -> ProviderCapabilities:
        """Synthetic limits, not claims about a remote model."""
        return ProviderCapabilities(100000, 8192)

    def supports_strict_budget(self, request: ProviderRequest) -> bool:
        """The offline deterministic counting/cap contract is testable."""
        return True

    def count_input_tokens(self, request: ProviderRequest) -> int:
        """Synthetic exact count including framing, recorded for assertions."""
        self.count_requests.append(request)
        return sum(estimate_tokens(m.role + m.content) for m in request.messages)

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Pop one queued response or fail on exhaustion; strings obey simulated caps."""
        self.requests.append(request)
        if not self.responses:
            raise ProviderError("FakeProvider response queue exhausted")
        item = self.responses.popleft()
        if isinstance(item, Exception):
            raise item
        if isinstance(item, ProviderResponse):
            return item
        incoming = sum(estimate_tokens(m.role + m.content) for m in request.messages)
        outgoing = estimate_tokens(item)
        complete = outgoing <= request.max_output_tokens
        return ProviderResponse(
            item if complete else item[: max(0, request.max_output_tokens - 16)],
            TokenUsage(incoming, min(outgoing, request.max_output_tokens)),
            request.model,
            "completed" if complete else "max_tokens",
        )

    def close(self) -> None:
        """Mark synthetic ownership cleanup for tests."""
        self.closed = True


def make_demo_provider(task_decompose: bool = False, max_steps: int = 10) -> FakeProvider:
    """Build a fresh, explicitly labeled demo sequence; it does not solve arbitrary tasks."""
    steps = [
        {
            "id": "build",
            "title": "Build demo",
            "instruction": "Create greeting fixture",
            "depends_on": [],
            "kind": "execute",
        }
    ]
    if max_steps > 1:
        steps.append(
            {
                "id": "integrate",
                "title": "Integrate",
                "instruction": "Return fixture",
                "depends_on": ["build"],
                "kind": "integrate",
            }
        )
    output = json.dumps(
        {
            "artifacts": [
                {
                    "path": "hello.py",
                    "language": "python",
                    "content": 'def hello(name):\n    return f"Hello, {name}!"\n',
                }
            ],
            "explanation": "OFFLINE DEMO fixture; no real generation",
        }
    )
    return FakeProvider(
        ([json.dumps({"steps": steps})] if task_decompose else [])
        + [output] * (len(steps) if task_decompose else 1)
    )
