import { ArrowRight, Check, ChevronDown, CirclePause, X } from "lucide-react";

import type { GuidedDemoTask, TaskId, TaskSummary } from "@/lib/agent-api";
import { titleCase } from "@/lib/orchestration-presentation";

interface RecentRunsProps {
  disabled: boolean;
  missions: GuidedDemoTask[];
  tasks: TaskSummary[];
  onOpen: (taskId: TaskId) => void;
}

function StatusIcon({ status }: { status: TaskSummary["status"] }) {
  if (status === "completed") return <Check size={15} aria-hidden="true" />;
  if (status === "waiting_for_approval" || status === "running") {
    return <CirclePause size={15} aria-hidden="true" />;
  }
  return <X size={15} aria-hidden="true" />;
}

export function RecentRuns({ disabled, missions, tasks, onOpen }: RecentRunsProps) {
  return (
    <details className="recent-runs">
      <summary>
        <span><b>Recent runs</b> Session history · {tasks.length}</span>
        <ChevronDown size={18} aria-hidden="true" />
      </summary>
      <div className="run-list">
        {tasks.length ? tasks.map((task) => {
          const mission = missions.find((item) => item.user_request === task.user_request);
          return (
            <button disabled={disabled} key={task.task_id} onClick={() => onOpen(task.task_id)} type="button">
              <span className={`history-state history-state-${task.status}`}><StatusIcon status={task.status} /> {titleCase(task.status)}</span>
              <span>
                <strong>{mission?.title ?? task.user_request}</strong>
                <small>
                  {task.task_id} · {task.tools_used} tools
                  {task.approval_status ? ` · approval ${task.approval_status}` : ""}
                </small>
              </span>
              <time>{new Date(task.updated_at).toLocaleString()}</time>
              <span className="open-run">Open run <ArrowRight size={14} aria-hidden="true" /></span>
            </button>
          );
        }) : <p>No missions have been run in this session.</p>}
      </div>
    </details>
  );
}
