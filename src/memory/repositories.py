from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from src.memory.database import Database


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Repository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def one(self, table: str, item_id: str) -> dict[str, Any] | None:
        if table not in {"customers", "orders", "cases"}:
            raise ValueError("Unsupported table")
        with self.db.connect() as conn:
            row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (item_id,)).fetchone()
        return dict(row) if row else None

    def demo_record_catalog(self) -> dict[str, list[str]]:
        """Return the public identifiers used to orient users in the demo UI."""
        with self.db.connect() as conn:
            customer_ids = [row["id"] for row in conn.execute("SELECT id FROM customers ORDER BY id")]
            case_ids = [row["id"] for row in conn.execute("SELECT id FROM cases ORDER BY id")]
        return {"customer_ids": customer_ids, "case_ids": case_ids}

    def open_cases_for_customer(self, customer_id: str) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT id AS case_id, case_type, status, description FROM cases "
                "WHERE customer_id = ? AND status = 'open' ORDER BY created_at DESC",
                (customer_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_task(self, state: dict[str, Any]) -> None:
        safe_state = {k: v for k, v in state.items() if k != "api_key"}
        with self.db.connect() as conn:
            conn.execute("""INSERT INTO tasks(id,user_request,planner_mode,provider,status,plan_json,state_json,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?)""", (state["task_id"], state["user_request"], state["planner_mode"], state.get("provider"),
                state["status"], json.dumps(state.get("plan")), json.dumps(safe_state, default=str), state["created_at"], state["updated_at"]))

    def save_task(self, state: dict[str, Any]) -> None:
        completed = now_iso() if state.get("status") in {"completed", "rejected", "failed"} else None
        safe_state = {k: v for k, v in state.items() if k != "api_key"}
        with self.db.connect() as conn:
            conn.execute("""UPDATE tasks SET status=?,plan_json=?,state_json=?,final_response=?,report_path=?,customer_response=?,updated_at=?,completed_at=COALESCE(?,completed_at) WHERE id=?""",
                (state["status"], json.dumps(state.get("plan")), json.dumps(safe_state, default=str), state.get("final_response"),
                 state.get("generated_report_path"), state.get("customer_response"), state["updated_at"], completed, state["task_id"]))

    def save_step(self, task_id: str, step: dict[str, Any], output: Any = None, latency_ms: int | None = None, error: str | None = None) -> None:
        now = now_iso()
        with self.db.connect() as conn:
            conn.execute("""INSERT INTO task_steps(task_id,step_id,tool_name,description,reason,tool_input_json,tool_output_json,status,requires_approval,started_at,completed_at,latency_ms,error_message)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(task_id,step_id) DO UPDATE SET tool_output_json=excluded.tool_output_json,status=excluded.status,completed_at=excluded.completed_at,latency_ms=excluded.latency_ms,error_message=excluded.error_message""",
            (task_id,step["step_id"],step["tool_name"],step.get("description"),step.get("reason"),json.dumps(step.get("inputs",{})),json.dumps(output,default=str) if output is not None else None,step["status"],int(step.get("requires_approval",False)),now,now if step["status"] in {"completed","failed","skipped","waiting_for_approval"} else None,latency_ms,error))

    def add_approval(self, task_id: str, step_id: str, decision: str, reason: str | None) -> None:
        with self.db.connect() as conn:
            conn.execute("INSERT INTO approvals(task_id,step_id,decision,reason,decided_at) VALUES(?,?,?,?,?)", (task_id,step_id,decision,reason,now_iso()))

    def add_event(self, task_id: str, event_type: str, detail: str, step_id: str | None = None) -> None:
        with self.db.connect() as conn:
            conn.execute("INSERT INTO tool_events(task_id,step_id,event_type,detail,created_at) VALUES(?,?,?,?,?)",
                         (task_id, step_id, event_type, detail, now_iso()))

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row: return None
        result = dict(row)
        result["state"] = json.loads(result.get("state_json") or "{}")
        return result

    def task_detail(self, task_id: str) -> dict[str, Any] | None:
        task = self.get_task(task_id)
        if not task: return None
        with self.db.connect() as conn:
            task["steps"] = [dict(r) for r in conn.execute("SELECT * FROM task_steps WHERE task_id=? ORDER BY id",(task_id,))]
            task["approvals"] = [dict(r) for r in conn.execute("SELECT * FROM approvals WHERE task_id=? ORDER BY id",(task_id,))]
            task["events"] = [dict(r) for r in conn.execute("SELECT * FROM tool_events WHERE task_id=? ORDER BY id",(task_id,))]
        return task

    def search_tasks(self, **filters: Any) -> list[dict[str, Any]]:
        clauses, params = [], []
        for key in ("task_id","status"):
            if filters.get(key):
                clauses.append(("id" if key == "task_id" else key) + " = ?"); params.append(filters[key])
        for key in ("case_id","customer_id","keyword"):
            if filters.get(key): clauses.append("user_request LIKE ?"); params.append(f"%{filters[key]}%")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(int(filters.get("limit",10)))
        with self.db.connect() as conn:
            rows = conn.execute(f"""SELECT t.id,t.user_request,t.planner_mode,t.provider,t.status,t.created_at,t.updated_at,t.completed_at,t.state_json,
              (SELECT COUNT(*) FROM task_steps s WHERE s.task_id=t.id AND s.status='completed') AS tools_used
              FROM tasks t{where} ORDER BY created_at DESC LIMIT ?""", params).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            state = json.loads(item.pop("state_json") or "{}")
            item.update({
                "requested_planner": state.get("requested_planner", item.get("planner_mode")),
                "executed_planner": state.get("executed_planner", item.get("planner_mode")),
                "fallback_used": bool(state.get("fallback_used", False)),
                "fallback_reason": state.get("fallback_reason"),
                "case_id": (state.get("tool_results", {}).get("case_lookup") or {}).get("case_id"),
                "customer_id": (state.get("tool_results", {}).get("customer_lookup") or {}).get("customer_id"),
                "refund_amount": (state.get("tool_results", {}).get("refund_calculator") or {}).get("final_recommended_refund"),
                "approval_status": state.get("approval_status"),
            })
            results.append(item)
        return results
