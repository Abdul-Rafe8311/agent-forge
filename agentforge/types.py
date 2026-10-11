"""Stable JSON-safe runtime contracts."""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

Accounting = Literal["reported", "estimated", "unknown"]
Status = Literal[
    "success",
    "validation_failed",
    "budget_exceeded",
    "provider_error",
    "planning_failed",
    "context_limit_exceeded",
    "memory_error",
]


@dataclass(frozen=True)
class Message:
    role: Literal["system", "user", "assistant"]
    content: str

    def __post_init__(self):
        if self.role not in ("system", "user", "assistant") or not isinstance(self.content, str):
            raise ValueError("Invalid message")


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0
    accounting: Accounting = "reported"

    def __post_init__(self):
        if any(
            type(n) is not int or n < 0
            for n in (self.input_tokens, self.output_tokens, self.cached_input_tokens)
        ):
            raise ValueError("Usage requires nonnegative integer counts")
        if self.cached_input_tokens > self.input_tokens or self.accounting not in (
            "reported",
            "estimated",
            "unknown",
        ):
            raise ValueError("Invalid cache subset/accounting")

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class ProviderRequest:
    model: str
    messages: list[Message]
    max_output_tokens: int
    timeout_seconds: float = 60.0

    def __post_init__(self):
        if not self.messages or self.max_output_tokens <= 0 or self.timeout_seconds <= 0:
            raise ValueError("Request needs messages and positive output/timeout")


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    usage: TokenUsage
    model: str
    finish_reason: str | None = None
    request_id: str | None = None


@dataclass(frozen=True)
class ProviderCapabilities:
    context_window_tokens: int | None = None
    max_output_tokens: int | None = None


@dataclass(frozen=True)
class CodeArtifact:
    path: str
    content: str
    language: str = "python"


@dataclass(frozen=True)
class Step:
    id: str
    title: str
    instruction: str
    depends_on: list[str] = field(default_factory=list)
    kind: Literal["execute", "integrate"] = "execute"


@dataclass(frozen=True)
class TaskPlan:
    steps: list[Step]


@dataclass(frozen=True)
class ValidationIssue:
    kind: str
    message: str
    path: str | None = None
    line: int | None = None


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    diagnostics: str = ""


@dataclass
class AttemptRecord:
    step_id: str
    attempt: int
    model: str
    usage: TokenUsage
    validation: ValidationResult | None = None
    error: str | None = None
    error_kind: str | None = None


@dataclass
class StepResult:
    step: Step
    artifacts: list[CodeArtifact]
    explanation: str
    attempts: list[AttemptRecord]
    status: Literal["success", "failed", "budget_exceeded"]
    error_kind: Status | None = None


@dataclass
class AgentResult:
    code: str = ""
    artifacts: list[CodeArtifact] = field(default_factory=list)
    steps: list[StepResult] = field(default_factory=list)
    steps_taken: int = 0
    tokens_used: int = 0
    token_usage: TokenUsage = field(default_factory=lambda: TokenUsage(0, 0))
    success: bool = False
    status: Status = "success"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    models_used: list[str] = field(default_factory=list)
    session_id: str = ""
    project_id: str = ""
    accounting_complete: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Recursively serialize the public result; never serialize configuration."""
        return asdict(self)

    def write_to(self, directory: str | Path, *, overwrite: bool = False) -> list[Path]:
        """Explicitly export accepted files; path and overwrite errors raise."""
        from .artifacts import write_artifacts

        return write_artifacts(self.artifacts, Path(directory), overwrite)


@dataclass(frozen=True)
class MemoryEntry:
    id: str
    project_id: str
    session_id: str
    created_at: str
    task: str
    summary: str
    artifacts: list[CodeArtifact]
    success: bool


@dataclass(frozen=True)
class ContextChunk:
    path: str
    start_line: int
    end_line: int
    content: str
    score: float = 0.0


@dataclass(frozen=True)
class ContextBundle:
    text: str
    chunks: list[ContextChunk]
    estimated_tokens: int
    skipped_files: list[str]


@dataclass(frozen=True)
class AgentCallResult:
    output: Any
    usage: TokenUsage | None = None
    accounting_complete: bool = False
