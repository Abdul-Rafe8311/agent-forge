import pytest
from conftest import generation

from agentforge.config import AgentConfig
from agentforge.exceptions import BudgetExceededError, ConfigurationError, ProviderError
from agentforge.providers.fake import FakeProvider
from agentforge.router import ModelRouter, TokenLedger
from agentforge.types import Message, ProviderCapabilities, ProviderResponse, TokenUsage


def test_ledger_reserve_commit_release_unknown_and_duplicate():
    ledger = TokenLedger(100)
    first = ledger.reserve(20, 30)
    assert ledger.remaining == 50
    ledger.commit(first, TokenUsage(10, 10))
    assert ledger.used == 20 and ledger.remaining == 80
    with pytest.raises(KeyError):
        ledger.commit(first, TokenUsage(0, 0))
    other = ledger.reserve(10, 10)
    ledger.release(other)
    unknown = ledger.reserve(10, 20)
    ledger.charge_unknown(unknown)
    assert ledger.used == 50 and not ledger.accounting_complete
    assert ledger.usage.accounting == "unknown"


def test_overspend_is_recorded_and_future_calls_refused():
    ledger = TokenLedger(100)
    key = ledger.reserve(10, 10)
    with pytest.raises(BudgetExceededError):
        ledger.commit(key, TokenUsage(30, 20))
    assert ledger.used == 50 and ledger.violated
    with pytest.raises(BudgetExceededError):
        ledger.reserve(1, 1)


def test_budget_preflight_and_output_clamp():
    provider = FakeProvider([generation()])
    ledger = TokenLedger(100)
    router = ModelRouter(AgentConfig("fake"), provider)
    response = router.generate([Message("user", "short")], ledger, "execute")
    assert provider.requests[0].max_output_tokens == 100 - len("usershort") - 16
    assert response.finish_reason == "max_tokens" and ledger.used == 100
    with pytest.raises(BudgetExceededError):
        router.generate([Message("user", "x")], ledger, "again")


def test_unknown_remote_failure_charges_full_reservation_once():
    provider = FakeProvider([ProviderError("Mock timeout")])
    ledger = TokenLedger(200)
    with pytest.raises(ProviderError):
        ModelRouter(AgentConfig("fake"), provider).generate(
            [Message("user", "x")], ledger, "execute"
        )
    assert ledger.used == 200 and ledger.usage.accounting == "unknown"
    assert len(provider.requests) == 1


def test_preflight_count_failure_does_not_charge_generation():
    class BadCount(FakeProvider):
        def count_input_tokens(self, request):
            raise ProviderError("Mock count error")

    provider = BadCount([generation()])
    ledger = TokenLedger(1000)
    with pytest.raises(ProviderError):
        ModelRouter(AgentConfig("fake"), provider).generate(
            [Message("user", "x")], ledger, "execute"
        )
    assert ledger.used == 0 and not provider.requests


def test_unknown_context_and_unsupported_strict_fail_before_calls():
    class Unknown(FakeProvider):
        def capabilities(self, model):
            return ProviderCapabilities()

        def supports_strict_budget(self, request):
            return False

    provider = Unknown([generation()])
    with pytest.raises(ConfigurationError, match="model_context_limit"):
        ModelRouter(AgentConfig("fake"), provider)
    router = ModelRouter(
        AgentConfig("fake", model_context_limit=10000, strict_budget=True), provider
    )
    with pytest.raises(ConfigurationError, match="strict_budget"):
        router.generate([Message("user", "x")], TokenLedger(1000), "execute")
    assert not provider.requests and not provider.count_requests


def test_fallback_keeps_shared_ledger():
    primary = FakeProvider([generation()])
    fallback = FakeProvider([generation()])
    router = ModelRouter(
        AgentConfig("fake", fallback_model="cheaper", fallback_threshold=0.1), primary, fallback
    )
    ledger = TokenLedger(1000)
    router.generate([Message("user", "x")], ledger, "one")
    before = ledger.used
    router.generate([Message("user", "x")], ledger, "two")
    assert ledger.used > before and fallback.requests[0].model == "cheaper"


def test_missing_usage_is_unknown_never_zero():
    provider = FakeProvider([ProviderResponse("x", TokenUsage(0, 0, accounting="unknown"), "fake")])
    ledger = TokenLedger(200)
    with pytest.raises(ProviderError):
        ModelRouter(AgentConfig("fake"), provider).generate(
            [Message("user", "x")], ledger, "execute"
        )
    assert ledger.used == 200 and not ledger.accounting_complete


def test_optional_context_drops_but_required_artifacts_remain():
    import json

    from agentforge.exceptions import ContextLimitExceededError

    provider = FakeProvider([generation()])
    config = AgentConfig("fake", model_context_limit=600, max_output_tokens=200)
    router = ModelRouter(config, provider)
    router.generate(
        [
            Message(
                "user",
                json.dumps(
                    {
                        "optional_context": "x" * 1000,
                        "accepted_artifacts": [{"path": "a.py", "content": "answer=42"}],
                    }
                ),
            )
        ],
        TokenLedger(5000),
        "execute",
    )
    payload = json.loads(provider.requests[0].messages[0].content)
    assert payload["optional_context"] == ""
    assert payload["accepted_artifacts"][0]["content"] == "answer=42"
    with pytest.raises(ContextLimitExceededError):
        router.generate(
            [
                Message(
                    "user",
                    json.dumps(
                        {
                            "optional_context": "optional",
                            "accepted_artifacts": [{"content": "required" * 1000}],
                        }
                    ),
                )
            ],
            TokenLedger(50000),
            "execute",
        )
    assert len(provider.requests) == 1


def test_reported_overspend_stops_run_even_with_usable_code():
    from agentforge import AgentWrapper

    provider = FakeProvider([ProviderResponse(generation(), TokenUsage(500, 100), "fake")])
    result = AgentWrapper("fake", provider_instance=provider, max_output_tokens=50).run("x")
    assert result.status == "budget_exceeded" and not result.success
    assert result.tokens_used == 600 and not result.artifacts
