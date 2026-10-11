"""Strict HTTP contracts reuse dataclass result definitions through Pydantic adapters."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from .types import AgentResult


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    task: str = Field(min_length=1, max_length=16000)

    @field_validator("task")
    @classmethod
    def task_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("task must be nonblank")
        return value


class ApiError(BaseModel):
    code: str
    message: str
    request_id: str


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str


GenerateResponse = AgentResult
RESULT_ADAPTER = TypeAdapter(AgentResult)
