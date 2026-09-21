import { useState, type SubmitEvent } from "react";
import { ArrowRight, ChevronDown } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type {
  Capabilities,
  PlannerMode,
  ProviderName,
  StartTaskRequest,
} from "@/lib/agent-api";
import { titleCase } from "@/lib/orchestration-presentation";

interface LocalMissionComposerProps {
  capabilities: Capabilities;
  disabled: boolean;
  onStart: (
    request: StartTaskRequest,
    providerApiKey?: string,
  ) => Promise<void>;
}

export function LocalMissionComposer({
  capabilities,
  disabled,
  onStart,
}: LocalMissionComposerProps) {
  const [userRequest, setUserRequest] = useState("");
  const [planner, setPlanner] = useState<PlannerMode>(
    capabilities.planner_modes[0] ?? "deterministic",
  );
  const [provider, setProvider] = useState<ProviderName | "">("");
  const [model, setModel] = useState("");
  const [providerApiKey, setProviderApiKey] = useState("");

  const selectedProvider = capabilities.providers.find(
    (item) => item.name === provider,
  );

  async function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!userRequest.trim()) return;
    await onStart(
      {
        user_request: userRequest.trim(),
        planner_mode: planner,
        provider: planner === "llm" && provider ? provider : null,
        model: planner === "llm" && model.trim() ? model.trim() : null,
      },
      providerApiKey || undefined,
    );
    setProviderApiKey("");
  }

  return (
    <section className="local-composer" aria-labelledby="local-heading">
      <div className="local-composer-intro">
        <p className="section-label">Local mission</p>
        <h1 id="local-heading">Set the objective. The agent will score the route.</h1>
        <p>Free-form supported workflows run against your local service and persistence.</p>
      </div>
      <form onSubmit={submit}>
        <label className="objective-field" htmlFor="mission-objective">
          <span>Mission objective</span>
          <Textarea
            id="mission-objective"
            onChange={(event) => setUserRequest(event.target.value)}
            placeholder="Review a case, calculate a refund, prepare a response…"
            required
            value={userRequest}
          />
        </label>
        <details className="advanced-settings">
          <summary><ChevronDown size={15} aria-hidden="true" /> Planning controls</summary>
          <div className="settings-grid">
            <label>
              <span>Planner</span>
              <select
                onChange={(event) => {
                  const value = event.target.value as PlannerMode;
                  setPlanner(value);
                  if (value === "deterministic") {
                    setProvider("");
                    setModel("");
                    setProviderApiKey("");
                  }
                }}
                value={planner}
              >
                {capabilities.planner_modes.map((mode) => (
                  <option key={mode} value={mode}>{titleCase(mode)}</option>
                ))}
              </select>
            </label>
            {planner === "llm" ? (
              <>
                <label>
                  <span>Provider</span>
                  <select
                    onChange={(event) => {
                      setProvider(event.target.value as ProviderName | "");
                      setProviderApiKey("");
                    }}
                    value={provider}
                  >
                    <option value="">Select provider</option>
                    {capabilities.providers.map((item) => (
                      <option key={item.name} value={item.name}>{titleCase(item.name)}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Model · optional</span>
                  <input
                    onChange={(event) => setModel(event.target.value)}
                    placeholder={selectedProvider?.default_model ?? "Provider default"}
                    value={model}
                  />
                </label>
                {capabilities.provider_api_key_allowed ? (
                  <label>
                    <span>Provider key · memory only</span>
                    <input
                      autoComplete="off"
                      onChange={(event) => setProviderApiKey(event.target.value)}
                      placeholder={selectedProvider?.requires_api_key ? "Required" : "Optional"}
                      type="password"
                      value={providerApiKey}
                    />
                  </label>
                ) : null}
              </>
            ) : null}
          </div>
        </details>
        <Button className="primary-action" disabled={disabled || !userRequest.trim()} type="submit">
          Conduct mission <ArrowRight size={17} aria-hidden="true" />
        </Button>
      </form>
    </section>
  );
}
