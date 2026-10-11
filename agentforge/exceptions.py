"""Safe, classified framework errors; expected run failures are represented in AgentResult."""


class AgentForgeError(Exception):
    """Base safe diagnostic; original causes remain chained for private debugging."""


class ConfigurationError(AgentForgeError, ValueError):
    """Invalid configuration before execution."""


class ProviderError(AgentForgeError):
    """A dispatched request failed; usage may be unknown."""

    def __init__(self, message: str, request_id: str | None = None):
        super().__init__(message)
        self.request_id = request_id


class UnsupportedProviderError(ConfigurationError):
    """Provider or feature is not supported."""


class BudgetExceededError(AgentForgeError):
    """Admission or reconciliation failed."""

    def __init__(self, message: str, remaining: int = 0, reserved: int = 0):
        super().__init__(message)
        self.remaining, self.reserved = remaining, reserved


class ValidationFailedError(AgentForgeError):
    """An artifact candidate failed validation."""


class MemoryBackendError(AgentForgeError):
    """Persistence failed without exposing its payload or credentials."""


class ArtifactPathError(ConfigurationError):
    """Unsafe artifact destination."""


class PlanningFailedError(AgentForgeError):
    """No valid dependency plan was obtained."""


class ContextLimitExceededError(AgentForgeError):
    """Required request content exceeds the model window."""


class RunStateError(AgentForgeError):
    """A wrapper is closed or already running."""
