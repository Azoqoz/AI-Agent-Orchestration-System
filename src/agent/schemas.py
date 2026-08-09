from __future__ import annotations

from decimal import Decimal
from enum import Enum
import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints


def _normalize_identifier(value: Any) -> Any:
    return value.strip().upper() if isinstance(value, str) else value


CaseId = Annotated[str, BeforeValidator(_normalize_identifier), StringConstraints(pattern=r"^CASE-\d{3,}$")]
CustomerId = Annotated[str, BeforeValidator(_normalize_identifier), StringConstraints(pattern=r"^CUST-\d{3,}$")]
OrderId = Annotated[str, BeforeValidator(_normalize_identifier), StringConstraints(pattern=r"^ORD-\d{3,}$")]
TaskId = Annotated[str, BeforeValidator(_normalize_identifier), StringConstraints(pattern=r"^TASK-[A-Z0-9]+$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StepStatus(str, Enum):
    pending = "pending"
    ready = "ready"
    running = "running"
    waiting_for_approval = "waiting_for_approval"
    approved = "approved"
    rejected = "rejected"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class PlanStep(StrictModel):
    step_id: str
    tool_name: str
    description: str
    reason: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    requires_approval: bool = False
    status: StepStatus = StepStatus.pending


class ExecutionPlan(StrictModel):
    task_type: str
    planner_mode: Literal["deterministic", "llm"]
    summary: str
    steps: list[PlanStep]


class CustomerLookupInput(StrictModel):
    customer_id: CustomerId


class CaseLookupInput(StrictModel):
    case_id: CaseId
    customer_id: CustomerId | None = None


class PolicyCheckInput(StrictModel):
    case_id: CaseId


_DECIMAL_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
_MONEY_PATTERN = re.compile(rf"^\s*\$?\s*({_DECIMAL_NUMBER})\s*(?:USD)?\s*$", re.I)
_PERCENT_PATTERN = re.compile(rf"^\s*({_DECIMAL_NUMBER})\s*%?\s*$")


def _decimal_value(value: Any, pattern: re.Pattern[str], field_description: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field_description} must be a numeric value")
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value))
        except Exception as exc:
            raise ValueError(f"{field_description} must be a valid decimal number") from exc
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_description} must be a non-empty numeric value")
    match = pattern.fullmatch(value)
    if not match:
        raise ValueError(f"{field_description} contains an invalid or ambiguous numeric value")
    return Decimal(match.group(1))


def normalize_money(value: Any) -> Decimal:
    return _decimal_value(value, _MONEY_PATTERN, "Money input")


def normalize_percentage(value: Any) -> Decimal:
    return _decimal_value(value, _PERCENT_PATTERN, "Refund percentage")


MoneyDecimal = Annotated[Decimal, BeforeValidator(normalize_money), Field(ge=0)]
PercentageDecimal = Annotated[Decimal, BeforeValidator(normalize_percentage), Field(ge=0, le=100)]


class RefundCalculatorInput(StrictModel):
    amount_paid: MoneyDecimal
    refund_percentage: PercentageDecimal
    non_refundable_fee: MoneyDecimal = Decimal("0")
    previous_refund_amount: MoneyDecimal = Decimal("0")
    tax_treatment: Literal["include", "exclude"] = "include"


class PriorityClassifierInput(StrictModel):
    case_id: CaseId


class SLACheckerInput(StrictModel):
    case_id: CaseId
    priority: Literal["Low", "Medium", "High"] | None = None


class GenerateReportInput(StrictModel):
    task_id: TaskId


class GenerateCustomerResponseInput(StrictModel):
    task_id: TaskId


class TaskHistorySearchInput(StrictModel):
    task_id: TaskId | None = None
    case_id: CaseId | None = None
    customer_id: CustomerId | None = None
    status: str | None = None
    keyword: str | None = None
    limit: int = Field(default=10, ge=1, le=50)
