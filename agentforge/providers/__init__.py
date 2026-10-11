"""Public adapter factories preserve model IDs and import SDKs only on dispatch."""

from ..config import AgentConfig, resolve_provider
from .anthropic import AnthropicProvider
from .base import ModelProvider
from .fake import FakeProvider, make_demo_provider
from .openai import OpenAIProvider


def make_provider(config: AgentConfig, *, fallback: bool = False) -> ModelProvider:
    """Construct an adapter without connecting; cross-provider fallback gets its own key."""
    model = config.fallback_model if fallback else config.model
    kind = resolve_provider(model or "", config.fallback_provider if fallback else config.provider)
    if kind == "fake":
        return make_demo_provider(config.task_decompose, config.max_steps)
    key = None if fallback else config.api_key
    return OpenAIProvider(key) if kind == "openai" else AnthropicProvider(key)


__all__ = [
    "ModelProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "FakeProvider",
    "make_demo_provider",
]
