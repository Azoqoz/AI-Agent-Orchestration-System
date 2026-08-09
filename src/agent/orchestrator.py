from __future__ import annotations

import uuid
from typing import Any

from src.agent.graph import WorkflowGraph
from src.config import APP_MODE, normalize_app_mode
from src.execution.executor import extract_request_entities
from src.memory.database import Database
from src.memory.repositories import Repository, now_iso
from src.memory.seed import seed_database
from src.tools.registry import build_registry


class Orchestrator:
    def __init__(self, db: Database | None = None, app_mode: str = APP_MODE) -> None:
        self.app_mode = normalize_app_mode(app_mode)
        self.db = db or Database(); seed_database(self.db)
        self.repo = Repository(self.db); self.registry = build_registry(self.db); self.graph = WorkflowGraph(self.registry, self.repo)

    def start(self, user_request: str, planner_mode: str = "deterministic", provider: str | None = None, api_key: str | None = None, model: str | None = None) -> dict[str, Any]:
        if planner_mode not in {"deterministic", "llm"}: raise ValueError("Invalid planner mode")
        if self.app_mode == "demo" and planner_mode != "deterministic":
            raise ValueError("Demo Mode supports deterministic planning only")
        created = now_iso(); state = {"task_id": f"TASK-{uuid.uuid4().hex[:8].upper()}", "user_request": user_request,
          "planner_mode": planner_mode, "provider": provider, "model": model, "plan": {}, "current_step_id": None, "tool_results": {},
          "entity_context": {"request": extract_request_entities(user_request), "resolved": {}},
          "approval_status": None, "approval_reason": None, "recommended_action": None, "final_response": None,
          "generated_report_path": None, "customer_response": None, "status": "received", "errors": [],
          "created_at": created, "updated_at": created, "api_key": api_key, "display_error": None,
          "requested_planner": planner_mode, "executed_planner": planner_mode, "fallback_used": False,
          "fallback_reason": None, "planning_notice": None, "planning_errors": [],
          "unsupported_actions": [], "failure_kind": None}
        self.repo.create_task(state)
        self.repo.add_event(state["task_id"], "task_received", "Task received by the orchestrator")
        return dict(self.graph.invoke(state))

    def resume(self, task_id: str, decision: str, reason: str | None = None) -> dict[str, Any]:
        task = self.repo.get_task(task_id)
        if not task: raise ValueError(f"Task {task_id} was not found")
        state = task["state"]
        if state.get("status") != "waiting_for_approval": raise ValueError("Task is not waiting for approval")
        if decision not in {"approved", "rejected"}: raise ValueError("Decision must be approved or rejected")
        step_id = state["current_step_id"]
        self.repo.add_approval(task_id, step_id, decision, reason)
        self.repo.add_event(task_id, "approval_received", decision, step_id)
        for step in state["plan"]["steps"]:
            if step["step_id"] == step_id: step["status"] = "pending"
        state.update({"approval_status": decision, "approval_reason": reason, "status": "running", "updated_at": now_iso()})
        self.repo.save_task(state)
        return dict(self.graph.invoke(state))

    def load(self, task_id: str) -> dict[str, Any] | None:
        task = self.repo.get_task(task_id); return task["state"] if task else None
