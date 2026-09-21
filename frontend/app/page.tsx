"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, CircleHelp, RotateCw } from "lucide-react";

import { LocalMissionComposer } from "@/components/local-mission-composer";
import { MissionSelector } from "@/components/mission-selector";
import { OrchestrationCanvas } from "@/components/orchestration-canvas";
import { OutcomePanel } from "@/components/outcome-panel";
import { RecentRuns } from "@/components/recent-runs";
import {
  AgentApiError,
  agentApi,
  type AppMode,
  type Capabilities,
  type GuidedDemoTask,
  type PendingApproval,
  type StartTaskRequest,
  type TaskDetail,
  type TaskId,
  type TaskSummary,
} from "@/lib/agent-api";
import { titleCase } from "@/lib/orchestration-presentation";

type ServiceState = "starting" | "ready" | "unavailable";
type RunOrigin = "new" | "existing";
interface OperationalError { code: string | null; message: string; }

const delay = (milliseconds: number) =>
  new Promise((resolve) => window.setTimeout(resolve, milliseconds));

function operationalError(error: unknown, fallback: string): OperationalError {
  if (error instanceof AgentApiError) {
    return { code: error.code, message: error.message };
  }
  return { code: null, message: fallback };
}

export default function Home() {
  const [serviceState, setServiceState] = useState<ServiceState>("starting");
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [viewMode, setViewMode] = useState<AppMode>("demo");
  const [recentTasks, setRecentTasks] = useState<TaskSummary[]>([]);
  const [currentTask, setCurrentTask] = useState<TaskDetail | null>(null);
  const [runOrigin, setRunOrigin] = useState<RunOrigin>("new");
  const [pendingApproval, setPendingApproval] = useState<PendingApproval | null>(null);
  const [reviewerNote, setReviewerNote] = useState("");
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [isWorking, setIsWorking] = useState(false);
  const [error, setError] = useState<OperationalError | null>(null);
  const [bootKey, setBootKey] = useState(0);
  const approvalSyncVersion = useRef(0);

  const refreshHistory = useCallback(async () => {
    const tasks = await agentApi.listTasks({ limit: capabilities?.history.max_results ?? 8 });
    setRecentTasks(tasks);
  }, [capabilities?.history.max_results]);

  const syncApproval = useCallback(async (task: TaskDetail) => {
    const syncVersion = approvalSyncVersion.current + 1;
    approvalSyncVersion.current = syncVersion;
    if (!task.workflow.waiting_for_approval) {
      setPendingApproval(null);
    } else if (task.pending_approval) {
      if (task.pending_approval.task_id === task.task_id) {
        setPendingApproval(task.pending_approval);
      }
    } else {
      const approval = await agentApi.getPendingApproval(task.task_id);
      if (
        approvalSyncVersion.current === syncVersion &&
        approval.task_id === task.task_id
      ) {
        setPendingApproval(approval);
      }
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function initialize() {
      setServiceState("starting");
      setError(null);
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          const [, capabilityData] = await Promise.all([
            agentApi.getHealth(),
            agentApi.getCapabilities(),
          ]);
          if (cancelled) return;
          setCapabilities(capabilityData);
          setViewMode(capabilityData.app_mode);
          const tasks = await agentApi.listTasks({ limit: capabilityData.history.max_results });
          if (cancelled) return;
          setRecentTasks(tasks);
          setServiceState("ready");
          return;
        } catch (caught) {
          if (attempt < 2) {
            await delay(1100 + attempt * 900);
            if (cancelled) return;
          } else if (!cancelled) {
            setServiceState("unavailable");
            setError(operationalError(caught, "The orchestration service is not available."));
          }
        }
      }
    }
    void initialize();
    return () => { cancelled = true; };
  }, [bootKey]);

  async function startTask(request: StartTaskRequest, providerApiKey?: string) {
    setIsWorking(true);
    setError(null);
    setReviewerNote("");
    setSelectedStepId(null);
    try {
      const task = await agentApi.startTask(request, { providerApiKey });
      setRunOrigin("new");
      setCurrentTask(task);
      await syncApproval(task);
      await refreshHistory();
    } catch (caught) {
      setError(operationalError(caught, "The mission could not be started."));
    } finally {
      setIsWorking(false);
    }
  }

  function selectMission(mission: GuidedDemoTask) {
    void startTask({ user_request: mission.user_request, planner_mode: "deterministic", provider: null, model: null });
  }

  async function decide(decision: "approved" | "rejected") {
    if (!currentTask) return;
    setIsWorking(true);
    setError(null);
    try {
      const task = await agentApi.decideApproval(currentTask.task_id, {
        decision,
        reviewer_note: reviewerNote.trim() || null,
      });
      setCurrentTask(task);
      setReviewerNote("");
      await syncApproval(task);
      await refreshHistory();
    } catch (caught) {
      setError(operationalError(caught, "The approval decision could not be recorded."));
    } finally {
      setIsWorking(false);
    }
  }

  async function openTask(taskId: TaskId) {
    setIsWorking(true);
    setError(null);
    try {
      const task = await agentApi.getTask(taskId);
      setRunOrigin("existing");
      setCurrentTask(task);
      setSelectedStepId(null);
      setReviewerNote("");
      await syncApproval(task);
    } catch (caught) {
      setError(operationalError(caught, "The mission record could not be loaded."));
    } finally {
      setIsWorking(false);
    }
  }

  function returnToMissions() {
    setCurrentTask(null);
    setPendingApproval(null);
    setSelectedStepId(null);
    setReviewerNote("");
    setError(null);
  }

  if (serviceState === "starting") {
    return (
      <main className="service-stage">
        <div className="service-pulse" aria-hidden="true"><i /><i /><i /></div>
        <p>Starting demo service…</p>
        <span>The orchestration workspace will open when its capabilities are ready.</span>
      </main>
    );
  }

  if (serviceState === "unavailable" || !capabilities) {
    return (
      <main className="service-stage service-offline">
        <CircleHelp size={28} aria-hidden="true" />
        <p>Demo service is still waking.</p>
        <span>{error?.message ?? "The API has not responded yet."}</span>
        <button onClick={() => setBootKey((value) => value + 1)} type="button"><RotateCw size={15} /> Try again</button>
      </main>
    );
  }

  const isDemo = viewMode === "demo";
  const currentMission = capabilities.guided_demo_tasks.find(
    (mission) => mission.user_request === currentTask?.user_request,
  );

  return (
    <main className="conductor-shell">
      <header className="conductor-header">
        <div className="wordmark">
          <span className="conductor-mark" aria-hidden="true"><i /><i /><i /></span>
          <div><strong>Conductor</strong><small>Mission orchestration canvas</small></div>
        </div>
        <div className="mode-switch" aria-label="Workspace mode">
          <button
            aria-pressed={isDemo}
            className={isDemo ? "active" : ""}
            disabled={!capabilities.demo_mode_available}
            onClick={() => { setViewMode("demo"); returnToMissions(); }}
            type="button"
          >Demo mode</button>
          <button
            aria-pressed={!isDemo}
            className={!isDemo ? "active" : ""}
            disabled={capabilities.app_mode === "demo"}
            onClick={() => { setViewMode("local"); returnToMissions(); }}
            type="button"
          >Local mode</button>
        </div>
        <div className="service-indicator"><i /> Service ready</div>
      </header>

      <div className="workspace">
        {currentTask ? (
          <>
            <div className="workspace-nav">
              <button onClick={returnToMissions} type="button"><ArrowLeft size={16} /> {isDemo ? "All guided missions" : "New mission"}</button>
              <span>
                <b>{runOrigin === "existing" ? "Opened run" : "New run"}</b>
                {currentMission?.title ?? titleCase(currentTask.plan?.task_type ?? "Custom mission")}
              </span>
            </div>
            <OrchestrationCanvas
              onDecision={(decision) => void decide(decision)}
              onReviewerNote={setReviewerNote}
              onSelectStep={setSelectedStepId}
              pendingApproval={pendingApproval}
              reviewerNote={reviewerNote}
              selectedStepId={selectedStepId}
              task={currentTask}
              working={isWorking}
            />
            <OutcomePanel task={currentTask} />
          </>
        ) : isDemo ? (
          <MissionSelector disabled={isWorking} missions={capabilities.guided_demo_tasks} onSelect={selectMission} />
        ) : (
          <LocalMissionComposer capabilities={capabilities} disabled={isWorking} onStart={startTask} />
        )}

        {error ? (
          <div className="workspace-error" role="alert"><b>{error.code ? titleCase(error.code) : "Operation unavailable"}</b><span>{error.message}</span></div>
        ) : null}

        <RecentRuns
          disabled={isWorking}
          missions={capabilities.guided_demo_tasks}
          onOpen={(taskId) => void openTask(taskId)}
          tasks={recentTasks}
        />
      </div>

      <footer className="conductor-footer">
        <span>Live FastAPI orchestration</span>
        <span>{isDemo ? "Session-scoped demo history" : "Persistent local history"}</span>
        <span>Provider credentials are never stored</span>
      </footer>
    </main>
  );
}
