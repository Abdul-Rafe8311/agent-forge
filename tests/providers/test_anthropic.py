from types import SimpleNamespace as NS
from unittest.mock import Mock, create_autospec

from anthropic.resources.messages.messages import Messages

from agentforge.providers.anthropic import AnthropicProvider
from agentforge.types import Message, ProviderRequest


def test_sdk_system_cache_usage_and_stop_reason():
    sdk = Mock()
    sdk.with_options.return_value = sdk
    sdk.messages = create_autospec(Messages, instance=True)
    sdk.messages.count_tokens.return_value = NS(input_tokens=25)
    sdk.messages.create.return_value = NS(
        content=[NS(type="thinking", thinking="hidden"), NS(type="text", text="code")],
        stop_reason="end_turn",
        usage=NS(
            input_tokens=10,
            output_tokens=30,
            cache_read_input_tokens=10,
            cache_creation_input_tokens=5,
        ),
        id="mock",
    )
    provider = AnthropicProvider(client=sdk)
    req = ProviderRequest(
        "claude-custom", [Message("system", "rules"), Message("user", "task")], 100
    )
    assert provider.count_input_tokens(req) == 25
    response = provider.generate(req)
    assert response.text == "code" and response.usage.total_tokens == 55
    assert response.usage.cached_input_tokens == 10
    payload = sdk.messages.create.call_args.kwargs
    assert payload["system"] == "rules" and payload["messages"] == [
        {"role": "user", "content": "task"}
    ]
    assert payload["max_tokens"] == 100 and "temperature" not in payload
