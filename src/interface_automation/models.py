from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


class ActionType(StrEnum):
    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    EXTRACT = "extract"
    WAIT = "wait"


class RiskLevel(StrEnum):
    SAFE = "safe"
    REVERSIBLE = "reversible"
    IRREVERSIBLE = "irreversible"


class Locator(BaseModel):
    strategy: Literal["role", "label", "text", "css"]
    value: str
    role: str | None = None
    exact: bool = True
    rationale: str

    @model_validator(mode="after")
    def role_strategy_requires_role(self) -> Locator:
        if self.strategy == "role" and not self.role:
            raise ValueError("role locator requires role")
        return self


class ParameterSpec(BaseModel):
    name: str
    type: Literal["string", "integer", "boolean"]
    description: str
    required: bool = True
    sensitive: bool = False
    pattern: str | None = None


class OutputSpec(BaseModel):
    name: str
    type: Literal["string", "integer", "number", "boolean"]
    description: str
    sensitive: bool = False


class Step(BaseModel):
    id: str
    action: ActionType
    description: str
    locator: Locator | None = None
    value: str | None = None
    output: str | None = None
    risk: RiskLevel = RiskLevel.SAFE
    timeout_ms: int = Field(default=5_000, ge=100, le=60_000)
    retries: int = Field(default=1, ge=0, le=3)


class Checkpoint(BaseModel):
    locator: Locator
    expected_text: str | None = None
    description: str


class BusinessOutcomeRule(BaseModel):
    code: str
    locator: Locator
    message: str


class CapabilityArtifact(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    capability_id: str
    name: str
    description: str
    artifact_version: str = "1.0.0"
    approval: Literal["draft", "approved"] = "draft"
    target_url: HttpUrl
    allowed_route_pattern: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    inputs: list[ParameterSpec]
    outputs: list[OutputSpec]
    steps: list[Step]
    checkpoint: Checkpoint
    business_outcomes: list[BusinessOutcomeRule] = Field(default_factory=list)


class StepFailure(BaseModel):
    step_id: str | None = None
    expected: str
    observed: str
    screenshot: str | None = None


class SuccessResult(BaseModel):
    status: Literal["success"] = "success"
    outputs: dict[str, Any]
    evidence_dir: str


class BusinessOutcomeResult(BaseModel):
    status: Literal["business_outcome"] = "business_outcome"
    code: str
    message: str
    evidence_dir: str


class FailureResult(BaseModel):
    status: Literal["failure"] = "failure"
    code: str
    message: str
    detail: StepFailure
    intervention_id: str | None = None
    evidence_dir: str


RunResult = SuccessResult | BusinessOutcomeResult | FailureResult


class InterventionRequest(BaseModel):
    id: str
    capability_id: str
    reason: str
    step_id: str | None
    screenshot: str | None
    control: Literal["automation", "human", "paused"] = "paused"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
