import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { MockAgentRun } from "../../shared/state/useAgentRunStore";
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

const runningRun: MockAgentRun = {
  runId: "run-1",
  agentId: "1",
  agentName: "Weekly Reporter",
  assistantMessageId: "message-1",
  prompt: "Generate the weekly report",
  activeStageIndex: 2,
  startedAt: Date.now() - 18_000,
  completedAt: null,
  durationSeconds: null,
  status: "running"
};

describe("AgentDetailPage", () => {
  it("renders the simplified agent header and a minimal empty run state", () => {
    const markup = renderToStaticMarkup(
      <AgentDetailPageView agent={agent} />
    );

    expect(markup).toContain("Back to Agents");
    expect(markup).toContain("Run in Chat");
    expect(markup).toContain("Weekly Reporter");
    expect(markup).toContain("Ward risk reporting collaborator");
    expect(markup).toContain("Prepares Korean weekly reports.");
    expect(markup).toContain("Live data");
    expect(markup).toContain("Ready");
    expect(markup).toContain("Current run");
    expect(markup).toContain("No active mock run.");
    expect(markup).toContain("Latest run");
    expect(markup).toContain("No previous mock run.");
  });

  it("does not render catalog metadata and informational sections", () => {
    const markup = renderToStaticMarkup(
      <AgentDetailPageView agent={agent} />
    );

    expect(markup).not.toContain("Graph ID");
    expect(markup).not.toContain("Runtime");
    expect(markup).not.toContain("Last observed");
    expect(markup).not.toContain("Capabilities");
    expect(markup).not.toContain("Contract");
    expect(markup).not.toContain("Configuration");
    expect(markup).not.toContain("Current limitations");
    expect(markup).not.toContain("Recent runs");
    expect(markup).not.toContain("Sample history");
    expect(markup).not.toContain("ansimk_weekly_reporter");
  });

  it("renders only a running mock record as the current run", () => {
    const runningMarkup = renderToStaticMarkup(
      <AgentDetailPageView agent={agent} run={runningRun} />
    );
    const terminalCurrentMarkup = renderToStaticMarkup(
      <AgentDetailPageView
        agent={agent}
        run={{
          ...runningRun,
          completedAt: Date.now(),
          durationSeconds: 18,
          status: "cancelled"
        }}
      />
    );

    expect(runningMarkup).toContain("Generate the weekly report");
    expect(runningMarkup).toContain("Processing information");
    expect(runningMarkup).toContain("Running for");
    expect(runningMarkup).toContain("Stop");
    expect(terminalCurrentMarkup).toContain("No active mock run.");
    expect(terminalCurrentMarkup).not.toContain("Cancelled");
  });

  it("renders the latest terminal run with its contextual Chat action", () => {
    const cancelledMarkup = renderToStaticMarkup(
      <AgentDetailPageView
        agent={agent}
        latestRun={{
          ...runningRun,
          completedAt: Date.now(),
          durationSeconds: 18,
          status: "cancelled"
        }}
      />
    );
    const completedMarkup = renderToStaticMarkup(
      <AgentDetailPageView
        agent={agent}
        latestRun={{
          ...runningRun,
          completedAt: Date.now(),
          durationSeconds: 2,
          status: "completed"
        }}
      />
    );
    const failedMarkup = renderToStaticMarkup(
      <AgentDetailPageView
        agent={agent}
        latestRun={{
          ...runningRun,
          completedAt: Date.now(),
          durationSeconds: 4,
          status: "failed"
        }}
      />
    );

    expect(cancelledMarkup).toContain("Cancelled");
    expect(cancelledMarkup).toContain("Duration 00:18");
    expect(cancelledMarkup).toContain("Finished");
    expect(cancelledMarkup).toContain("Run again in Chat");
    expect(cancelledMarkup).not.toContain(">Stop<");
    expect(completedMarkup).toContain("Completed in 00:02");
    expect(completedMarkup).toContain("Run again in Chat");
    expect(failedMarkup).toContain("Failed");
    expect(failedMarkup).toContain("Retry in Chat");
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
