"""Opaque return-preserving decoration and explicitly routed structured invocations."""

import inspect
import logging
from functools import wraps
from pathlib import Path
from typing import Callable
from uuid import uuid4

from .compressor import ContextCompressor
from .config import AgentConfig, derive_project_id
from .exceptions import ConfigurationError, MemoryBackendError
from .memory import LocalMemoryBackend, RedisMemoryBackend, build_memory_context, make_memory_entry
from .providers import ModelProvider, make_provider
from .router import ModelRouter, TokenLedger
from .types import AgentCallResult, AgentResult, Message, ProviderResponse
from .utils import redact_sensitive_text


class AgentCallContext:
    def __init__(self, router: ModelRouter, ledger: TokenLedger):
        """Expose only routed generation; opaque callback calls remain outside this ledger."""
        self.router, self.ledger = router, ledger

    def generate(self, messages: list[Message]) -> ProviderResponse:
        """Admit and account one controlled request without double-counting returned usage."""
        return self.router.generate(messages, self.ledger, "callback")


def optimize(
    model: str,
    *,
    structured: bool = False,
    provider: str | None = None,
    provider_instance: ModelProvider | None = None,
    fallback_provider_instance: ModelProvider | None = None,
    memory: bool = False,
    memory_backend: str = "local",
    project_id: str | None = None,
    memory_path: str | Path | None = None,
    redis_url: str | None = None,
    context_compression: bool = False,
    codebase_path: str | Path | None = None,
    token_budget: int | None = None,
    fallback_model: str | None = None,
    fallback_provider: str | None = None,
    error_loop: bool = False,
    max_retries: int = 3,
    task_decompose: bool = False,
    strict_budget: bool = False,
    model_context_limit: int | None = None,
    fallback_context_limit: int | None = None,
) -> Callable:
    """Decorate synchronous task-first callbacks; opaque mode preserves values and exceptions."""
    if not isinstance(model, str) or not model.strip():
        raise ConfigurationError("model must be nonblank")
    if task_decompose or strict_budget:
        raise ConfigurationError("Decorator decomposition/strict budgeting are unsupported in v0.1")
    if not structured and any(
        v is not None
        for v in (
            token_budget,
            fallback_model,
            fallback_provider,
            fallback_provider_instance,
            provider_instance,
        )
    ):
        raise ConfigurationError("Opaque callbacks cannot enforce budgets or automatic routing")
    if type(max_retries) is not int or max_retries < 0:
        raise ConfigurationError("Invalid retry count")
    if memory_backend not in ("local", "redis"):
        raise ConfigurationError("Invalid memory backend")
    root = Path(codebase_path) if codebase_path is not None else None
    if context_compression and (root is None or not root.is_dir()):
        raise ConfigurationError("Context needs a codebase directory")
    project = project_id or derive_project_id(root, Path.cwd())
    config = (
        AgentConfig(
            model=model,
            provider=provider,
            token_budget=50000 if token_budget is None else token_budget,
            fallback_model=fallback_model,
            fallback_provider=fallback_provider,
            model_context_limit=model_context_limit,
            fallback_context_limit=fallback_context_limit,
        )
        if structured
        else None
    )
    if config:
        config.validate_settings()

    def decorate(callback):
        if inspect.iscoroutinefunction(callback) or inspect.iscoroutinefunction(
            getattr(callback, "__call__", None)
        ):
            raise ConfigurationError("Async callbacks are not supported")
        signature = inspect.signature(callback)
        parameters = list(signature.parameters.values())
        if (
            not parameters
            or parameters[0].name != "task"
            or parameters[0].kind
            not in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ):
            raise ConfigurationError("First ordinary callback parameter must be named task")
        reserved = signature.parameters.get("agentforge_context")
        if structured and (reserved is None or reserved.kind != inspect.Parameter.KEYWORD_ONLY):
            raise ConfigurationError("Structured callback requires keyword-only agentforge_context")

        @wraps(callback)
        def wrapped(*args, **kwargs):
            if structured and "agentforge_context" in kwargs:
                raise ConfigurationError("agentforge_context is reserved for framework injection")
            bound = (
                signature.bind_partial(*args, **kwargs)
                if structured
                else signature.bind(*args, **kwargs)
            )
            task = bound.arguments.get("task")
            if not isinstance(task, str) or not task.strip():
                raise ConfigurationError("Invalid task")
            backend = None
            primary = None
            fallback = None
            if memory:
                backend = (
                    RedisMemoryBackend(redis_url)
                    if memory_backend == "redis"
                    else LocalMemoryBackend(Path(memory_path) if memory_path else None)
                )
            ledger = None
            if structured:
                assert config is not None
                ledger = TokenLedger(config.token_budget)
            context = ""
            try:
                if backend:
                    context = build_memory_context(backend.load(project), task, 4000)
                if context_compression:
                    assert root is not None
                    context += ContextCompressor(root).compress(task, 8000).text
                augmented = task + ("\nUNTRUSTED PROJECT CONTEXT:\n" + context if context else "")
                if structured:
                    assert config is not None and ledger is not None
                    primary = provider_instance or make_provider(config)
                    fallback = (
                        fallback_provider_instance or make_provider(config, fallback=True)
                        if fallback_model
                        else None
                    )
                    router = ModelRouter(config, primary, fallback)
                    bound.arguments["agentforge_context"] = AgentCallContext(router, ledger)
                for attempt in range((max_retries if error_loop else 0) + 1):
                    bound.arguments["task"] = augmented
                    try:
                        signature.bind(*bound.args, **bound.kwargs)
                        output = callback(*bound.args, **bound.kwargs)
                        break
                    except Exception as exc:
                        if attempt == (max_retries if error_loop else 0):
                            raise
                        augmented = (
                            task
                            + "\nPrevious callback exception: "
                            + redact_sensitive_text(type(exc).__name__)
                            + "\n"
                            + context
                        )
                if structured:
                    assert ledger is not None
                    if not isinstance(output, AgentCallResult):
                        raise ConfigurationError("Structured callback must return AgentCallResult")
                    returned = AgentCallResult(
                        output.output, ledger.usage, ledger.accounting_complete
                    )
                else:
                    returned = output
                if backend:
                    primitive = (
                        output
                        if type(output) in (str, int, float, bool, type(None))
                        else (
                            "<output type: "
                            + type(output).__module__
                            + "."
                            + type(output).__name__
                            + ">"
                        )
                    )
                    record = AgentResult(
                        success=True,
                        status="success",
                        session_id=str(uuid4()),
                        project_id=project,
                        errors=[redact_sensitive_text(str(primitive))[:512]],
                    )
                    try:
                        backend.append(make_memory_entry(task, record))
                    except MemoryBackendError:
                        logging.getLogger("agentforge").warning(
                            "Decorator memory persistence failed"
                        )
                return returned
            finally:
                if backend:
                    backend.close()
                if primary is not None and provider_instance is None:
                    primary.close()
                if fallback is not None and fallback_provider_instance is None:
                    fallback.close()

        return wrapped

    return decorate
