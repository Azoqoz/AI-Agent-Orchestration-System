from __future__ import annotations

import logging
import time
from typing import Any

from langgraph.graph import END, START, StateGraph

from src.agent.plan_validator import PlanValidator
from src.agent.schemas import ExecutionPlan, StepStatus
from src.agent.state import AgentState
from src.execution.executor import bind_tool_entities, resolve_inputs
from src.execution.result_resolver import recommendation
from src.memory.repositories import Repository, now_iso
from src.planners import DeterministicPlanner, LLMPlanner
from src.planners.deterministic import UnsupportedActionError, unsupported_actions
from src.reporting.response_builder import build_case_summary
from src.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class WorkflowGraph:
    def __init__(self, registry: ToolRegistry, repo: Repository) -> None:
        self.registry, self.repo = registry, repo
        graph = StateGraph(AgentState)
        graph.add_node("prepare", self._prepare)
        graph.add_node("plan", self._plan)
        graph.add_node("validate", self._validate)
        graph.add_node("execute", self._execute)
        graph.add_node("finalize", self._finalize)
        graph.add_edge(START, "prepare")
        graph.add_conditional_edges("prepare", self._after_prepare, {"plan": "plan", "execute": "execute", "finalize": "finalize"})
        graph.add_edge("plan", "validate")
        graph.add_conditional_edges("validate", lambda s: "execute" if s.get("status") != "failed" else "finalize", {"execute": "execute", "finalize": "finalize"})
        graph.add_conditional_edges("execute", self._after_execute, {"execute": "execute", "finalize": "finalize", "end": END})
        graph.add_edge("finalize", END)
        self.compiled = graph.compile()

    def invoke(self, state: AgentState) -> AgentState:
        return self.compiled.invoke(state)

    def _prepare(self, state: AgentState) -> dict[str, Any]:
        return {"updated_at": now_iso()}

    @staticmethod
    def _after_prepare(state: AgentState) -> str:
        if state.get("status") in {"completed", "rejected", "failed"}: return "finalize"
        return "execute" if state.get("plan") else "plan"

    def _plan(self, state: AgentState) -> dict[str, Any]:
        try:
            blocked = unsupported_actions(state["user_request"])
            if blocked: raise UnsupportedActionError(blocked)
            planner = (LLMPlanner(state.get("provider") or "openai", self.registry.planning_catalog(), state.get("api_key"), state.get("model"),
                                  (state.get("entity_context") or {}).get("request"))
                       if state["planner_mode"] == "llm" else DeterministicPlanner())
            plan = planner.create_plan(state["user_request"])
            if state["planner_mode"] == "llm": plan.planner_mode = "llm"
            update = {"plan": plan.model_dump(mode="json"), "status": "plan_generated", "updated_at": now_iso()}
            self.repo.add_event(state["task_id"], "plan_generated", plan.summary)
        except Exception as exc:
            logger.exception("Planning failed")
            if state.get("planner_mode") == "llm" and getattr(exc, "planning_invalid", False):
                update = self._fallback_plan(state, exc, "LLM output was not a valid execution plan.")
            else:
                update = {"status": "failed", "errors": [*state.get("errors", []), str(exc)],
                          "display_error": getattr(exc, "user_message", str(exc)),
                          "unsupported_actions": getattr(exc, "unsupported_actions", state.get("unsupported_actions", [])),
                          "failure_kind": "unsupported_action" if isinstance(exc, UnsupportedActionError) else state.get("failure_kind"),
                          "updated_at": now_iso()}
        self.repo.save_task({**state, **update}); return update

    def _fallback_plan(self, state: AgentState, llm_error: Exception, reason: str) -> dict[str, Any]:
        technical = [*state.get("planning_errors", []), f"LLM planning failed: {llm_error}"]
        try:
            plan = DeterministicPlanner().create_plan(state["user_request"])
        except Exception as fallback_error:
            logger.exception("Deterministic fallback planning failed")
            return {
                "status": "failed",
                "errors": [*state.get("errors", []), f"Planning failed: {fallback_error}"],
                "planning_errors": [*technical, f"Deterministic planning failed: {fallback_error}"],
                "display_error": "This request could not be planned by either planner.",
                "fallback_used": False,
                "fallback_reason": None,
                "updated_at": now_iso(),
            }
        notice = "LLM planning could not produce a valid plan, so the deterministic planner was used."
        self.repo.add_event(state["task_id"], "planner_fallback", reason)
        return {
            "plan": plan.model_dump(mode="json"),
            "status": "plan_generated",
            "executed_planner": "deterministic_fallback",
            "fallback_used": True,
            "fallback_reason": reason,
            "planning_notice": notice,
            "planning_errors": technical,
            "display_error": None,
            "updated_at": now_iso(),
        }

    def _validate(self, state: AgentState) -> dict[str, Any]:
        if state.get("status") == "failed": return {}
        try:
            if state.get("requested_planner") == "llm" and not state.get("fallback_used"):
                excluded = DeterministicPlanner.negative_constraints(state.get("user_request", "").lower())
                planned_tools = {step.get("tool_name") for step in (state.get("plan") or {}).get("steps", [])}
                conflicts = sorted(planned_tools & excluded)
                if conflicts:
                    raise ValueError(f"LLM plan conflicts with explicit exclusions: {', '.join(conflicts)}")
            plan = PlanValidator(self.registry).validate(state["plan"], state)
            update = {"plan": plan.model_dump(mode="json"), "status": "running", "updated_at": now_iso()}
            for step in update["plan"]["steps"]: self.repo.save_step(state["task_id"], step)
            self.repo.add_event(state["task_id"], "plan_validated", f"Validated {len(plan.steps)} steps")
        except Exception as exc:
            logger.exception("Plan validation failed")
            if state.get("requested_planner") == "llm" and not state.get("fallback_used"):
                fallback = self._fallback_plan(state, exc, "LLM plan failed validation.")
                if fallback.get("status") != "failed":
                    try:
                        plan = PlanValidator(self.registry).validate(fallback["plan"], {**state, **fallback})
                        fallback.update({"plan": plan.model_dump(mode="json"), "status": "running"})
                        for step in fallback["plan"]["steps"]: self.repo.save_step(state["task_id"], step)
                        self.repo.add_event(state["task_id"], "plan_validated", f"Validated {len(plan.steps)} fallback steps")
                        self.repo.save_task({**state, **fallback})
                        return fallback
                    except Exception as fallback_error:
                        logger.exception("Deterministic fallback validation failed")
                        fallback.update({
                            "status": "failed",
                            "errors": [*state.get("errors", []), f"Fallback plan validation failed: {fallback_error}"],
                            "planning_errors": [*fallback.get("planning_errors", []), f"Fallback validation failed: {fallback_error}"],
                            "display_error": "Neither planner could produce a valid execution plan.",
                        })
                self.repo.save_task({**state, **fallback})
                return fallback
            invalid_refund_inputs = any(
                step.get("tool_name") == "refund_calculator"
                and step.get("step_id", "") in str(exc)
                for step in (state.get("plan") or {}).get("steps", [])
            )
            if state.get("planner_mode") == "llm" and invalid_refund_inputs:
                display_error = "Refund calculation could not be completed because the planner produced invalid numeric input."
            elif state.get("planner_mode") == "llm" and state.get("provider") == "ollama":
                display_error = "Ollama returned an invalid execution plan. Please retry or use Deterministic Planner."
            else:
                display_error = None
            update = {"status": "failed", "errors": [*state.get("errors", []), f"Plan validation failed: {exc}"],
                      "display_error": display_error, "updated_at": now_iso()}
        self.repo.save_task({**state, **update}); return update

    def _execute(self, state: AgentState) -> dict[str, Any]:
        plan = ExecutionPlan.model_validate(state["plan"])
        next_step = next((s for s in plan.steps if s.status.value not in {"completed", "failed", "skipped"}), None)
        if next_step is None: return {"status": "finalizing", "updated_at": now_iso()}
        if any(next(s for s in plan.steps if s.step_id == dep).status.value != "completed" for dep in next_step.depends_on):
            next_step.status = StepStatus.skipped; update = self._plan_update(plan)
            self.repo.save_step(state["task_id"], next_step.model_dump(mode="json")); self.repo.save_task({**state, **update}); return update
        if next_step.requires_approval and not state.get("approval_status"):
            next_step.status = StepStatus.waiting_for_approval
            update = {**self._plan_update(plan), "current_step_id": next_step.step_id, "status": "waiting_for_approval",
                      "recommended_action": recommendation(state.get("tool_results", {}))}
            self.repo.add_event(state["task_id"], "waiting_for_approval", next_step.tool_name, next_step.step_id)
            self.repo.save_step(state["task_id"], next_step.model_dump(mode="json")); self.repo.save_task({**state, **update}); return update
        if state.get("approval_status") == "rejected" and next_step.tool_name == "generate_customer_response":
            next_step.status = StepStatus.skipped; update = self._plan_update(plan)
            self.repo.save_step(state["task_id"], next_step.model_dump(mode="json")); self.repo.save_task({**state, **update}); return update
        next_step.status = StepStatus.running; started = time.perf_counter()
        try:
            inputs = resolve_inputs(next_step.inputs, state, next_step.tool_name)
            output = self.registry.execute(next_step.tool_name, inputs, {"state": state})
            latency = int((time.perf_counter() - started) * 1000); output["_latency_ms"] = latency
            next_step.inputs = inputs; next_step.status = StepStatus.completed
            results = {**state.get("tool_results", {}), next_step.tool_name: output}
            entity_context = bind_tool_entities(state.get("entity_context"), next_step.tool_name, output)
            update = {**self._plan_update(plan), "tool_results": results, "entity_context": entity_context,
                      "current_step_id": next_step.step_id, "status": "running"}
            if next_step.tool_name == "generate_report": update["generated_report_path"] = output["markdown_path"]
            if next_step.tool_name == "generate_customer_response": update["customer_response"] = output["customer_response"]
            self.repo.save_step(state["task_id"], next_step.model_dump(mode="json"), output, latency)
            self.repo.add_event(state["task_id"], "tool_completed", f"{next_step.tool_name} completed in {latency} ms", next_step.step_id)
        except Exception as exc:
            latency = int((time.perf_counter() - started) * 1000); next_step.status = StepStatus.failed
            message = f"{next_step.tool_name} failed: {exc}"; logger.exception(message)
            display_error = (
                "Refund calculation could not be completed because the planner produced invalid numeric input."
                if next_step.tool_name == "refund_calculator" else state.get("display_error")
            )
            update = {**self._plan_update(plan), "status": "failed", "errors": [*state.get("errors", []), message],
                      "display_error": display_error}
            self.repo.save_step(state["task_id"], next_step.model_dump(mode="json"), None, latency, str(exc))
        self.repo.save_task({**state, **update}); return update

    @staticmethod
    def _plan_update(plan: ExecutionPlan) -> dict[str, Any]:
        return {"plan": plan.model_dump(mode="json"), "updated_at": now_iso()}

    @staticmethod
    def _after_execute(state: AgentState) -> str:
        if state.get("status") == "waiting_for_approval": return "end"
        if state.get("status") in {"failed", "finalizing"}: return "finalize"
        return "execute"

    def _finalize(self, state: AgentState) -> dict[str, Any]:
        if state.get("status") == "failed" and state.get("failure_kind") == "unsupported_action":
            final = state.get("display_error") or "This action is not supported in V1."; status = "failed"
        elif state.get("status") == "failed":
            final = "The task could not be completed. " + (state.get("display_error") or (state.get("errors") or ["Unknown error"])[-1]); status = "failed"
        elif state.get("approval_status") == "rejected":
            final = "The recommendation was rejected by the human reviewer. An internal record was generated; no refund was approved or processed."; status = "rejected"
        else:
            planned_tools = {step.get("tool_name") for step in (state.get("plan") or {}).get("steps", [])}
            case_summary = (
                build_case_summary((state.get("tool_results") or {}).get("case_lookup", {}))
                if planned_tools == {"case_lookup"} else None
            )
            final = state.get("customer_response") or case_summary or "The requested checks completed successfully. Review the execution trace for results."; status = "completed"
        update = {"final_response": final, "status": status, "updated_at": now_iso()}
        self.repo.save_task({**state, **update}); return update
