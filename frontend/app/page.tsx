"use client";

import {
  type CSSProperties,
  type SubmitEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  ChevronDown,
  CirclePause,
  Clock3,
  FileText,
  History,
  Inspect,
  LoaderCircle,
  LockKeyhole,
  Plus,
  ShieldCheck,
  WifiOff,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  AgentApiError,
  agentApi,
  type Capabilities,
  type PendingApproval,
  type PlanStep,
  type PlannerMode,
  type ProviderName,
  type TaskDetail,
  type TaskId,
  type TaskSummary,
  type ToolExecutionResult,
} from "@/lib/agent-api";

type ApiAvailability = "checking" | "available" | "unavailable";
type ScoreVisualStatus =
  | "completed"
  | "waiting"
  | "pending"
  | "running"
  | "failed"
  | "skipped";
type EvidenceKind = "success" | "refund" | "sla" | "priority" | "generic";

interface OperationalError {
  code: string | null;
  message: string;
}

interface EvidenceMetric {
  key: string;
  label: string;
  value: string;
  kind: EvidenceKind;
}

const RECENT_TASK_LIMIT = 5;

const preferredEvidenceKeys = [
  "refund_eligible",
  "eligible",
  "eligibility_status",
  "recommended_refund",
  "refund_amount",
  "sla_remaining",
  "hours_remaining",
  "sla_risk",
  "priority",
  "urgency",
] as const;

const excludedEvidenceKeys = new Set([
  "task_id",
  "step_id",
  "case_id",
  "customer_id",
  "currency",
  "status",
  "error",
  "error_message",
  "message",
  "report_path",
  "generated_report_path",
  "customer_response",
]);

function formatIdentifier(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatStatus(status: string): string {
  return formatIdentifier(status);
}

function toOperationalError(error: unknown, fallback: string): OperationalError {
  if (error instanceof AgentApiError) {
    return { code: error.code, message: error.message };
  }
  return { code: null, message: fallback };
}

function visualStatusForStep(
  step: PlanStep,
  currentStepId: string | null,
): ScoreVisualStatus {
  if (step.status === "completed") return "completed";
  if (
    step.status === "waiting_for_approval" ||
    (step.requires_approval && step.step_id === currentStepId)
  ) {
    return "waiting";
  }
  if (step.status === "failed") return "failed";
  if (step.status === "rejected" || step.status === "skipped") return "skipped";
  if (step.status === "running" || step.status === "approved") return "running";
  return "pending";
}

function stepStatusIcon(status: ScoreVisualStatus) {
  if (status === "completed") return <Check size={14} aria-hidden="true" />;
  if (status === "waiting" || status === "running") {
    return <CirclePause size={14} aria-hidden="true" />;
  }
  if (status === "failed" || status === "skipped") {
    return <X size={13} aria-hidden="true" />;
  }
  return <LockKeyhole size={13} aria-hidden="true" />;
}

function primitiveEvidenceValue(value: unknown): string | null {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }
  if (
    Array.isArray(value) &&
    value.every((item) =>
      ["string", "number", "boolean"].includes(typeof item),
    )
  ) {
    return value.join(", ");
  }
  return null;
}

function evidenceKindForKey(key: string): EvidenceKind {
  if (key.includes("eligible") || key.includes("eligibility")) return "success";
  if (key.includes("refund") || key.includes("amount")) return "refund";
  if (key.includes("sla") || key.includes("hours") || key.includes("time")) {
    return "sla";
  }
  if (key.includes("priority") || key.includes("risk") || key.includes("urgency")) {
    return "priority";
  }
  return "generic";
}

function evidenceFromResults(results: ToolExecutionResult[]): EvidenceMetric[] {
  const candidates = new Map<string, EvidenceMetric>();

  for (const result of results) {
    for (const [key, rawValue] of Object.entries(result.payload)) {
      if (excludedEvidenceKeys.has(key) || candidates.has(key)) continue;

      let value = primitiveEvidenceValue(rawValue);
      if (value === null || value.length > 80) continue;

      const currency = result.payload.currency;
      if (
        (key.includes("refund") || key.includes("amount")) &&
        typeof currency === "string" &&
        !value.includes(currency)
      ) {
        value = `${currency} ${value}`;
      }

      candidates.set(key, {
        key,
        label: formatIdentifier(key),
        value,
        kind: evidenceKindForKey(key),
      });
    }
  }

  const ordered: EvidenceMetric[] = [];
  for (const key of preferredEvidenceKeys) {
    const metric = candidates.get(key);
    if (metric) ordered.push(metric);
  }
  for (const metric of candidates.values()) {
    if (!ordered.some((item) => item.key === metric.key)) ordered.push(metric);
  }

  return ordered.slice(0, 4);
}

function resultForStep(
  results: ToolExecutionResult[],
  stepId: string,
): ToolExecutionResult | undefined {
  return results.find((result) => result.step_id === stepId);
}

function historyIcon(status: TaskSummary["status"]) {
  if (status === "completed") return <Check size={14} aria-hidden="true" />;
  if (status === "waiting_for_approval" || status === "running") {
    return <CirclePause size={14} aria-hidden="true" />;
  }
  return <X size={14} aria-hidden="true" />;
}

export default function Home() {
  const [apiAvailability, setApiAvailability] =
    useState<ApiAvailability>("checking");
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [recentTasks, setRecentTasks] = useState<TaskSummary[]>([]);
  const [currentTask, setCurrentTask] = useState<TaskDetail | null>(null);
  const [pendingApproval, setPendingApproval] =
    useState<PendingApproval | null>(null);
  const [operationalError, setOperationalError] =
    useState<OperationalError | null>(null);
  const [isWorking, setIsWorking] = useState(false);
  const [isTaskFormOpen, setIsTaskFormOpen] = useState(true);
  const [selectedResultStepId, setSelectedResultStepId] = useState<string | null>(
    null,
  );

  const [userRequest, setUserRequest] = useState("");
  const [plannerMode, setPlannerMode] =
    useState<PlannerMode>("deterministic");
  const [provider, setProvider] = useState<ProviderName | "">("");
  const [model, setModel] = useState("");
  const [providerApiKey, setProviderApiKey] = useState("");
  const [reviewerNote, setReviewerNote] = useState("");

  const refreshHistory = useCallback(async () => {
    const tasks = await agentApi.listTasks({ limit: RECENT_TASK_LIMIT });
    setRecentTasks(tasks);
    return tasks;
  }, []);

  const syncPendingApproval = useCallback(async (task: TaskDetail) => {
    if (!task.workflow.waiting_for_approval) {
      setPendingApproval(null);
      return;
    }
    const approval = await agentApi.getPendingApproval(task.task_id);
    setPendingApproval(approval);
  }, []);

  const loadTask = useCallback(
    async (taskId: TaskId) => {
      setIsWorking(true);
      setOperationalError(null);
      setSelectedResultStepId(null);
      try {
        const task = await agentApi.getTask(taskId);
        setCurrentTask(task);
        setIsTaskFormOpen(false);
        await syncPendingApproval(task);
      } catch (error) {
        setOperationalError(
          toOperationalError(error, "The selected task could not be loaded."),
        );
      } finally {
        setIsWorking(false);
      }
    },
    [syncPendingApproval],
  );

  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    async function initialize() {
      const options = { signal: controller.signal };
      const [healthResult, capabilitiesResult, tasksResult] =
        await Promise.allSettled([
          agentApi.getHealth(options),
          agentApi.getCapabilities(options),
          agentApi.listTasks({ limit: RECENT_TASK_LIMIT }, options),
        ]);

      if (!active) return;

      if (healthResult.status === "fulfilled") {
        setApiAvailability("available");
      } else {
        setApiAvailability("unavailable");
        setOperationalError(
          toOperationalError(
            healthResult.reason,
            "The agent API is currently unavailable.",
          ),
        );
      }

      if (capabilitiesResult.status === "fulfilled") {
        const loadedCapabilities = capabilitiesResult.value;
        setCapabilities(loadedCapabilities);
        setPlannerMode((current) =>
          loadedCapabilities.planner_modes.includes(current)
            ? current
            : (loadedCapabilities.planner_modes[0] ?? "deterministic"),
        );
      } else if (healthResult.status === "fulfilled") {
        setOperationalError(
          toOperationalError(
            capabilitiesResult.reason,
            "Agent capabilities could not be loaded.",
          ),
        );
      }

      if (tasksResult.status === "fulfilled") {
        const tasks = tasksResult.value;
        setRecentTasks(tasks);

        if (tasks.length > 0) {
          try {
            const task = await agentApi.getTask(tasks[0].task_id, options);
            if (!active) return;
            setCurrentTask(task);
            setIsTaskFormOpen(false);
            if (task.workflow.waiting_for_approval) {
              const approval = await agentApi.getPendingApproval(
                task.task_id,
                options,
              );
              if (active) setPendingApproval(approval);
            }
          } catch (error) {
            if (active) {
              setOperationalError(
                toOperationalError(
                  error,
                  "The most recent task could not be loaded.",
                ),
              );
            }
          }
        }
      } else if (healthResult.status === "fulfilled") {
        setOperationalError(
          toOperationalError(
            tasksResult.reason,
            "Recent task history could not be loaded.",
          ),
        );
      }
    }

    void initialize();
    return () => {
      active = false;
      controller.abort();
    };
  }, []);

  const selectedProviderCapability = useMemo(
    () => capabilities?.providers.find((item) => item.name === provider) ?? null,
    [capabilities, provider],
  );
  const selectedResult = useMemo(
    () =>
      selectedResultStepId && currentTask
        ? resultForStep(currentTask.tool_results, selectedResultStepId)
        : undefined,
    [currentTask, selectedResultStepId],
  );
  const approvalEvidence = useMemo(
    () => (currentTask ? evidenceFromResults(currentTask.tool_results) : []),
    [currentTask],
  );

  const currentPlanSteps = currentTask?.plan?.steps ?? [];
  const scoreStyle = {
    "--score-step-count": Math.max(currentPlanSteps.length, 1),
  } as CSSProperties;
  const apiLabel =
    apiAvailability === "checking"
      ? "Checking API"
      : apiAvailability === "available"
        ? "API available"
        : "API unavailable";
  const headerStatus = currentTask
    ? formatStatus(currentTask.workflow.status)
    : apiLabel;

  async function handleTaskSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!userRequest.trim() || !capabilities) return;

    setIsWorking(true);
    setOperationalError(null);
    setSelectedResultStepId(null);

    try {
      const task = await agentApi.startTask(
        {
          user_request: userRequest.trim(),
          planner_mode: plannerMode,
          provider: plannerMode === "llm" && provider ? provider : null,
          model: plannerMode === "llm" && model.trim() ? model.trim() : null,
        },
        { providerApiKey: providerApiKey || undefined },
      );
      setCurrentTask(task);
      setIsTaskFormOpen(false);
      setUserRequest("");
      setReviewerNote("");
      await syncPendingApproval(task);
      await refreshHistory();
    } catch (error) {
      setOperationalError(
        toOperationalError(error, "The task could not be started."),
      );
    } finally {
      setProviderApiKey("");
      setIsWorking(false);
    }
  }

  async function handleApprovalDecision(decision: "approved" | "rejected") {
    if (!currentTask) return;
    setIsWorking(true);
    setOperationalError(null);
    try {
      const task = await agentApi.decideApproval(currentTask.task_id, {
        decision,
        reviewer_note: reviewerNote.trim() || null,
      });
      setCurrentTask(task);
      setPendingApproval(null);
      setReviewerNote("");
      await refreshHistory();
    } catch (error) {
      setOperationalError(
        toOperationalError(error, "The approval decision could not be saved."),
      );
    } finally {
      setIsWorking(false);
    }
  }

  function handlePlannerChange(nextPlanner: PlannerMode) {
    setPlannerMode(nextPlanner);
    if (nextPlanner === "deterministic") {
      setProvider("");
      setModel("");
      setProviderApiKey("");
      return;
    }
    if (!provider) setProvider(capabilities?.providers[0]?.name ?? "");
  }

  const taskHasResult = Boolean(
    currentTask &&
      !currentTask.workflow.waiting_for_approval &&
      (currentTask.workflow.is_terminal ||
        currentTask.final_response ||
        currentTask.generated_report_path ||
        currentTask.customer_response ||
        currentTask.error ||
        currentTask.unsupported_actions.length > 0),
  );

  return (
    <main className="min-h-screen bg-[var(--paper)] text-[var(--ink)]">
      <header className="utility-bar">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <span>Conductor</span>
          <span className="brand-subtitle">AI Agent Orchestration</span>
        </div>

        <dl className="run-facts" aria-label="Workflow facts">
          <div><dt>Task</dt><dd>{currentTask?.task_id ?? "No task"}</dd></div>
          <div>
            <dt>Planner</dt>
            <dd>{formatStatus(currentTask?.planner_mode ?? plannerMode)}</dd>
          </div>
          <div><dt>Provider</dt><dd>{currentTask?.provider ?? (provider || "None")}</dd></div>
          <div className="status-fact"><dt>Status</dt><dd>{headerStatus}</dd></div>
        </dl>

        <button
          className="history-link"
          onClick={() => document.getElementById("history-heading")?.scrollIntoView({ behavior: "smooth" })}
          type="button"
        >
          <History size={15} aria-hidden="true" />
          Repertoire
          <span>{recentTasks.length}</span>
        </button>
      </header>

      <section className="task-brief" aria-labelledby="task-heading">
        <div className="section-kicker">
          <span>{currentTask && !isTaskFormOpen ? "Current task" : "Task intake"}</span>
          <span>
            {capabilities ? `${formatStatus(capabilities.app_mode)} mode` : "Capabilities pending"}
          </span>
        </div>
        <div className="task-copy">
          <p id="task-heading">
            {currentTask && !isTaskFormOpen
              ? currentTask.user_request
              : currentTask
                ? "Define the next task for the agent to orchestrate."
                : "No task is selected. Enter a supported operation to begin."}
          </p>

          <div className="task-signals" aria-label="Task operational signals">
            <span className={apiAvailability === "unavailable" ? "signal-error" : ""}>
              {apiAvailability === "checking" && <LoaderCircle className="spin" size={14} aria-hidden="true" />}
              {apiAvailability === "available" && <ShieldCheck size={14} aria-hidden="true" />}
              {apiAvailability === "unavailable" && <WifiOff size={14} aria-hidden="true" />}
              {apiLabel}
            </span>
            {currentTask?.unsupported_actions.length ? (
              <span className="signal-error">Unsupported action blocked</span>
            ) : currentTask?.plan ? <span>Supported workflow</span> : null}
            {currentTask?.plan ? <span>{currentTask.plan.steps.length} planned movements</span> : null}
            {currentTask && !isTaskFormOpen ? (
              <button className="new-task-link" onClick={() => setIsTaskFormOpen(true)} type="button">
                <Plus size={13} aria-hidden="true" /> Start another task
              </button>
            ) : null}
          </div>

          {isTaskFormOpen ? (
            <form className="task-intake" onSubmit={handleTaskSubmit}>
              <div className="task-request-field">
                <label htmlFor="user-request">User request</label>
                <Textarea
                  id="user-request"
                  onChange={(event) => setUserRequest(event.target.value)}
                  placeholder="Describe the operation for the agent…"
                  required
                  value={userRequest}
                />
              </div>

              <div className="task-config-grid">
                <label>
                  <span>Planner</span>
                  <select
                    disabled={!capabilities || isWorking}
                    onChange={(event) => handlePlannerChange(event.target.value as PlannerMode)}
                    value={plannerMode}
                  >
                    {(capabilities?.planner_modes ?? ["deterministic"]).map((mode) => (
                      <option key={mode} value={mode}>{formatStatus(mode)}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Provider</span>
                  <select
                    disabled={plannerMode !== "llm" || isWorking}
                    onChange={(event) => {
                      setProvider(event.target.value as ProviderName | "");
                      setProviderApiKey("");
                    }}
                    value={provider}
                  >
                    <option value="">None</option>
                    {(capabilities?.providers ?? []).map((item) => (
                      <option key={item.name} value={item.name}>{formatStatus(item.name)}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Model · optional</span>
                  <input
                    disabled={plannerMode !== "llm" || isWorking}
                    onChange={(event) => setModel(event.target.value)}
                    placeholder={selectedProviderCapability?.default_model ?? "Default model"}
                    type="text"
                    value={model}
                  />
                </label>
                <label>
                  <span>Provider API key · optional</span>
                  <input
                    autoComplete="off"
                    disabled={plannerMode !== "llm" || isWorking}
                    onChange={(event) => setProviderApiKey(event.target.value)}
                    placeholder={selectedProviderCapability?.requires_api_key ? "Required by provider" : "Not required"}
                    type="password"
                    value={providerApiKey}
                  />
                </label>
              </div>

              <div className="task-submit-row">
                {currentTask ? (
                  <button className="cancel-task-link" onClick={() => setIsTaskFormOpen(false)} type="button">
                    Return to current task
                  </button>
                ) : (
                  <span>{capabilities ? `${formatStatus(capabilities.app_mode)} capabilities loaded` : "Waiting for capabilities"}</span>
                )}
                <Button
                  className="approve-button"
                  disabled={isWorking || apiAvailability !== "available" || !capabilities || !userRequest.trim()}
                  type="submit"
                >
                  {isWorking ? "Starting…" : "Start task"}
                  <ArrowRight size={16} aria-hidden="true" />
                </Button>
              </div>
            </form>
          ) : null}

          {operationalError ? (
            <div className="operational-message operational-message-error" role="alert">
              <AlertTriangle size={16} aria-hidden="true" />
              <span>
                {operationalError.code ? <b>{formatIdentifier(operationalError.code)} · </b> : null}
                {operationalError.message}
              </span>
            </div>
          ) : null}
        </div>
      </section>

      <section className="score-section" aria-labelledby="score-heading">
        <div className="score-header">
          <div><p className="eyebrow">Execution score</p><h1 id="score-heading">From evidence to action</h1></div>
          <div className="legend" aria-label="Status legend">
            <span><i className="legend-complete" /> Complete</span>
            <span><i className="legend-active" /> Active gate</span>
            <span><i className="legend-blocked" /> Pending / blocked</span>
          </div>
        </div>

        {currentPlanSteps.length > 0 ? (
          <ol
            className={`score ${currentPlanSteps.length === 6 ? "" : "score-variable"}`}
            style={scoreStyle}
            aria-label={`${currentPlanSteps.length}-step execution plan`}
          >
            {currentPlanSteps.map((step, index) => {
              const visualStatus = visualStatusForStep(step, currentTask?.workflow.current_step_id ?? null);
              const result = currentTask ? resultForStep(currentTask.tool_results, step.step_id) : undefined;
              const inspectorOpen = selectedResultStepId === step.step_id;
              return (
                <li className={`score-step score-step-${visualStatus} ${result ? "score-step-inspectable" : ""}`} key={step.step_id}>
                  <div className="playhead" aria-hidden="true" />
                  <div className="step-topline">
                    <span className="step-number">{String(index + 1).padStart(2, "0")}</span>
                    <span className="step-state">{stepStatusIcon(visualStatus)}{formatStatus(step.status)}</span>
                  </div>
                  <div className="step-body">
                    <h2>{step.description}</h2>
                    <code>{step.tool_name}</code>
                    <p>{step.reason}</p>
                  </div>
                  <div className="step-foot">
                    {step.depends_on.length > 0 ? (
                      <span className="dependency"><ArrowRight size={12} aria-hidden="true" /><b>After</b> {step.depends_on.join(", ")}</span>
                    ) : <span className="dependency dependency-none">No dependencies</span>}
                    <span className="duration">
                      <Clock3 size={12} aria-hidden="true" />
                      {result?.latency_ms !== null && result?.latency_ms !== undefined ? `${result.latency_ms} ms` : formatStatus(step.status)}
                    </span>
                  </div>
                  {result ? (
                    <button
                      aria-expanded={inspectorOpen}
                      className="inspect-trigger"
                      onClick={() => setSelectedResultStepId((openStepId) => openStepId === step.step_id ? null : step.step_id)}
                      type="button"
                    >
                      <Inspect size={15} aria-hidden="true" /> Inspect output
                      <ChevronDown className={inspectorOpen ? "rotate" : ""} size={15} aria-hidden="true" />
                    </button>
                  ) : null}
                </li>
              );
            })}
          </ol>
        ) : (
          <div className="score-empty">
            {apiAvailability === "checking" ? "Checking the orchestration service…" : currentTask ? "This task has no executable plan." : "No execution plan is active."}
          </div>
        )}

        {selectedResult ? (
          <section className="output-inspector" aria-labelledby="inspector-heading">
            <div className="inspector-heading">
              <div><p className="eyebrow">Tool output · {selectedResult.step_id ?? "Workflow"}</p><h2 id="inspector-heading">{selectedResult.tool_name}</h2></div>
              <button onClick={() => setSelectedResultStepId(null)} type="button"><X size={16} aria-hidden="true" /> Close</button>
            </div>
            <dl className="calculation-grid">
              <div><dt>Status</dt><dd>{formatStatus(selectedResult.status)}</dd></div>
              {selectedResult.step_id ? <div><dt>Step</dt><dd>{selectedResult.step_id}</dd></div> : null}
              {selectedResult.latency_ms !== null ? <div><dt>Latency</dt><dd>{selectedResult.latency_ms} ms</dd></div> : null}
              {selectedResult.error_message ? <div className="calculation-total"><dt>Error</dt><dd>{selectedResult.error_message}</dd></div> : null}
            </dl>
            <div className="output-meta">
              <span>{Object.keys(selectedResult.payload).length} structured output fields</span>
              <details><summary>Structured payload</summary><pre>{JSON.stringify(selectedResult.payload, null, 2)}</pre></details>
            </div>
          </section>
        ) : null}
      </section>

      {currentTask?.workflow.waiting_for_approval && pendingApproval ? (
        <section className="approval-band approval-waiting" aria-labelledby="approval-heading">
          <div className="approval-rail"><CirclePause size={22} aria-hidden="true" /><span>Human decision required</span></div>
          <div className="approval-content">
            <div className="approval-title">
              <p className="eyebrow">Approval gate · {pendingApproval.step_id} · {pendingApproval.tool_name}</p>
              <h2 id="approval-heading">{pendingApproval.description}</h2>
              <p>{pendingApproval.reason}</p>
            </div>
            {approvalEvidence.length > 0 ? (
              <dl className="evidence-strip" aria-label="Approval evidence">
                {approvalEvidence.map((metric) => (
                  <div className={`evidence-metric evidence-metric-${metric.kind}`} key={metric.key}>
                    <dt>{metric.label}</dt><dd>{metric.value}</dd>
                  </div>
                ))}
              </dl>
            ) : null}
            {pendingApproval.recommended_action || currentTask.recommended_action ? (
              <div className="recommendation"><span>Agent recommendation</span><p>{pendingApproval.recommended_action ?? currentTask.recommended_action}</p></div>
            ) : null}
            <div className="decision-row">
              <div className="note-field">
                <label htmlFor="review-note">Reviewer note <span>optional</span></label>
                <Textarea id="review-note" onChange={(event) => setReviewerNote(event.target.value)} placeholder="Add context for the audit record…" value={reviewerNote} />
              </div>
              <div className="decision-actions">
                <Button className="reject-button" disabled={isWorking} onClick={() => void handleApprovalDecision("rejected")} variant="outline">Reject task</Button>
                <Button className="approve-button" disabled={isWorking} onClick={() => void handleApprovalDecision("approved")}>{isWorking ? "Saving…" : "Approve & continue"}<ArrowRight size={16} aria-hidden="true" /></Button>
              </div>
            </div>
          </div>
        </section>
      ) : null}

      {currentTask && taskHasResult ? (
        <section className={`task-result task-result-${currentTask.workflow.status}`} aria-labelledby="result-heading">
          <div className="result-heading"><p className="eyebrow">Workflow result</p><h2 id="result-heading">{formatStatus(currentTask.workflow.status)}</h2></div>
          <div className="result-content">
            {currentTask.final_response ? <p>{currentTask.final_response}</p> : null}
            {currentTask.error ? <div className="result-error-copy"><b>{formatIdentifier(currentTask.error.code)}</b><span>{currentTask.error.message}</span></div> : null}
            {currentTask.unsupported_actions.length > 0 ? <dl><dt>Unsupported actions safely blocked</dt><dd>{currentTask.unsupported_actions.join(", ")}</dd></dl> : null}
            {currentTask.generated_report_path ? <dl><dt>Report artifact</dt><dd><code>{currentTask.generated_report_path}</code></dd></dl> : null}
            {currentTask.customer_response ? <dl><dt>Customer response</dt><dd>{currentTask.customer_response}</dd></dl> : null}
          </div>
        </section>
      ) : null}

      <section className="history-ribbon" aria-labelledby="history-heading">
        <div><p className="eyebrow">Task history</p><h2 id="history-heading">Recent repertoire</h2></div>
        <div className="history-list">
          {recentTasks.length > 0 ? recentTasks.map((task) => (
            <button className={`history-entry history-entry-${task.status}`} disabled={isWorking} key={task.task_id} onClick={() => void loadTask(task.task_id)} type="button">
              <span className="history-status">{historyIcon(task.status)} {formatStatus(task.status)}</span>
              <span className="history-task">{task.user_request}</span>
              <span className="history-meta">{task.tools_used} tools · {task.approval_status ?? "no decision"} · {task.updated_at}</span>
              <FileText size={16} aria-hidden="true" />
            </button>
          )) : (
            <p className="history-empty">{apiAvailability === "unavailable" ? "Task history is unavailable while the API is offline." : "No persisted tasks are available yet."}</p>
          )}
        </div>
      </section>

      <footer className="prototype-footer">
        Live FastAPI integration · Provider credentials remain in memory only
      </footer>
    </main>
  );
}
