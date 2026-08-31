from __future__ import annotations

from src.config import APP_MODE, normalize_app_mode
from src.services.contracts import (
    PlannerConfiguration,
    PlannerMode,
    ProviderName,
    StartTaskRequest,
)
from src.services.errors import InvalidTaskRequest


DEFAULT_MODELS = {
    ProviderName.openai: "gpt-4.1-mini",
    ProviderName.anthropic: "claude-3-5-haiku-latest",
    ProviderName.gemini: "gemini-2.0-flash",
    ProviderName.ollama: "llama3.2",
}


class ProviderService:
    """Resolve planner capabilities without contacting any model provider."""

    def __init__(self, app_mode: str = APP_MODE) -> None:
        self.app_mode = normalize_app_mode(app_mode)

    def allowed_planner_modes(self) -> tuple[PlannerMode, ...]:
        if self.app_mode == "demo":
            return (PlannerMode.deterministic,)
        return (PlannerMode.deterministic, PlannerMode.llm)

    def configure(self, request: StartTaskRequest) -> PlannerConfiguration:
        if request.planner_mode not in self.allowed_planner_modes():
            raise InvalidTaskRequest("Demo Mode supports deterministic planning only")
        if request.planner_mode == PlannerMode.deterministic:
            return PlannerConfiguration(
                app_mode=self.app_mode,
                planner_mode=request.planner_mode,
                provider=request.provider,
                requested_model=request.model,
            )

        effective_provider = request.provider or ProviderName.openai
        return PlannerConfiguration(
            app_mode=self.app_mode,
            planner_mode=request.planner_mode,
            provider=request.provider,
            effective_provider=effective_provider,
            requested_model=request.model,
            effective_model=request.model or DEFAULT_MODELS[effective_provider],
            requires_api_key=effective_provider != ProviderName.ollama,
        )
