import { ArrowRight, LockKeyhole } from "lucide-react";

import type { GuidedDemoTask } from "@/lib/agent-api";

interface MissionSelectorProps {
  disabled: boolean;
  missions: GuidedDemoTask[];
  onSelect: (mission: GuidedDemoTask) => void;
}

export function MissionSelector({
  disabled,
  missions,
  onSelect,
}: MissionSelectorProps) {
  return (
    <section className="mission-selector" aria-labelledby="mission-heading">
      <header className="mission-selector-heading">
        <div>
          <p className="section-label">Guided missions</p>
          <h1 id="mission-heading">Choose an operation to conduct.</h1>
        </div>
        <p>
          Every mission runs against the live orchestration service with
          deterministic planning and fictional operational data.
        </p>
      </header>

      <ol className="mission-list">
        {missions.map((mission, index) => (
          <li key={mission.id}>
            <button
              className="mission-row"
              disabled={disabled}
              onClick={() => onSelect(mission)}
              type="button"
            >
              <span className="mission-index">{String(index + 1).padStart(2, "0")}</span>
              <span className="mission-title">
                <strong>{mission.title}</strong>
                <small>{mission.user_request}</small>
              </span>
              <span className="mission-behavior">
                {mission.expected_status === "failed"
                  ? "Safety boundary demonstration"
                  : mission.demonstrates_approval
                    ? "Human checkpoint included"
                    : "Autonomous read-only run"}
              </span>
              <span className="mission-spec">
                <b>{mission.expected_tools.length}</b>
                {mission.expected_tools.length === 1 ? " tool" : " tools"}
                {mission.demonstrates_approval ? (
                  <em><LockKeyhole size={13} aria-hidden="true" /> Approval</em>
                ) : null}
              </span>
              <span className="mission-start">Start new run</span>
              <ArrowRight className="mission-arrow" size={20} aria-hidden="true" />
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}
