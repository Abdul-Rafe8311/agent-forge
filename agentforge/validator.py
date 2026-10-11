"""Strict output parsing, syntax-only default validation and explicit command validation."""

import ast
import os
import subprocess
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .artifacts import merge_artifacts, write_artifacts
from .exceptions import (
    ArtifactPathError,
    BudgetExceededError,
    ContextLimitExceededError,
    ProviderError,
    ValidationFailedError,
)
from .prompts import build_repair_messages, build_step_messages
from .types import (
    AttemptRecord,
    CodeArtifact,
    Status,
    Step,
    StepResult,
    TokenUsage,
    ValidationIssue,
    ValidationResult,
)
from .utils import parse_json_object, redact_sensitive_text


class _Artifact(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str = Field(min_length=1, max_length=512)
    content: str = Field(min_length=1, max_length=1000000)
    language: str = Field(min_length=1, max_length=32)


class _Generation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    artifacts: list[_Artifact] = Field(min_length=1, max_length=100)
    explanation: str = Field(max_length=8000)


def parse_generation(text: str) -> tuple[list[CodeArtifact], str]:
    """Parse one strict nonempty artifact bundle and reject malformed or unsafe candidates."""
    try:
        data = _Generation.model_validate(parse_json_object(text))
        artifacts = [CodeArtifact(**a.model_dump()) for a in data.artifacts]
        return merge_artifacts([], artifacts), data.explanation
    except (ValidationError, ArtifactPathError) as exc:
        raise ValidationFailedError("Invalid artifact schema or paths") from exc


class Validator(Protocol):
    def validate(self, artifacts: list[CodeArtifact]) -> ValidationResult: ...


class PythonSyntaxValidator:
    def validate(self, artifacts: list[CodeArtifact]) -> ValidationResult:
        """Check structure/Python AST only; never prove runtime or cross-file semantics."""
        issues = []
        notes = []
        for artifact in artifacts:
            if not artifact.content.strip():
                issues.append(ValidationIssue("empty", "Empty artifact", artifact.path))
            elif artifact.language == "python" or artifact.path.endswith(".py"):
                try:
                    ast.parse(artifact.content, filename=artifact.path)
                except (SyntaxError, ValueError) as exc:
                    issues.append(
                        ValidationIssue(
                            "syntax", str(exc), artifact.path, getattr(exc, "lineno", None)
                        )
                    )
            else:
                notes.append(f"{artifact.path}: structure-only validation")
        return ValidationResult(not issues, issues, "; ".join(notes))


class CommandValidator:
    def __init__(self, command: list[str] | tuple[str, ...], timeout_seconds: float = 30):
        """Explicit opt-in argument-array command; this subprocess is not a security sandbox."""
        if not command or timeout_seconds <= 0:
            raise ValueError("Invalid validator command/timeout")
        self.command, self.timeout_seconds = list(command), timeout_seconds

    def validate(self, artifacts: list[CodeArtifact]) -> ValidationResult:
        """Stage files in a temporary directory and bound timeout and retained diagnostics."""
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            write_artifacts(artifacts, root)
            env = {
                k: v
                for k, v in os.environ.items()
                if k in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
            }
            try:
                process = subprocess.Popen(
                    self.command,
                    cwd=root,
                    env=env,
                    shell=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                buffers: list[bytearray] = [bytearray(), bytearray()]

                def drain(stream, target):
                    # Drain all output; retain at most 8 KiB per stream.
                    while chunk := stream.read(4096):
                        target.extend(chunk[: max(0, 8192 - len(target))])

                threads = [
                    threading.Thread(target=drain, args=(stream, target), daemon=True)
                    for stream, target in zip((process.stdout, process.stderr), buffers)
                ]
                for thread in threads:
                    thread.start()
                timed_out = False
                try:
                    process.wait(timeout=self.timeout_seconds)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    process.kill()
                    process.wait()
                for thread in threads:
                    thread.join(timeout=1)
                diagnostic = redact_sensitive_text(
                    (bytes(buffers[0]) + bytes(buffers[1])).decode(errors="replace")
                )
                if timed_out:
                    return ValidationResult(
                        False, [ValidationIssue("timeout", "Validator timed out")], diagnostic
                    )
                if process.returncode:
                    return ValidationResult(
                        False,
                        [ValidationIssue("command", "Validator exit " + str(process.returncode))],
                        diagnostic,
                    )
                return ValidationResult(True, [], diagnostic)
            except subprocess.TimeoutExpired:
                return ValidationResult(False, [ValidationIssue("timeout", "Validator timed out")])
            except OSError:
                return ValidationResult(
                    False, [ValidationIssue("command", "Validator could not start")]
                )


class RepairLoop:
    def execute(
        self,
        task: str,
        step: Step,
        context: str,
        accepted_artifacts: list[CodeArtifact],
        router,
        ledger,
        validator: Validator,
        max_retries: int,
    ) -> StepResult:
        """One retry authority validates combined candidates and returns accepted changes only."""
        attempts = []
        previous = ""
        validation = ValidationResult(False, [])
        for attempt in range(max_retries + 1):
            messages = (
                build_step_messages(task, step, context, accepted_artifacts)
                if attempt == 0
                else build_repair_messages(
                    task, step, previous, validation, context, accepted_artifacts
                )
            )
            before = len(router.records)
            record = AttemptRecord(step.id, attempt + 1, router.config.model, TokenUsage(0, 0))
            try:
                response = router.generate(messages, ledger, "repair" if attempt else "execute")
                record.model, record.usage = response.model, response.usage
                previous = response.text
                if response.finish_reason not in (
                    None,
                    "completed",
                    "end_turn",
                    "stop_sequence",
                    "stop",
                ):
                    raise ValidationFailedError("Response was truncated, refused, or nontext")
                delta, explanation = parse_generation(response.text)
                candidate = merge_artifacts(accepted_artifacts, delta)
                validation = validator.validate(candidate)
                if not isinstance(validation, ValidationResult):
                    raise TypeError("Validator must return ValidationResult")
                record.validation = validation
                attempts.append(record)
                if validation.passed:
                    return StepResult(step, delta, explanation, attempts, "success")
            except (ValidationFailedError, ArtifactPathError) as exc:
                validation = ValidationResult(False, [ValidationIssue("structure", str(exc))])
                record.validation = validation
                attempts.append(record)
            except (BudgetExceededError, ProviderError, ContextLimitExceededError) as exc:
                if len(router.records) > before:
                    record.model, record.usage = router.records[-1].model, router.records[-1].usage
                kind: Status = (
                    "budget_exceeded"
                    if isinstance(exc, BudgetExceededError)
                    else "context_limit_exceeded"
                    if isinstance(exc, ContextLimitExceededError)
                    else "provider_error"
                )
                record.error = redact_sensitive_text(str(exc))
                record.error_kind = kind
                attempts.append(record)
                return StepResult(
                    step,
                    [],
                    "",
                    attempts,
                    "budget_exceeded" if kind == "budget_exceeded" else "failed",
                    kind,
                )
        return StepResult(step, [], "", attempts, "failed", "validation_failed")
