import {
  ArrowDown,
  Check,
  ChevronRight,
  CirclePause,
  Clock3,
  LockKeyhole,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type {
  PendingApproval,
  PlanStep,
  TaskDetail,
  ToolExecutionResult,
} from "@/lib/agent-api";
import {
  pathState,
  readableFields,
  resultForStep,
  titleCase,
  type PathState,
} from "@/lib/orchestration-presentation";

interface OrchestrationCanvasProps {
  task: TaskDetail;
  pendingApproval: PendingApproval | null;
  reviewerNote: string;
  selectedStepId: string | null;
  working: boolean;
  onDecision: (decision: "approved" | "rejected") => void;
  onReviewerNote: (note: string) => void;
  onSelectStep: (stepId: string) => void;
}

function stateIcon(state: PathState) {
  if (state === "complete") return <Check size={16} aria-hidden="true" />;
  if (state === "approval" || state === "active") {
    return <CirclePause size={16} aria-hidden="true" />;
  }
  if (state === "failed" || state === "blocked") {
    return <X size={16} aria-hidden="true" />;
  }
  return <LockKeyhole size={15} aria-hidden="true" />;
}

function StepInspector({
  result,
  step,
}: {
  result: ToolExecutionResult | undefined;
  step: PlanStep | undefined;
}) {
  if (!step) {
    return (
      <aside className="step-inspector inspector-empty">
        <span>Step inspector</span>
        <p>Select a completed movement to inspect its evidence.</p>
      </aside>
    );
  }

  const fields = result ? readableFields(result.payload) : [];
  return (
    <aside className="step-inspector" aria-live="polite">
      <div className="inspector-title">
        <span>Movement {step.step_id}</span>
        <h2>{step.description}</h2>
        <code>{step.tool_name}</code>
      </div>
      <dl className="inspector-facts">
        <div><dt>Status</dt><dd>{titleCase(result?.status ?? step.status)}</dd></div>
        <div><dt>Latency</dt><dd>{result?.latency_ms === null || result?.latency_ms === undefined ? "—" : `${result.latency_ms} ms`}</dd></div>
        <div><dt>Dependencies</dt><dd>{step.depends_on.length ? step.depends_on.join(", ") : "None"}</dd></div>
      </dl>
      {fields.length ? (
        <dl className="readable-output">
          {fields.map((field) => (
            <div key={field.label}><dt>{field.label}</dt><dd>{field.value}</dd></div>
          ))}
        </dl>
      ) : (
        <p className="inspector-no-output">No human-readable output is available for this movement yet.</p>
      )}
      <details className="raw-data">
        <summary>Raw tool input</summary>
        <pre>{JSON.stringify(step.inputs, null, 2)}</pre>
      </details>
      {result ? (
        <details className="raw-data">
          <summary>Raw tool output</summary>
          <pre>{JSON.stringify(result.payload, null, 2)}</pre>
        </details>
      ) : null}
    </aside>
  );
}

export function OrchestrationCanvas({
  task,
  pendingApproval,
  reviewerNote,
  selectedStepId,
  working,
  onDecision,
  onReviewerNote,
  onSelectStep,
}: OrchestrationCanvasProps) {
  const steps = task.plan?.steps ?? [];
  const selectedStep = steps.find((step) => step.step_id === selectedStepId);
  const selectedResult = selectedStep
    ? resultForStep(task, selectedStep.step_id)
    : undefined;
  const completedCount = steps.filter((step) => step.status === "completed").length;
  const firstInspectable = steps.find((step) => resultForStep(task, step.step_id));
  const inspectorStep = selectedStep ?? firstInspectable;
  const inspectorResult = inspectorStep
    ? resultForStep(task, inspectorStep.step_id)
    : undefined;

  return (
    <section className="orchestration-section" aria-labelledby="path-heading">
      <header className="run-heading">
        <div>
          <button className="task-id" onClick={() => navigator.clipboard?.writeText(task.task_id)} type="button">
            {task.task_id}
          </button>
          <p>{task.user_request}</p>
        </div>
        <dl>
          <div><dt>Plan</dt><dd>{task.plan?.task_type ? titleCase(task.plan.task_type) : "No executable plan"}</dd></div>
          <div><dt>Progress</dt><dd>{completedCount}/{steps.length}</dd></div>
          <div className={`run-status run-status-${task.workflow.status}`}><dt>Status</dt><dd>{titleCase(task.workflow.status)}</dd></div>
        </dl>
      </header>

      {steps.length ? (
        <div className="canvas-layout">
          <div className="path-column">
            <div className="path-label">
              <p className="section-label">Execution path</p>
              <span>Plan → tools → decision → outcome</span>
            </div>
            <ol className="execution-path" aria-labelledby="path-heading">
              {steps.map((step, index) => {
                const result = resultForStep(task, step.step_id);
                const isSelected = inspectorStep?.step_id === step.step_id;
                const approvalRecord = [...task.approvals]
                  .reverse()
                  .find((approval) => approval.step_id === step.step_id);
                const state = approvalRecord
                  ? approvalRecord.decision === "approved"
                    ? "complete"
                    : "blocked"
                  : pathState(step, task);
                const activeApproval =
                  task.workflow.waiting_for_approval &&
                  task.workflow.current_step_id === step.step_id &&
                  pendingApproval?.task_id === task.task_id &&
                  pendingApproval.step_id === step.step_id;
                return (
                  <li className={`path-step path-step-${state}`} key={step.step_id}>
                    <button
                      aria-current={isSelected ? "step" : undefined}
                      disabled={!result}
                      onClick={() => onSelectStep(step.step_id)}
                      type="button"
                    >
                      <span className="path-node">{stateIcon(state)}</span>
                      <span className="path-number">{String(index + 1).padStart(2, "0")}</span>
                      <span className="path-copy">
                        <strong>{step.description}</strong>
                        <code>{step.tool_name}</code>
                        <small>{step.reason}</small>
                      </span>
                      <span className="path-state">
                        {titleCase(state === "queued" ? step.status : state)}
                        {result?.latency_ms !== null && result?.latency_ms !== undefined ? (
                          <small><Clock3 size={12} aria-hidden="true" /> {result.latency_ms} ms</small>
                        ) : null}
                      </span>
                      {result ? <ChevronRight size={17} aria-hidden="true" /> : null}
                    </button>

                    {activeApproval ? (
                      <div className="approval-checkpoint">
                        <div className="approval-marker">
                          <ArrowDown size={18} aria-hidden="true" /> Human checkpoint
                        </div>
                        <div className="approval-body">
                          <div>
                            <p className="section-label">Decision required</p>
                            <h2>{pendingApproval.description}</h2>
                            <p>{pendingApproval.reason}</p>
                          </div>
                          {pendingApproval.recommended_action || task.recommended_action ? (
                            <blockquote>
                              <span>Agent recommendation</span>
                              {pendingApproval.recommended_action ?? task.recommended_action}
                            </blockquote>
                          ) : null}
                          <label className="review-note" htmlFor="reviewer-note">
                            <span>Reviewer note <small>optional · recorded in audit</small></span>
                            <Textarea
                              id="reviewer-note"
                              onChange={(event) => onReviewerNote(event.target.value)}
                              placeholder="Add decision context…"
                              value={reviewerNote}
                            />
                          </label>
                          <div className="approval-actions">
                            <Button className="reject-action" disabled={working} onClick={() => onDecision("rejected")} variant="outline">
                              Reject mission
                            </Button>
                            <Button className="primary-action" disabled={working} onClick={() => onDecision("approved")}>
                              {working ? "Recording decision…" : "Approve & resume"}
                              <ChevronRight size={17} aria-hidden="true" />
                            </Button>
                          </div>
                        </div>
                      </div>
                    ) : null}
                    {!activeApproval && approvalRecord ? (
                      <div className={`approval-history approval-history-${approvalRecord.decision}`}>
                        <span>Human decision</span>
                        <strong>{titleCase(approvalRecord.decision)}</strong>
                        {approvalRecord.reviewer_note ? (
                          <p><b>Reviewer note</b>{approvalRecord.reviewer_note}</p>
                        ) : null}
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ol>
          </div>
          <StepInspector result={selectedResult ?? inspectorResult} step={selectedStep ?? inspectorStep} />
        </div>
      ) : (
        <div className="empty-path">
          <span>No tool path was opened.</span>
          <p>The safety layer resolved this mission before execution.</p>
        </div>
      )}
    </section>
  );
}
