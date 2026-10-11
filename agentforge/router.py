"""One synchronized run ledger for planning, repair, execution and integration."""

import json
import threading
from dataclasses import replace
from uuid import uuid4

from .config import AgentConfig
from .exceptions import (
    BudgetExceededError,
    ConfigurationError,
    ContextLimitExceededError,
    ProviderError,
)
from .providers.base import ModelProvider
from .types import Message, ProviderRequest, ProviderResponse, TokenUsage
from .utils import estimate_tokens


class TokenLedger:
    def __init__(self, limit: int):
        """Start one run with no reservations; positive integer limits only."""
        if type(limit) is not int or limit <= 0:
            raise ConfigurationError("Invalid token ledger limit")
        self.limit = limit
        self._usage = TokenUsage(0, 0)
        self._pending: dict[str, tuple[int, int]] = {}
        self._lock = threading.Lock()
        self.violated = False

    @property
    def used(self) -> int:
        return self._usage.total_tokens

    @property
    def usage(self) -> TokenUsage:
        return self._usage

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used - sum(a + b for a, b in self._pending.values()))

    @property
    def accounting_complete(self) -> bool:
        return self._usage.accounting == "reported"

    def reserve(self, input_allowance: int, output_allowance: int) -> str:
        """Atomically admit one allocation, refusing exhausted/violated ledgers."""
        with self._lock:
            if any(type(n) is not int or n < 0 for n in (input_allowance, output_allowance)):
                raise ConfigurationError("Invalid reservation")
            amount = input_allowance + output_allowance
            if self.violated or amount > self.remaining:
                raise BudgetExceededError(
                    "Insufficient remaining allocation", self.remaining, amount
                )
            key = str(uuid4())
            self._pending[key] = (input_allowance, output_allowance)
            return key

    def commit(self, reservation_id: str, usage: TokenUsage) -> None:
        """Finalize exactly once, retaining actual overspend and disabling later admission."""
        with self._lock:
            a, b = self._pending.pop(reservation_id)
            previous = self._usage
            modes = {"reported": 0, "estimated": 1, "unknown": 2}
            accounting = max((previous.accounting, usage.accounting), key=lambda m: modes[m])
            self._usage = TokenUsage(
                previous.input_tokens + usage.input_tokens,
                previous.output_tokens + usage.output_tokens,
                previous.cached_input_tokens + usage.cached_input_tokens,
                accounting,
            )
            if usage.input_tokens > a or usage.output_tokens > b or self.used > self.limit:
                self.violated = True
                raise BudgetExceededError(
                    "Actual usage exceeded admitted bounds", self.remaining, a + b
                )

    def release(self, reservation_id: str) -> None:
        """Release only an allocation known not to have been dispatched."""
        with self._lock:
            self._pending.pop(reservation_id)

    def charge_unknown(self, reservation_id: str) -> None:
        """Finalize uncertain remote outcomes with the full allocation and unknown accounting."""
        a, b = self._pending[reservation_id]
        self.commit(reservation_id, TokenUsage(a, b, accounting="unknown"))


class ModelRouter:
    def __init__(
        self, config: AgentConfig, primary: ModelProvider, fallback: ModelProvider | None = None
    ):
        """Retain adapters; model windows must be known before any dispatch."""
        self.config, self.primary, self.fallback = config, primary, fallback
        self.records: list[ProviderResponse] = []
        for provider, model, limit in (
            (primary, config.model, config.model_context_limit),
            (fallback, config.fallback_model, config.fallback_context_limit),
        ):
            if (
                provider
                and model
                and not (limit or provider.capabilities(model).context_window_tokens)
            ):
                raise ConfigurationError(
                    "Unknown model window; set "
                    + (
                        "fallback_context_limit"
                        if provider is fallback and fallback
                        else "model_context_limit"
                    )
                )

    def select_model(self, ledger: TokenLedger) -> tuple[ModelProvider, str]:
        """Select fallback before exhaustion; never reset or extend the ledger."""
        if ledger.violated or ledger.remaining < 1:
            raise BudgetExceededError("Token budget exhausted", ledger.remaining)
        if (
            self.fallback
            and self.config.fallback_model
            and ledger.used >= (ledger.limit * self.config.fallback_threshold)
        ):
            return self.fallback, self.config.fallback_model
        return self.primary, self.config.model

    def generate(
        self, messages: list[Message], ledger: TokenLedger, purpose: str
    ) -> ProviderResponse:
        """Admit the full request and reconcile one dispatch; no automatic transport replay."""
        provider, model = self.select_model(ledger)
        request = ProviderRequest(
            model, messages, self.config.max_output_tokens, self.config.timeout_seconds
        )
        if self.config.strict_budget and not provider.supports_strict_budget(request):
            raise ConfigurationError("strict_budget unsupported; no count/generation request sent")
        count = provider.count_input_tokens(request)
        incoming = (
            count
            if count is not None
            else sum(estimate_tokens(m.role + m.content) for m in messages)
        )
        if type(incoming) is not int or incoming < 0:
            raise ProviderError("Invalid input token count")
        caps = provider.capabilities(model)
        override = (
            self.config.fallback_context_limit
            if provider is self.fallback
            else self.config.model_context_limit
        )
        window = override or caps.context_window_tokens
        if window is None:
            raise ConfigurationError("Configure the selected model context limit")
        # Input estimates already include conservative byte/framing overhead.
        if incoming >= window or incoming >= ledger.remaining:
            reduced = []
            changed = False
            for message in messages:
                try:
                    value = json.loads(message.content)
                    if isinstance(value, dict) and value.get("optional_context"):
                        value["optional_context"] = ""
                        reduced.append(Message(message.role, json.dumps(value)))
                        changed = True
                        continue
                except ValueError:
                    pass
                reduced.append(message)
            if changed:
                return self.generate(reduced, ledger, purpose)
        if incoming >= window:
            raise ContextLimitExceededError("Required prompt exceeds model context")
        output = min(
            request.max_output_tokens,
            caps.max_output_tokens or request.max_output_tokens,
            ledger.remaining - incoming,
            window - incoming,
        )
        if output < 1:
            raise BudgetExceededError("Prompt cannot fit the remaining budget", ledger.remaining)
        request = replace(request, max_output_tokens=output)
        reservation = ledger.reserve(incoming, output)
        try:
            response = provider.generate(request)
            if not isinstance(response, ProviderResponse):
                raise ProviderError("Invalid provider response contract")
        except ConfigurationError:
            ledger.release(reservation)
            raise
        except Exception as exc:
            ledger.charge_unknown(reservation)
            failed = ProviderResponse(
                "", TokenUsage(incoming, output, accounting="unknown"), model, "error"
            )
            self.records.append(failed)
            if isinstance(exc, ProviderError):
                raise
            raise ProviderError("Provider dispatch failed; usage is uncertain") from exc
        if response.usage.accounting == "unknown":
            ledger.charge_unknown(reservation)
            response = replace(response, usage=TokenUsage(incoming, output, accounting="unknown"))
            self.records.append(response)
            raise ProviderError("Provider omitted usage; full allocation charged")
        usage = response.usage
        self.records.append(response)
        ledger.commit(reservation, usage)
        return response
