from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel] | None
    risk_level: str
    requires_approval: bool
    function: Callable[[BaseModel, dict[str, Any]], dict[str, Any]]

