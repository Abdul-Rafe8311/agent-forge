import inspect

import pytest
from conftest import generation

from agentforge import AgentCallResult, Message, optimize
from agentforge.exceptions import ConfigurationError
from agentforge.providers.fake import FakeProvider


def test_opaque_preserves_signature_args_kwargs_identity_and_return():
    value = object()
    seen = []

    @optimize("custom")
    def callback(task: str, number=1, *, option="x"):
        seen.append((task, number, option))
        return value

    assert callback(task="build", number=2, option="z") is value
    assert seen == [("build", 2, "z")]
    assert str(inspect.signature(callback)) == "(task: str, number=1, *, option='x')"
    assert callback.__name__ == "callback"


def test_opaque_preserves_exception_and_retries_only_when_enabled():
    error = RuntimeError("fixture")
    calls = []

    @optimize("custom", error_loop=True, max_retries=1)
    def callback(task):
        calls.append(task)
        raise error

    with pytest.raises(RuntimeError) as caught:
        callback("build")
    assert caught.value is error and len(calls) == 2


@pytest.mark.parametrize(
    "options",
    [
        {"token_budget": 1},
        {"fallback_model": "fake"},
        {"task_decompose": True},
        {"strict_budget": True},
    ],
)
def test_opaque_unsupported_controls_fail_before_callback(options):
    with pytest.raises(ConfigurationError):
        optimize("custom", **options)


def test_async_rejected():
    async def callback(task):
        return task

    with pytest.raises(ConfigurationError):
        optimize("custom")(callback)


def test_structured_aggregates_multicall_once_preserves_output_and_ignores_advisory_usage():
    provider = FakeProvider([generation(), generation()])
    output = object()

    @optimize("fake", structured=True, provider_instance=provider)
    def callback(task, *, agentforge_context):
        response = agentforge_context.generate([Message("user", task)])
        agentforge_context.generate([Message("user", "second")])
        return AgentCallResult(output, response.usage)

    result = callback(task="first")
    assert result.output is output and result.accounting_complete
    assert result.usage.total_tokens > provider.requests[0].max_output_tokens / 100
    assert len(provider.requests) == 2 and not provider.closed
    with pytest.raises(ConfigurationError):
        callback("x", agentforge_context=object())


def test_structured_bad_return_and_reserved_signature():
    with pytest.raises(ConfigurationError):
        optimize("fake", structured=True)(lambda task: task)

    @optimize("fake", structured=True, provider_instance=FakeProvider([generation()]))
    def bad(task, *, agentforge_context):
        agentforge_context.generate([Message("user", task)])
        return "bad"

    with pytest.raises(ConfigurationError, match="AgentCallResult"):
        bad("x")
