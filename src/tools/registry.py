from __future__ import annotations

from typing import Any

from src.agent.schemas import (CaseLookupInput, CustomerLookupInput, GenerateCustomerResponseInput,
    GenerateReportInput, PolicyCheckInput, PriorityClassifierInput, RefundCalculatorInput,
    SLACheckerInput, TaskHistorySearchInput)
from src.memory.database import Database
from src.memory.repositories import Repository
from src.tools.base import ToolDefinition
from src.tools.case_lookup import execute as case_lookup
from src.tools.customer_lookup import execute as customer_lookup
from src.tools.generate_customer_response import execute as generate_customer_response
from src.tools.generate_report import execute as generate_report
from src.tools.policy_checker import execute as policy_checker
from src.tools.priority_classifier import execute as priority_classifier
from src.tools.refund_calculator import execute as refund_calculator
from src.tools.sla_checker import execute as sla_checker
from src.tools.task_history_search import execute as task_history_search


class ToolRegistry:
    def __init__(self, db: Database) -> None:
        self.db = db
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if tool.name in self._tools: raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition:
        if name not in self._tools: raise KeyError(f"Unknown tool: {name}")
        return self._tools[name]

    def names(self) -> set[str]: return set(self._tools)
    def descriptions(self) -> dict[str, str]: return {k:v.description for k,v in self._tools.items()}
    def planning_catalog(self) -> dict[str, dict[str, Any]]:
        return {
            name: {
                "description": tool.description,
                "input_schema": tool.input_schema.model_json_schema(),
                "requires_approval": tool.requires_approval,
            }
            for name, tool in self._tools.items()
        }

    def execute(self, name: str, inputs: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        tool = self.get(name)
        parsed = tool.input_schema.model_validate(inputs)
        context = {**context, "db": self.db, "repo": Repository(self.db)}
        return tool.function(parsed, context)


def build_registry(db: Database) -> ToolRegistry:
    registry = ToolRegistry(db)
    specs = [
        ("customer_lookup","Retrieve a fictional customer record.",CustomerLookupInput,"low",False,customer_lookup),
        ("case_lookup","Retrieve a support or refund case.",CaseLookupInput,"low",False,case_lookup),
        ("policy_checker","Apply deterministic refund eligibility rules.",PolicyCheckInput,"medium",False,policy_checker),
        ("refund_calculator","Calculate a recommended refund using decimal arithmetic.",RefundCalculatorInput,"medium",False,refund_calculator),
        ("priority_classifier","Classify case priority using explainable rules.",PriorityClassifierInput,"low",False,priority_classifier),
        ("sla_checker","Check a case against the configured SLA.",SLACheckerInput,"low",False,sla_checker),
        ("generate_report","Generate an internal Markdown and text report.",GenerateReportInput,"medium",True,generate_report),
        ("generate_customer_response","Draft a controlled customer response.",GenerateCustomerResponseInput,"medium",False,generate_customer_response),
        ("task_history_search","Search the persistent task audit history.",TaskHistorySearchInput,"low",False,task_history_search),
    ]
    for name, desc, schema, risk, approval, func in specs:
        registry.register(ToolDefinition(name,desc,schema,None,risk,approval,func))
    return registry
