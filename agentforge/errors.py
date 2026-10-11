"""Compatibility error aliases from the original local prototype."""

from .exceptions import (
    AgentForgeError,
    BudgetExceededError,
    ConfigurationError,
    MemoryBackendError,
    ProviderError,
    ValidationFailedError,
)

BudgetExceeded = BudgetExceededError
ValidationError = ValidationFailedError
MemoryError = MemoryBackendError
__all__ = [
    "AgentForgeError",
    "ConfigurationError",
    "ProviderError",
    "BudgetExceeded",
    "ValidationError",
    "MemoryError",
]
