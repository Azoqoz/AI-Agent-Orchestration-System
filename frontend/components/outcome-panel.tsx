import { Check, FileText, ShieldX, X } from "lucide-react";

import type { TaskDetail } from "@/lib/agent-api";
import { outcomeFields, titleCase } from "@/lib/orchestration-presentation";

export function OutcomePanel({ task }: { task: TaskDetail }) {
  if (task.workflow.waiting_for_approval) return null;
  const showOutcome =
    task.workflow.is_terminal ||
    Boolean(task.final_response || task.error || task.unsupported_actions.length);
  if (!showOutcome) return null;

  const guardrail = task.unsupported_actions.length > 0;
  const rejected = task.workflow.status === "rejected";
  const fields = outcomeFields(task);
  const title = guardrail
    ? "Action blocked before execution"
    : rejected
      ? "Decision declined"
      : task.workflow.status === "completed"
        ? "Mission complete"
        : "Mission stopped";

  return (
    <section className={`outcome outcome-${guardrail ? "guardrail" : task.workflow.status}`} aria-labelledby="outcome-heading">
      <header>
        <span className="outcome-icon" aria-hidden="true">
          {guardrail ? <ShieldX /> : task.workflow.status === "completed" ? <Check /> : <X />}
        </span>
        <div>
          <p className="section-label">Outcome</p>
          <h2 id="outcome-heading">{title}</h2>
        </div>
      </header>

      {guardrail ? (
        <div className="guardrail-statement">
          <p>The request crossed a protected operational boundary.</p>
          <ul>
            <li>No tools executed</li>
            <li>No refund was issued</li>
            <li>No customer message was dispatched</li>
          </ul>
          <dl><dt>Blocked actions</dt><dd>{task.unsupported_actions.join(", ")}</dd></dl>
        </div>
      ) : null}

      {fields.length ? (
        <dl className="outcome-fields">
          {fields.map((field) => (
            <div key={`${field.label}-${field.value}`}><dt>{field.label}</dt><dd>{field.value}</dd></div>
          ))}
        </dl>
      ) : null}

      <div className="outcome-records">
        {task.final_response ? <div><span>Agent response</span><p>{task.final_response}</p></div> : null}
        {task.error ? <div className="error-record"><span>{titleCase(task.error.code)}</span><p>{task.error.message}</p></div> : null}
        {task.generated_report_path ? (
          <div><span><FileText size={15} aria-hidden="true" /> Report artifact</span><code>{task.generated_report_path}</code></div>
        ) : null}
        {task.customer_response ? <div><span>Prepared customer response</span><p>{task.customer_response}</p></div> : null}
        {rejected && task.generated_report_path && !task.customer_response ? (
          <div><span>Decision effect</span><p>The audit report was created. The customer response step was skipped and nothing was sent.</p></div>
        ) : null}
      </div>
    </section>
  );
}
