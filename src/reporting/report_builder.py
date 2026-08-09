from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.config import REPORT_DIR


def _find(results: dict[str, Any], tool: str) -> dict[str, Any]:
    return next((v for k,v in results.items() if k.startswith(tool+":") or k == tool), {})


def build_report(state: dict[str, Any]) -> tuple[str, str, str]:
    results = state.get("tool_results", {})
    customer, case = _find(results,"customer_lookup"), _find(results,"case_lookup")
    policy, refund = _find(results,"policy_checker"), _find(results,"refund_calculator")
    priority, sla = _find(results,"priority_classifier"), _find(results,"sla_checker")
    decision = state.get("approval_status") or "not required"
    recommendation = "Recommendation rejected; no customer-facing approval." if decision == "rejected" else state.get("recommended_action","Review the recorded evidence")
    lines = [f"# Internal Case Report — {state['task_id']}","",
      f"- **Customer:** {customer.get('customer_id','N/A')} — {customer.get('name','N/A')}",
      f"- **Case:** {case.get('case_id','N/A')} — {case.get('description','N/A')}",
      f"- **Eligibility:** {policy.get('eligibility','N/A')} — {policy.get('reason','N/A')}",
      f"- **Priority:** {priority.get('priority','N/A')}",
      f"- **SLA:** {sla.get('explanation','N/A')}",
      f"- **Recommended refund:** ${refund.get('final_recommended_refund','0.00')} USD",
      f"- **Human decision:** {decision.title()}","", "## Execution", ""]
    for step in state.get("plan",{}).get("steps",[]):
        lines.append(f"- `{step['tool_name']}` — {step['status']} — {step['reason']}")
    lines += ["", "## Final recommendation", "", recommendation,
              "", "_Fictional demo data. This report does not execute a financial transaction._"]
    markdown = "\n".join(lines)
    plain = re.sub(r"[`*_#]", "", markdown)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", state["task_id"])
    md_path = REPORT_DIR / f"{safe}.md"
    txt_path = REPORT_DIR / f"{safe}.txt"
    md_path.write_text(markdown, encoding="utf-8")
    txt_path.write_text(plain, encoding="utf-8")
    return str(md_path), str(txt_path), markdown

