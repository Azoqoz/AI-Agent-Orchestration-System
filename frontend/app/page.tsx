"use client";

import { useMemo, useState } from "react";
import {
  ArrowRight,
  Check,
  ChevronDown,
  CirclePause,
  Clock3,
  FileText,
  History,
  Inspect,
  LockKeyhole,
  RotateCcw,
  ShieldCheck,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

type Outcome = "waiting" | "approved" | "rejected";
type StepStatus = "completed" | "waiting" | "blocked" | "skipped";

const taskBrief =
  "Review CASE-2026-0417, check refund eligibility and SLA risk, calculate the recommended refund if eligible, then prepare an internal report and customer response.";

const baseSteps = [
  {
    number: "01",
    name: "Case Lookup",
    tool: "lookup_case",
    dependency: null,
    reason: "Establish verified case context",
    duration: "42 ms",
  },
  {
    number: "02",
    name: "Policy Checker",
    tool: "check_refund_eligibility",
    dependency: "Step 01",
    reason: "Confirm policy eligibility",
    duration: "31 ms",
  },
  {
    number: "03",
    name: "Refund Calculator",
    tool: "calculate_refund",
    dependency: "Step 02",
    reason: "Determine the safe refund amount",
    duration: "18 ms",
  },
  {
    number: "04",
    name: "SLA Checker",
    tool: "check_sla_risk",
    dependency: "Step 01",
    reason: "Measure response urgency",
    duration: "24 ms",
  },
  {
    number: "05",
    name: "Generate Report",
    tool: "generate_report",
    dependency: "Steps 02, 03 + 04",
    reason: "Create the internal decision record",
    duration: "Awaiting review",
  },
  {
    number: "06",
    name: "Customer Response",
    tool: "generate_customer_response",
    dependency: "Steps 03 + 05",
    reason: "Prepare an approved customer reply",
    duration: "Not started",
  },
] as const;

function statusForStep(index: number, outcome: Outcome): StepStatus {
  if (index < 4) return "completed";
  if (index === 4) return outcome === "waiting" ? "waiting" : "completed";
  if (outcome === "approved") return "completed";
  if (outcome === "rejected") return "skipped";
  return "blocked";
}

function timingForStep(index: number, outcome: Outcome, defaultValue: string) {
  if (index === 4 && outcome !== "waiting") return outcome === "approved" ? "Report ready · 96 ms" : "Audit retained · 88 ms";
  if (index === 5 && outcome === "approved") return "Response ready · 71 ms";
  if (index === 5 && outcome === "rejected") return "Skipped by decision";
  return defaultValue;
}

const statusLabel: Record<StepStatus, string> = {
  completed: "Completed",
  waiting: "Waiting for approval",
  blocked: "Blocked",
  skipped: "Skipped on rejection",
};

export default function Home() {
  const [outcome, setOutcome] = useState<Outcome>("waiting");
  const [reviewerNote, setReviewerNote] = useState("");
  const [inspectorOpen, setInspectorOpen] = useState(false);

  const workflowStatus = useMemo(() => {
    if (outcome === "approved") return "Completed";
    if (outcome === "rejected") return "Rejected · audit retained";
    return "Waiting for approval";
  }, [outcome]);

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
          <div>
            <dt>Task</dt>
            <dd>TASK-9F7A2C41</dd>
          </div>
          <div>
            <dt>Planner</dt>
            <dd>Deterministic</dd>
          </div>
          <div>
            <dt>Provider</dt>
            <dd>None</dd>
          </div>
          <div className="status-fact">
            <dt>Status</dt>
            <dd>{workflowStatus}</dd>
          </div>
        </dl>

        <button className="history-link" type="button">
          <History size={15} aria-hidden="true" />
          Repertoire
          <span>12</span>
        </button>
      </header>

      <section className="task-brief" aria-labelledby="task-heading">
        <div className="section-kicker">
          <span>Current task</span>
          <span>Customer operations · Refund review</span>
        </div>
        <div className="task-copy">
          <p id="task-heading">{taskBrief}</p>
          <div className="task-signals" aria-label="Task safety signals">
            <span>
              <ShieldCheck size={14} aria-hidden="true" /> Supported workflow
            </span>
            <span>Case ID verified</span>
            <span>6 planned movements</span>
          </div>
        </div>
      </section>

      <section className="score-section" aria-labelledby="score-heading">
        <div className="score-header">
          <div>
            <p className="eyebrow">Execution score</p>
            <h1 id="score-heading">From evidence to action</h1>
          </div>
          <div className="legend" aria-label="Status legend">
            <span><i className="legend-complete" /> Complete</span>
            <span><i className="legend-active" /> Active gate</span>
            <span><i className="legend-blocked" /> Blocked</span>
          </div>
        </div>

        <ol className="score" aria-label="Six-step execution plan">
          {baseSteps.map((step, index) => {
            const status = statusForStep(index, outcome);
            const isInspectable = index === 2;
            return (
              <li
                className={`score-step score-step-${status} ${isInspectable ? "score-step-inspectable" : ""}`}
                key={step.number}
              >
                <div className="playhead" aria-hidden="true" />
                <div className="step-topline">
                  <span className="step-number">{step.number}</span>
                  <span className="step-state">
                    {status === "completed" && <Check size={14} />}
                    {status === "waiting" && <CirclePause size={14} />}
                    {status === "blocked" && <LockKeyhole size={13} />}
                    {status === "skipped" && <X size={13} />}
                    {statusLabel[status]}
                  </span>
                </div>
                <div className="step-body">
                  <h2>{step.name}</h2>
                  <code>{step.tool}</code>
                  <p>{step.reason}</p>
                </div>
                <div className="step-foot">
                  {step.dependency ? (
                    <span className="dependency">
                      <ArrowRight size={12} aria-hidden="true" />
                      <b>After</b> {step.dependency}
                    </span>
                  ) : <span className="dependency dependency-none">No dependencies</span>}
                  <span className="duration">
                    <Clock3 size={12} aria-hidden="true" /> {timingForStep(index, outcome, step.duration)}
                  </span>
                </div>
                {isInspectable && (
                  <button
                    aria-expanded={inspectorOpen}
                    className="inspect-trigger"
                    onClick={() => setInspectorOpen((open) => !open)}
                    type="button"
                  >
                    <Inspect size={15} aria-hidden="true" />
                    Inspect output
                    <ChevronDown className={inspectorOpen ? "rotate" : ""} size={15} />
                  </button>
                )}
              </li>
            );
          })}
        </ol>

        {inspectorOpen && (
          <section className="output-inspector" aria-labelledby="inspector-heading">
            <div className="inspector-heading">
              <div>
                <p className="eyebrow">Tool output · Step 03</p>
                <h2 id="inspector-heading">Refund calculation</h2>
              </div>
              <button onClick={() => setInspectorOpen(false)} type="button">
                <X size={16} /> Close
              </button>
            </div>
            <dl className="calculation-grid">
              <div><dt>Input amount</dt><dd>SAR 600.00</dd></div>
              <div><dt>Refund percentage</dt><dd>75%</dd></div>
              <div><dt>Fees</dt><dd>− SAR 30.00</dd></div>
              <div className="calculation-total"><dt>Final recommended refund</dt><dd>SAR 420.00</dd></div>
            </dl>
            <div className="output-meta">
              <span>Calculation completed in 18 ms</span>
              <details>
                <summary>Structured payload</summary>
                <pre>{`{
  "case_id": "CASE-2026-0417",
  "eligible": true,
  "recommended_refund": 420.0,
  "currency": "SAR"
}`}</pre>
              </details>
            </div>
          </section>
        )}
      </section>

      <section className={`approval-band approval-${outcome}`} aria-labelledby="approval-heading">
        <div className="approval-rail">
          {outcome === "waiting" ? <CirclePause size={22} /> : outcome === "approved" ? <Check size={22} /> : <X size={22} />}
          <span>Human decision required</span>
        </div>

        <div className="approval-content">
          <div className="approval-title">
            <p className="eyebrow">Approval gate · Step 05</p>
            <h2 id="approval-heading">
              {outcome === "waiting" && "Release the internal report?"}
              {outcome === "approved" && "Report approved and workflow resumed"}
              {outcome === "rejected" && "Action rejected; audit report retained"}
            </h2>
            <p>
              {outcome === "waiting"
                ? "The agent has assembled the evidence. Your decision authorizes all remaining approval-marked work in this run."
                : outcome === "approved"
                  ? "The report and customer response are now complete. The decision and reviewer note were added to the audit trail."
                  : "The internal audit report was generated, while the customer response was skipped under the current rejection semantics."}
            </p>
          </div>

          <dl className="evidence-strip" aria-label="Approval evidence">
            <div><dt>Refund eligible</dt><dd>Yes</dd></div>
            <div><dt>Recommended refund</dt><dd>SAR 420.00</dd></div>
            <div><dt>SLA remaining</dt><dd>3.2 hours</dd></div>
            <div><dt>Priority</dt><dd>High</dd></div>
          </dl>

          <div className="recommendation">
            <span>Agent recommendation</span>
            <p>Approve report generation and customer-response preparation.</p>
          </div>

          {outcome === "waiting" ? (
            <div className="decision-row">
              <div className="note-field">
                <label htmlFor="review-note">Reviewer note <span>optional</span></label>
                <Textarea
                  id="review-note"
                  onChange={(event) => setReviewerNote(event.target.value)}
                  placeholder="Add context for the audit record…"
                  value={reviewerNote}
                />
              </div>
              <div className="decision-actions">
                <Button className="reject-button" onClick={() => setOutcome("rejected")} variant="outline">
                  Reject task
                </Button>
                <Button className="approve-button" onClick={() => setOutcome("approved")}>
                  Approve &amp; continue <ArrowRight size={16} />
                </Button>
              </div>
            </div>
          ) : (
            <div className="decision-record">
              <span>{outcome === "approved" ? "Approved" : "Rejected"} by You · just now</span>
              <span>{reviewerNote || "No reviewer note supplied"}</span>
              <button onClick={() => setOutcome("waiting")} type="button">
                <RotateCcw size={14} /> Reset prototype
              </button>
            </div>
          )}
        </div>
      </section>

      <section className="history-ribbon" aria-labelledby="history-heading">
        <div>
          <p className="eyebrow">Task history</p>
          <h2 id="history-heading">Recent repertoire</h2>
        </div>
        <button className="history-entry" type="button">
          <span className="history-status"><Check size={14} /> Completed</span>
          <span className="history-task">Review CASE-2026-0388 for SLA risk and prepare an internal report</span>
          <span className="history-meta">6 steps · 1 approval · 14:32</span>
          <FileText size={16} aria-hidden="true" />
        </button>
      </section>

      <footer className="prototype-footer">
        Isolated visual prototype · Static demonstration data · No backend or provider connection
      </footer>
    </main>
  );
}
