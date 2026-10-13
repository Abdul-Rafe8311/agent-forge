"""Versioned helper contracts, independent of provider generation/accounting."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Requirement(Contract):
    id: str = Field(pattern=r"^R[0-9]+$")
    document: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    category: Literal["objective", "shared_constraint", "acceptance"] = "objective"
    scope: Literal["all_tasks", "selected_tasks"] = "selected_tasks"
    interpretation: str = Field(default="", max_length=512)
    extraction_mode: Literal["explicit", "agent_inferred"] = "explicit"
    clarification_status: Literal["unreviewed", "resolved", "needs_clarification"] = "unreviewed"
    acceptance_check_ids: list[str] = Field(default_factory=list)
    supersedes: list[str] = Field(default_factory=list)


class RelevantFile(Contract):
    path: str = Field(max_length=512)
    reason: str = Field(default="", max_length=160)
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)


class TaskCard(Contract):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
    objective: str = Field(min_length=1, max_length=512)
    requirement_ids: list[str] = Field(min_length=1)
    depends_on: list[str] = Field(default_factory=list)
    kind: Literal["execute", "integrate"] = "execute"
    context_queries: list[str] = Field(default_factory=list, max_length=4)
    relevant_files: list[RelevantFile] = Field(default_factory=list, max_length=20)
    acceptance_check_ids: list[str] = Field(default_factory=lambda: ["syntax"])
    manual_acceptance_criteria: list[str] = Field(default_factory=list)
    input_contracts: list[str] = Field(default_factory=list)
    output_contracts: list[str] = Field(default_factory=list)
    context_unknowns: list[str] = Field(default_factory=list, max_length=20)


class Plan(Contract):
    spec_hash: str
    tasks: list[TaskCard] = Field(min_length=1, max_length=9)
    planning_mode: Literal["unsplit", "explicit_sections", "agent_model"] = "unsplit"
    planning_note: str = Field(default="", max_length=512)


class Check(Contract):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
    kind: Literal["syntax", "command", "manual"]
    argv: list[str] = Field(default_factory=list, max_length=64)
    files: list[str] = Field(default_factory=list, max_length=100)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    description: str = Field(default="", max_length=512)


class Completion(Contract):
    spec_hash: str
    plan_version: int = Field(ge=1)
    summary: str = Field(min_length=1, max_length=1200)
    changed_files: list[str] = Field(default_factory=list, max_length=20)
    decisions: list[str] = Field(default_factory=list)
    next_task_implications: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)


class Limits(Contract):
    packet_bytes: int = Field(default=20480, ge=1024, le=65536)
    memory_bytes: int = Field(default=2048, ge=256, le=8192)
    code_bytes: int = Field(default=12288, ge=256, le=32768)
    instruction_bytes: int = Field(default=4096, ge=512, le=16384)
    max_files: int = Field(default=1000, ge=1, le=10000)
    file_bytes: int = Field(default=262144, ge=128, le=1048576)
    scan_bytes: int = Field(default=8388608, ge=128, le=33554432)
    max_depth: int = Field(default=12, ge=1, le=32)
    scan_seconds: int = Field(default=5, ge=1, le=30)
    max_chunks: int = Field(default=6, ge=1, le=20)
