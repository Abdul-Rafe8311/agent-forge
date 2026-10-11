"""AgentForge public API; importing it creates no SDK clients or storage."""

__version__ = "0.1.0"
from .core import AgentWrapper
from .decorators import AgentCallContext, optimize
from .providers import AnthropicProvider, FakeProvider, OpenAIProvider, make_demo_provider
from .types import AgentCallResult, AgentResult, Message

__all__ = [
    "AgentWrapper",
    "optimize",
    "AgentResult",
    "AgentCallResult",
    "AgentCallContext",
    "Message",
    "FakeProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "make_demo_provider",
    "__version__",
]
