from __future__ import annotations

from typing import Literal

from pydantic import Field

from src.services.contracts import (
    ContractModel,
    GuidedDemoTask,
    HistoryCapability,
    PlannerMode,
    ProviderName,
    ServiceErrorDTO,
)


class HealthResponse(ContractModel):
    status: Literal["ok"] = "ok"


class ProviderCapability(ContractModel):
    name: ProviderName
    default_model: str
    requires_api_key: bool


class ToolCapability(ContractModel):
    name: str
    description: str
    requires_approval: bool


class CapabilitiesResponse(ContractModel):
    app_mode: Literal["demo", "local"]
    demo_mode_available: bool
    free_form_task_policy: Literal["supported_fictional_data", "full_supported_workflows"]
    guided_demo_tasks: list[GuidedDemoTask] = Field(default_factory=list)
    planner_modes: list[PlannerMode] = Field(default_factory=list)
    providers: list[ProviderCapability] = Field(default_factory=list)
    provider_controls_available: bool
    provider_api_key_allowed: bool
    history: HistoryCapability
    tools: list[ToolCapability] = Field(default_factory=list)
    approval_required_tools: list[str] = Field(default_factory=list)


class ErrorResponse(ContractModel):
    error: ServiceErrorDTO
