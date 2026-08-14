import { beforeEach, describe, expect, it } from "vitest";

import type { AgentDefinition } from "../types/agents";
import { useUiStore } from "./useUiStore";

const weeklyReporter: AgentDefinition = {
  id: "1",
  name: "Weekly Reporter",
  role: "Ward risk reporting collaborator",
  description: "Produces ward danger-day reports.",
  graphId: "ansimk_weekly_reporter",
  readiness: "ready",
  currentWork: "Ready",
  runtimeLabel: "LangGraph",
  lastObservedAt: null,
  observationMode: "live",
  capabilities: [],
  inputs: [],
  outputDescription: "Markdown",
  configuration: [],
  limitations: [],
  recentRuns: []
};

beforeEach(() => {
  useUiStore.setState({ selectedAgent: null, pendingAgentRun: null });
});

describe("useUiStore agent runs", () => {
  it("selects an agent and records a one-shot run request", () => {
    useUiStore.getState().requestAgentRun(weeklyReporter);

    expect(useUiStore.getState().selectedAgent).toEqual(weeklyReporter);
    expect(useUiStore.getState().pendingAgentRun).toMatchObject({ agentId: "1" });

    useUiStore.getState().clearPendingAgentRun();
    expect(useUiStore.getState().pendingAgentRun).toBeNull();
  });
});
