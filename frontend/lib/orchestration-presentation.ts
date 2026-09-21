import type {
  PlanStep,
  TaskDetail,
  ToolExecutionResult,
} from "@/lib/agent-api";

export type PathState =
  | "complete"
  | "approval"
  | "active"
  | "blocked"
  | "failed"
  | "queued";

export interface ReadableField {
  label: string;
  value: string;
}

const HIDDEN_FIELDS = new Set([
  "task_id",
  "step_id",
  "status",
  "error",
  "error_message",
]);

export function titleCase(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function displayValue(value: unknown): string | null {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return new Intl.NumberFormat().format(value);
  if (typeof value === "string") return value;
  if (
    Array.isArray(value) &&
    value.every((entry) => ["string", "number", "boolean"].includes(typeof entry))
  ) {
    return value.map(String).join(", ");
  }
  return null;
}

export function readableFields(
  payload: Record<string, unknown>,
  limit = 8,
): ReadableField[] {
  const fields: ReadableField[] = [];
  for (const [key, rawValue] of Object.entries(payload)) {
    if (HIDDEN_FIELDS.has(key)) continue;
    const value = displayValue(rawValue);
    if (!value || value.length > 240) continue;
    fields.push({ label: titleCase(key), value });
    if (fields.length === limit) break;
  }
  return fields;
}

export function resultForStep(
  task: TaskDetail,
  stepId: string,
): ToolExecutionResult | undefined {
  return task.tool_results.find((result) => result.step_id === stepId);
}

export function pathState(step: PlanStep, task: TaskDetail): PathState {
  if (step.status === "completed") return "complete";
  if (
    step.status === "waiting_for_approval" ||
    (task.workflow.waiting_for_approval && task.workflow.current_step_id === step.step_id)
  ) {
    return "approval";
  }
  if (step.status === "running" || step.status === "approved") return "active";
  if (step.status === "failed") return "failed";
  if (step.status === "rejected" || step.status === "skipped") return "blocked";
  return "queued";
}

export function outcomeFields(task: TaskDetail): ReadableField[] {
  const preferred = [
    "refund_eligible",
    "eligible",
    "recommended_refund",
    "refund_amount",
    "priority",
    "sla_remaining",
    "hours_remaining",
    "risk_level",
    "customer_name",
    "case_type",
  ];
  const values = new Map<string, ReadableField>();
  for (const result of task.tool_results) {
    for (const [key, rawValue] of Object.entries(result.payload)) {
      if (values.has(key) || HIDDEN_FIELDS.has(key)) continue;
      const value = displayValue(rawValue);
      if (!value || value.length > 120) continue;
      values.set(key, { label: titleCase(key), value });
    }
  }
  const ordered: ReadableField[] = [];
  for (const key of preferred) {
    const field = values.get(key);
    if (field) ordered.push(field);
  }
  for (const field of values.values()) {
    if (!ordered.includes(field)) ordered.push(field);
  }
  return ordered.slice(0, 6);
}
