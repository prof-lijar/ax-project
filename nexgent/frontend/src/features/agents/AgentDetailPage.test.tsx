import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { AgentDefinition } from "../../shared/types/agents";
import { AgentDetailPageView } from "./AgentDetailPage";

const agent: AgentDefinition = {
  id: "1",
  name: "Weekly Reporter",
  role: "Ward risk reporting collaborator",
  description: "Prepares Korean weekly reports.",
  graphId: "ansimk_weekly_reporter",
  readiness: "ready",
  currentWork: "Ready for a report",
  runtimeLabel: "LangGraph",
  lastObservedAt: null,
  observationMode: "live",
  capabilities: ["Weekly activity comparison"],
  inputs: [
    {
      name: "week_start",
      description: "Monday in YYYY-MM-DD format",
      required: true
    }
  ],
  outputDescription: "Korean Markdown",
  configuration: [{ label: "Trigger", value: "Manual" }],
  limitations: ["Scheduling is not connected"],
  recentRuns: []
};

describe("AgentDetailPage", () => {
  it("renders the catalog-backed agent contract and actions", () => {
    const markup = renderToStaticMarkup(
      <AgentDetailPageView agent={agent} />
    );

    expect(markup).toContain("Back to Agents");
    expect(markup).toContain("Run in Chat");
    expect(markup).toContain("Weekly Reporter");
    expect(markup).toContain("Ward risk reporting collaborator");
    expect(markup).toContain("Live data");
    expect(markup).toContain("Ready");
    expect(markup).toContain("ansimk_weekly_reporter");
    expect(markup).toContain("Capabilities");
    expect(markup).toContain("week_start");
    expect(markup).toContain("Korean Markdown");
    expect(markup).toContain("Configuration");
    expect(markup).toContain("Scheduling is not connected");
    expect(markup).toContain("No sample runs yet.");
  });

  it("renders an operational unknown-agent state", () => {
    const markup = renderToStaticMarkup(
      <AgentDetailPageView agent={null} />
    );

    expect(markup).toContain("Agent not found");
    expect(markup).toContain("Back to Agents");
    expect(markup).not.toContain("Run in Chat");
  });
});
