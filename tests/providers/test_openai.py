from types import SimpleNamespace as NS
from unittest.mock import Mock, create_autospec, patch

import pytest
from openai.resources.responses.input_tokens import InputTokens
from openai.resources.responses.responses import Responses

from agentforge.exceptions import ConfigurationError, ProviderError
from agentforge.providers.openai import OpenAIProvider
from agentforge.types import Message, ProviderRequest


def client():
    sdk = Mock()
    sdk.with_options.return_value = sdk
    sdk.responses = create_autospec(Responses, instance=True)
    sdk.responses.input_tokens = create_autospec(InputTokens, instance=True)
    sdk.responses.input_tokens.count.return_value = NS(input_tokens=20)
    sdk.responses.create.return_value = NS(
        output_text="code",
        status="completed",
        id="mock-request",
        usage=NS(input_tokens=20, output_tokens=30, input_tokens_details=NS(cached_tokens=10)),
    )
    return sdk


def request():
    return ProviderRequest(
        "gpt-custom", [Message("system", "rules"), Message("user", "task")], 100, 5
    )


def test_sdk_caps_messages_usage_cache_no_double_count_and_no_retry():
    sdk = client()
    provider = OpenAIProvider(client=sdk)
    assert provider.count_input_tokens(request()) == 20
    response = provider.generate(request())
    assert response.usage.total_tokens == 50 and response.usage.cached_input_tokens == 10
    payload = sdk.responses.create.call_args.kwargs
    assert payload["max_output_tokens"] == 100 and payload["store"] is False
    assert payload["input"][0] == {"role": "system", "content": "rules"}
    assert sdk.with_options.call_args_list[0].kwargs == {"max_retries": 0}


def test_lazy_key_precedence_and_missing_sdk(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "mock-environment")
    sdk = client()
    with patch("openai.OpenAI", return_value=sdk) as factory:
        provider = OpenAIProvider("mock-explicit")
        factory.assert_not_called()
        provider.generate(request())
        assert factory.call_args.kwargs["api_key"] == "mock-explicit"


def test_missing_usage_and_truncation_stay_failure_information():
    sdk = client()
    sdk.responses.create.return_value.usage = None
    response = OpenAIProvider(client=sdk).generate(request())
    assert response.usage.accounting == "unknown"
    sdk.responses.create.return_value.status = "incomplete"
    assert OpenAIProvider(client=sdk).generate(request()).finish_reason == "incomplete"


def test_auth_timeout_not_retried_and_safe():
    sdk = client()
    sdk.responses.create.side_effect = RuntimeError("sk-mocksecret123456")
    with pytest.raises(ProviderError) as caught:
        OpenAIProvider(client=sdk).generate(request())
    assert "sk-" not in str(caught.value) and sdk.responses.create.call_count == 1
    with pytest.raises(ConfigurationError):
        OpenAIProvider().generate(request())


def test_safe_request_id_and_original_cause_retained():
    sdk = client()
    error = RuntimeError("private diagnostic")
    error.request_id = "req_mock123"
    sdk.responses.create.side_effect = error
    with pytest.raises(ProviderError) as caught:
        OpenAIProvider(client=sdk).generate(request())
    assert caught.value.request_id == "req_mock123"
    assert caught.value.__cause__ is error
