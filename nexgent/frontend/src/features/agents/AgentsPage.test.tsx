import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { AgentDefinition } from "../../shared/types/agents";
import {
  AgentsPageView,
  filterAgents,
  getReadinessPresentation,
  getRunStatusPresentation
} from "./AgentsPage";

const agent: AgentDefinition = {
  id: "weekly-reporter",
  name: "Weekly Reporter",
  role: "Work insight collaborator",
  description: "Prepares Korean weekly reports.",
  graphId: "ansimk_weekly_reporter",
  readiness: "ready",
  currentWork: "Ready for a report",
  runtimeLabel: "LangGraph",
  lastObservedAt: null,
  observationMode: "preview",
  capabilities: ["Weekly activity comparison"],
  inputs: [],
  outputDescription: "Korean Markdown",
  configuration: [],
  limitations: ["Scheduling is not connected"],
  recentRuns: []
};

describe("AgentsPage", () => {
  it("matches search across agent identity, graph id, and capabilities", () => {
    expect(filterAgents([agent], "weekly")).toEqual([agent]);
    expect(filterAgents([agent], "ansimk_weekly_reporter")).toEqual([agent]);
    expect(filterAgents([agent], "activity comparison")).toEqual([agent]);
    expect(filterAgents([agent], "delivery")).toEqual([]);
  });

  it("maps readiness and run states to restrained status presentations", () => {
    expect(getReadinessPresentation("ready")).toEqual({
      label: "Ready",
      tone: "green"
    });
    expect(getReadinessPresentation("degraded").tone).toBe("amber");
    expect(getRunStatusPresentation("failed").tone).toBe("red");
    expect(getRunStatusPresentation("cancelled").tone).toBe("neutral");
  });

  it("labels preview content and handles empty run history", () => {
    const markup = renderToStaticMarkup(
      <AgentsPageView agents={[agent]} search="" />
    );

    expect(markup).toContain("Preview data");
    expect(markup).toContain("No sample runs yet.");
    expect(markup).toContain("ansimk_weekly_reporter");
    expect(markup).not.toContain("Run agent");
  });

  it("shows an operational no-results state", () => {
    const markup = renderToStaticMarkup(
      <AgentsPageView agents={[agent]} search="does-not-match" />
    );

    expect(markup).toContain("No agents match your workspace search.");
    expect(markup).toContain("Select an agent to inspect");
  });
});
