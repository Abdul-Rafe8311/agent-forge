"""Strict bounded dependency plans and one optional plan-format repair."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .exceptions import PlanningFailedError, ValidationFailedError
from .prompts import build_plan_messages
from .types import Message, Step, TaskPlan
from .utils import parse_json_object


class _Step(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    instruction: str = Field(min_length=1, max_length=4000)
    depends_on: list[str] = Field(max_length=100)
    kind: Literal["execute", "integrate"]


class _Plan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    steps: list[_Step] = Field(min_length=1, max_length=100)


def parse_plan(text: str, max_steps: int = 10) -> TaskPlan:
    """Validate dependencies/cycles/integration and return a stable topological ordering."""
    try:
        parsed = _Plan.model_validate(parse_json_object(text))
        steps = [Step(**item.model_dump()) for item in parsed.steps]
        if len(steps) > max_steps:
            raise ValueError("Plan exceeds max_steps")
        ids = [s.id for s in steps]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate step IDs")
        for step in steps:
            if not step.id.strip() or not step.title.strip() or not step.instruction.strip():
                raise ValueError("Blank step")
            if (
                step.id in step.depends_on
                or any(d not in ids for d in step.depends_on)
                or len(set(step.depends_on)) != len(step.depends_on)
            ):
                raise ValueError("Invalid dependencies")
        if len(steps) > 1:
            integration = [s for s in steps if s.kind == "integrate"]
            if len(integration) != 1 or set(integration[0].depends_on) != set(ids) - {
                integration[0].id
            }:
                raise ValueError("Exactly one integrate step must depend on every other step")
        ordered: list[Step] = []
        remaining = list(steps)
        while remaining:
            available = next(
                (s for s in remaining if set(s.depends_on) <= set(a.id for a in ordered)), None
            )
            if available is None:
                raise ValueError("Dependency cycle")
            ordered.append(available)
            remaining.remove(available)
        return TaskPlan(ordered)
    except (ValidationError, ValueError, ValidationFailedError) as exc:
        raise PlanningFailedError("Invalid bounded dependency plan") from exc


class TaskDecomposer:
    def __init__(self, router, max_steps: int):
        """Use the same run router/ledger as execution."""
        self.router, self.max_steps = router, max_steps

    def decompose(self, task: str, context: str, ledger) -> TaskPlan:
        """Request a plan, with at most one format repair using the same ledger."""
        messages = build_plan_messages(task, context, self.max_steps)
        repairs = 1 if self.router.config.error_loop and self.router.config.max_retries > 0 else 0
        for attempt in range(repairs + 1):
            response = self.router.generate(messages, ledger, "plan")
            try:
                if response.finish_reason not in (
                    None,
                    "completed",
                    "end_turn",
                    "stop_sequence",
                    "stop",
                ):
                    raise PlanningFailedError("Planning response truncated or refused")
                return parse_plan(response.text, self.max_steps)
            except PlanningFailedError:
                if attempt == repairs:
                    raise
                messages.append(
                    Message(
                        "user",
                        "Repair the invalid plan; original schema/dependencies "
                        "still apply. Rejected output: " + response.text[:8000],
                    )
                )
        raise AssertionError("Unreachable")
