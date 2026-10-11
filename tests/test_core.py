import pytest
from conftest import generation, plan

from agentforge import AgentWrapper
from agentforge.exceptions import MemoryBackendError, RunStateError
from agentforge.providers.fake import FakeProvider
from agentforge.types import ValidationIssue, ValidationResult


def test_single_run_contract_and_borrowed_cleanup():
    provider = FakeProvider([generation(), generation()])
    wrapper = AgentWrapper("fake", provider_instance=provider)
    first = wrapper.run("first")
    second = wrapper.run("first")
    assert first.success and first.status == "success" and first.steps_taken == 1
    assert first.code == first.artifacts[0].content
    assert first.tokens_used == first.token_usage.total_tokens
    assert first.session_id != second.session_id and first.project_id == second.project_id
    assert first.tokens_used == second.tokens_used
    wrapper.close()
    assert not provider.closed


def test_planning_execution_repair_integration_share_ledger():
    provider = FakeProvider(
        [plan(), generation("def broken(:\n"), generation(), generation("answer=43\n")]
    )
    result = AgentWrapper(
        "fake", provider_instance=provider, task_decompose=True, error_loop=True, max_retries=1
    ).run("build")
    assert result.success and result.steps_taken == 2
    assert len(provider.requests) == 4 and len(result.steps[0].attempts) == 2
    total = sum(r.usage.total_tokens for r in result.steps[0].attempts + result.steps[1].attempts)
    assert result.tokens_used > total
    assert "def broken" in provider.requests[2].messages[-1].content


@pytest.mark.parametrize("retries", [0, 1, 3])
def test_validation_attempt_bound_and_partial_state(retries):
    provider = FakeProvider([generation("def broken(:")] * 4)
    result = AgentWrapper(
        "fake", provider_instance=provider, error_loop=True, max_retries=retries
    ).run("build")
    assert result.status == "validation_failed" and not result.success
    assert len(provider.requests) == retries + 1 and result.steps_taken == 1
    assert result.artifacts == []


def test_planning_failed_repairs_at_most_once():
    provider = FakeProvider(["bad", "bad", generation()])
    result = AgentWrapper(
        "fake", provider_instance=provider, task_decompose=True, error_loop=True, max_retries=3
    ).run("build")
    assert result.status == "planning_failed" and len(provider.requests) == 2


def test_semantic_combined_validation_repairs_without_losing_accepted_files():
    class Contract:
        def validate(self, artifacts):
            files = {a.path: a.content for a in artifacts}
            passed = "use.py" not in files or "answer" in files["app.py"]
            return ValidationResult(
                passed, [] if passed else [ValidationIssue("contract", "Missing answer")]
            )

    provider = FakeProvider([plan(), generation(), generation("import app\n", "use.py")])
    result = AgentWrapper(
        "fake", provider_instance=provider, task_decompose=True, validator=Contract()
    ).run("build")
    assert result.success and len(result.artifacts) == 2
    provider = FakeProvider(
        [plan(), generation(), generation("bad_name=1"), generation("answer=44")]
    )

    class Required:
        def validate(self, artifacts):
            passed = "answer" in artifacts[0].content
            return ValidationResult(
                passed, [] if passed else [ValidationIssue("contract", "Required answer")]
            )

    result = AgentWrapper(
        "fake",
        provider_instance=provider,
        task_decompose=True,
        error_loop=True,
        max_retries=1,
        validator=Required(),
    ).run("build")
    assert result.success and "answer=44" in result.code


def test_memory_read_stops_generation_write_failure_preserves_success():
    class Memory:
        def load(self, *args):
            raise MemoryBackendError("Read failed")

        def append(self, entry):
            raise MemoryBackendError("Write failed")

        def close(self):
            pass

    provider = FakeProvider([generation()])
    result = AgentWrapper(
        "fake", provider_instance=provider, memory=True, memory_instance=Memory()
    ).run("x")
    assert result.status == "memory_error" and not provider.requests

    class WriteFailure(Memory):
        def load(self, *args):
            return []

    result = AgentWrapper(
        "fake", provider_instance=provider, memory=True, memory_instance=WriteFailure()
    ).run("x")
    assert result.success and any("persistence" in w for w in result.warnings)


def test_run_budget_and_context_stop_are_results():
    assert AgentWrapper("fake", token_budget=1).run("x").status == "budget_exceeded"
    assert (
        AgentWrapper("fake", model_context_limit=20).run("required task").status
        == "context_limit_exceeded"
    )


def test_wrapper_non_reentrant_and_closed():
    wrapper = AgentWrapper("fake")
    wrapper._lock.acquire()
    with pytest.raises(RunStateError):
        wrapper.run("x")
    wrapper._lock.release()
    wrapper.close()
    with pytest.raises(RunStateError):
        wrapper.run("x")


def test_decompose_one_step_works():
    result = AgentWrapper("fake", task_decompose=True, max_steps=1).run("x")
    assert result.success and result.steps_taken == 1


def test_later_failure_keeps_previous_accepted_files():
    provider = FakeProvider([plan(), generation(), generation("def bad(:", "new.py")])
    result = AgentWrapper("fake", provider_instance=provider, task_decompose=True).run("build")
    assert result.status == "validation_failed" and result.steps_taken == 2
    assert [a.path for a in result.artifacts] == ["app.py"]
    assert result.steps[-1].artifacts == []


def test_persistence_remains_inside_non_reentrant_run():
    class Memory:
        def load(self, *args):
            return []

        def append(self, entry):
            with pytest.raises(RunStateError):
                wrapper.run("overlap")

        def close(self):
            pass

    wrapper = AgentWrapper("fake", memory=True, memory_instance=Memory())
    assert wrapper.run("x").success
