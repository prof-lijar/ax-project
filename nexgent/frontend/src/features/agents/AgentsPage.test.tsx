import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it } from "vitest";

import { useUiStore } from "../../shared/state/useUiStore";
import { agentCatalogClient } from "../../shared/api/agentCatalogClient";
import type { AgentDefinition } from "../../shared/types/agents";
import {
  AgentsPageView,
  filterAgents,
  getReadinessPresentation,
  prepareAgentChatSelection
} from "./AgentsPage";

const agent: AgentDefinition = {
  id: "1",
  name: "Weekly Reporter",
  role: "Work insight collaborator",
  description: "Prepares Korean weekly reports.",
  graphId: "ansimk_weekly_reporter",
  canRunInChat: true,
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

beforeEach(() => {
  useUiStore.setState({ selectedAgent: null, pendingAgentRun: null });
});

describe("AgentsPage", () => {
  it("matches search across agent identity, graph id, and capabilities", () => {
    expect(filterAgents([agent], "weekly")).toEqual([agent]);
    expect(filterAgents([agent], "ansimk_weekly_reporter")).toEqual([agent]);
    expect(filterAgents([agent], "activity comparison")).toEqual([agent]);
    expect(filterAgents([agent], "delivery")).toEqual([]);
  });

  it("maps readiness to restrained status presentations", () => {
    expect(getReadinessPresentation("ready")).toEqual({
      label: "Ready",
      tone: "green"
    });
    expect(getReadinessPresentation("degraded").tone).toBe("amber");
  });

  it("renders a compact catalog with detail and direct Chat actions", () => {
    const markup = renderToStaticMarkup(
      <AgentsPageView agents={[agent]} search="" />
    );

    expect(markup).toContain("Preview data");
    expect(markup).toContain('href="/agents/1"');
    expect(markup).toContain("Chat");
    expect(markup).toContain("0 runs");
    expect(markup).not.toContain("sample runs");
    expect(markup).not.toContain("No sample runs yet.");
    expect(markup).not.toContain("Graph ID");
  });

  it("renders only the real shared catalog without fake RAG runtime state", async () => {
    const agents = await agentCatalogClient.listAgents();
    const markup = renderToStaticMarkup(
      <AgentsPageView agents={agents} search="" />
    );

    expect(markup).toContain("Weekly Reporter");
    expect(markup).toContain("RAG Agent");
    expect(markup).toContain("AnsimK Scout Agent");
    expect(markup).toContain('href="/agents/ansimk_scout_agent"');
    expect(markup).toContain("Google ADK");
    expect(markup).not.toContain("Data Analyst");
    expect(markup).not.toContain("Report QA");
    expect(markup).not.toContain("Document Assistant");
    expect(markup).not.toContain("Database Assistant");
    expect(markup).not.toContain("Risk Monitoring Agent");
    expect(markup).not.toContain("Preview data");
    expect(markup).not.toContain("Awaiting live Agent Server-to-RAG");
    expect(markup).not.toContain("Needs attention");
    expect(markup).not.toContain("0 runs");
    expect(markup).toContain("2 runs");
  });

  it("does not offer the non-Chat Scout card as a Chat action", async () => {
    const scout = (await agentCatalogClient.listAgents()).find(
      ({ id }) => id === "ansimk_scout_agent"
    );
    expect(scout).toBeDefined();

    const markup = renderToStaticMarkup(
      <AgentsPageView agents={[scout!]} search="" />
    );

    expect(markup).toContain("AnsimK Scout Agent");
    expect(markup).not.toContain(">Chat<");
  });

  it("prepares Chat with the selected agent without a pending run intent", () => {
    useUiStore.getState().requestAgentRun(agent);

    prepareAgentChatSelection(agent);

    expect(useUiStore.getState().selectedAgent).toEqual(agent);
    expect(useUiStore.getState().pendingAgentRun).toBeNull();
  });

  it("shows an operational no-results state", () => {
    const markup = renderToStaticMarkup(
      <AgentsPageView agents={[agent]} search="does-not-match" />
    );

    expect(markup).toContain("No agents match your workspace search.");
    expect(markup).not.toContain("Agent details");
  });
});
