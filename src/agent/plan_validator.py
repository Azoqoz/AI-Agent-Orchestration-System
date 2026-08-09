from __future__ import annotations

from typing import Any
from src.agent.schemas import ExecutionPlan
from src.config import MAX_PLAN_STEPS
from src.execution.executor import apply_authoritative_inputs, is_tool_reference
from src.tools.registry import ToolRegistry


class PlanValidationError(ValueError): pass


class PlanValidator:
    def __init__(self, registry: ToolRegistry, max_steps: int = MAX_PLAN_STEPS) -> None:
        self.registry, self.max_steps = registry, max_steps

    def validate(self, plan: ExecutionPlan | dict[str, Any], state: dict[str, Any] | None = None) -> ExecutionPlan:
        parsed = plan if isinstance(plan,ExecutionPlan) else ExecutionPlan.model_validate(plan)
        if not parsed.steps: raise PlanValidationError("Plan must contain at least one step")
        if len(parsed.steps)>self.max_steps: raise PlanValidationError(f"Plan exceeds the {self.max_steps}-step limit")
        ids=[s.step_id for s in parsed.steps]
        if len(ids)!=len(set(ids)): raise PlanValidationError("Step IDs must be unique")
        seen:set[str]=set()
        has_refund_calculation = any(step.tool_name == "refund_calculator" for step in parsed.steps)
        for step in parsed.steps:
            if step.tool_name not in self.registry.names(): raise PlanValidationError(f"Unknown tool: {step.tool_name}")
            if state is not None:
                step.inputs = apply_authoritative_inputs(step.inputs, state, step.tool_name)
            for dep in step.depends_on:
                if dep not in ids: raise PlanValidationError(f"Step {step.step_id} has unknown dependency {dep}")
                if dep not in seen: raise PlanValidationError(f"Step {step.step_id} depends on a later step {dep}")
            definition=self.registry.get(step.tool_name)
            approval_required = definition.requires_approval or (
                step.tool_name == "generate_customer_response" and has_refund_calculation
            )
            if approval_required and not step.requires_approval:
                raise PlanValidationError(f"Tool {step.tool_name} must require approval")
            if step.tool_name == "generate_customer_response" and not approval_required:
                step.requires_approval = False
            self._validate_inputs(definition.input_schema,step.inputs,step.step_id)
            seen.add(step.step_id)
        self._check_cycles(parsed)
        return parsed

    @staticmethod
    def _validate_inputs(schema: type, inputs: dict[str,Any], step_id: str) -> None:
        fields=schema.model_fields
        for name,field in fields.items():
            if field.is_required() and (name not in inputs or inputs[name] is None): raise PlanValidationError(f"Step {step_id} is missing required input: {name}")
        if any(is_tool_reference(v) for v in inputs.values()):
            return
        concrete={k:v for k,v in inputs.items() if v is not None}
        try: schema.model_validate({**{k:"placeholder" for k,v in inputs.items() if isinstance(v,str) and v.startswith("$")},**concrete})
        except Exception as exc: raise PlanValidationError(f"Invalid inputs for {step_id}: {exc}") from exc

    @staticmethod
    def _check_cycles(plan: ExecutionPlan) -> None:
        graph={s.step_id:s.depends_on for s in plan.steps}; visiting:set[str]=set(); done:set[str]=set()
        def visit(node:str)->None:
            if node in visiting: raise PlanValidationError("Plan contains a circular dependency")
            if node in done:return
            visiting.add(node)
            for dep in graph[node]: visit(dep)
            visiting.remove(node);done.add(node)
        for node in graph: visit(node)
