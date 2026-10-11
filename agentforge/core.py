"""Synchronous orchestration, with expected failures preserved as typed results."""

import threading
from pathlib import Path
from uuid import uuid4

from .artifacts import merge_artifacts, render_code
from .compressor import ContextCompressor
from .config import AgentConfig
from .decomposer import TaskDecomposer
from .exceptions import (
    BudgetExceededError,
    ConfigurationError,
    ContextLimitExceededError,
    MemoryBackendError,
    PlanningFailedError,
    ProviderError,
    RunStateError,
)
from .memory import (
    LocalMemoryBackend,
    MemoryBackend,
    RedisMemoryBackend,
    build_memory_context,
    make_memory_entry,
)
from .providers import ModelProvider, make_provider
from .router import ModelRouter, TokenLedger
from .types import AgentResult, Step, TaskPlan
from .utils import redact_sensitive_text
from .validator import PythonSyntaxValidator, RepairLoop, Validator


class AgentWrapper:
    def __init__(
        self,
        model: str,
        *,
        provider: str | None = None,
        api_key: str | None = None,
        memory: bool = False,
        memory_backend: str = "local",
        project_id: str | None = None,
        task_decompose: bool = False,
        max_steps: int = 10,
        error_loop: bool = False,
        max_retries: int = 3,
        token_budget: int = 50000,
        fallback_model: str | None = None,
        context_compression: bool = False,
        codebase_path: str | Path | None = None,
        provider_instance: ModelProvider | None = None,
        fallback_provider_instance: ModelProvider | None = None,
        memory_instance: MemoryBackend | None = None,
        validator: Validator | None = None,
        memory_path: str | Path | None = None,
        redis_url: str | None = None,
        fallback_provider: str | None = None,
        fallback_threshold: float = 0.8,
        context_token_budget: int = 8000,
        memory_token_budget: int = 4000,
        max_output_tokens: int = 4096,
        timeout_seconds: float = 60,
        strict_budget: bool = False,
        model_context_limit: int | None = None,
        fallback_context_limit: int | None = None,
        memory_retention_entries: int = 100,
        memory_entry_max_bytes: int = 262144,
    ):
        """Validate settings and retain lazy adapters without remote requests."""
        settings = {
            k: v
            for k, v in locals().items()
            if k
            not in (
                "self",
                "provider_instance",
                "fallback_provider_instance",
                "memory_instance",
                "validator",
            )
        }
        self.config = AgentConfig(**settings)
        self.config.validate_settings()
        self.primary = provider_instance or make_provider(self.config)
        self.fallback = (
            fallback_provider_instance or make_provider(self.config, fallback=True)
            if fallback_model
            else None
        )
        self._owned_primary = provider_instance is None
        self._owned_fallback = fallback_provider_instance is None
        ModelRouter(self.config, self.primary, self.fallback)
        self.backend = memory_instance
        self._owned_memory = memory_instance is None
        if memory and self.backend is None:
            if memory_backend == "redis":
                self.backend = RedisMemoryBackend(
                    self.config.redis_url,
                    retention=memory_retention_entries,
                    max_bytes=memory_entry_max_bytes,
                )
            else:
                self.backend = LocalMemoryBackend(
                    self.config.memory_path,
                    retention=memory_retention_entries,
                    max_bytes=memory_entry_max_bytes,
                )
        self.validator = validator or PythonSyntaxValidator()
        self._lock = threading.Lock()
        self._closed = False
        self.last_result: AgentResult | None = None

    def run(self, task: str) -> AgentResult:
        """Execute one run without writing artifacts; expected failures return partial results."""
        if not isinstance(task, str) or not task.strip():
            raise ConfigurationError("task must be a nonblank string")
        if self._closed or not self._lock.acquire(blocking=False):
            raise RunStateError("Wrapper is closed or already running")
        try:
            return self._run(task)
        finally:
            self._lock.release()

    def _run(self, task: str) -> AgentResult:
        ledger = TokenLedger(self.config.token_budget)
        router = ModelRouter(self.config, self.primary, self.fallback)
        result = AgentResult(session_id=str(uuid4()), project_id=self.config.project_id or "")
        self.last_result = result
        try:
            context = ""
            if self.config.memory and self.backend:
                try:
                    context = build_memory_context(
                        self.backend.load(result.project_id), task, self.config.memory_token_budget
                    )
                except MemoryBackendError as exc:
                    result.status = "memory_error"
                    result.errors.append(str(exc))
                    return self._finish(result, ledger, router)
            if self.config.context_compression:
                assert self.config.codebase_path is not None
                context += (
                    ContextCompressor(self.config.codebase_path)
                    .compress(task, self.config.context_token_budget)
                    .text
                )
            plan = (
                TaskDecomposer(router, self.config.max_steps).decompose(task, context, ledger)
                if self.config.task_decompose
                else TaskPlan([Step("task", "Execute task", task)])
            )
            for step in plan.steps:
                executed = RepairLoop().execute(
                    task,
                    step,
                    context,
                    result.artifacts,
                    router,
                    ledger,
                    self.validator,
                    self.config.max_retries if self.config.error_loop else 0,
                )
                result.steps.append(executed)
                if executed.status != "success":
                    result.status = executed.error_kind or "validation_failed"
                    result.errors.extend(a.error for a in executed.attempts if a.error)
                    if executed.attempts[-1].validation:
                        result.errors.extend(
                            i.message for i in executed.attempts[-1].validation.issues
                        )
                    break
                result.artifacts = merge_artifacts(result.artifacts, executed.artifacts)
        except (
            PlanningFailedError,
            BudgetExceededError,
            ProviderError,
            ContextLimitExceededError,
        ) as exc:
            result.status = (
                "planning_failed"
                if isinstance(exc, PlanningFailedError)
                else "budget_exceeded"
                if isinstance(exc, BudgetExceededError)
                else "context_limit_exceeded"
                if isinstance(exc, ContextLimitExceededError)
                else "provider_error"
            )
            result.errors.append(redact_sensitive_text(str(exc)))
        self._finish(result, ledger, router)
        if self.config.memory and self.backend:
            try:
                self.backend.append(
                    make_memory_entry(task, result, self.config.memory_entry_max_bytes)
                )
            except MemoryBackendError:
                result.warnings.append("Computation finished but memory persistence failed")
        return result

    def _finish(self, result, ledger, router):
        result.code = render_code(result.artifacts)
        result.steps_taken = len(result.steps)
        result.token_usage = ledger.usage
        result.tokens_used = ledger.used
        result.accounting_complete = ledger.accounting_complete
        result.models_used = list(dict.fromkeys(r.model for r in router.records))
        result.success = result.status == "success"
        if self.config.provider == "fake" or self.config.model == "fake":
            result.warnings.append("OFFLINE DEMO: fixture output, not real AI generation")
        return result

    def close(self) -> None:
        """Release owned resources; injected resources retain caller ownership."""
        if not self._lock.acquire(blocking=False):
            raise RunStateError("Cannot close an active wrapper")
        try:
            if self._closed:
                return
            if self._owned_primary:
                self.primary.close()
            if self.fallback and self._owned_fallback:
                self.fallback.close()
            if self.backend and self._owned_memory:
                self.backend.close()
            self._closed = True
        finally:
            self._lock.release()

    def __enter__(self) -> "AgentWrapper":
        """Use owned resource cleanup at context-manager exit."""
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """Close owned resources without changing a prior result."""
        self.close()
