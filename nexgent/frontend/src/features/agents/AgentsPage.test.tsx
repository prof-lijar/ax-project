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
    expect(markup).toContain("Start chat");
    expect(markup).toContain("Your co-workers");
    expect(markup).toContain('aria-label="Find a co-worker"');
    expect(markup).not.toContain("0 runs");
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
    expect(markup).not.toContain("Google ADK");
    expect(markup).not.toContain("Data Analyst");
    expect(markup).not.toContain("Report QA");
    expect(markup).not.toContain("Document Assistant");
    expect(markup).not.toContain("Database Assistant");
    expect(markup).not.toContain("Risk Monitoring Agent");
    expect(markup).not.toContain("Preview data");
    expect(markup).not.toContain("Awaiting live Agent Server-to-RAG");
    expect(markup).not.toContain("Needs attention");
    expect(markup).not.toContain("0 runs");
    expect(markup).not.toContain("2 runs");
  });

  it("keeps Weekly Reporter out of Chat now that it is bulk-only", async () => {
    const weeklyReporter = (await agentCatalogClient.listAgents()).find(
      ({ id }) => id === "1"
    );
    expect(weeklyReporter).toBeDefined();

    const markup = renderToStaticMarkup(
      <AgentsPageView agents={[weeklyReporter!]} search="" />
    );

    expect(markup).toContain("Weekly Reporter");
    expect(markup).not.toContain("Start chat");
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
    expect(markup).not.toContain("Start chat");
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

    expect(markup).toContain("No co-workers found");
    expect(markup).not.toContain("Agent details");
  });
});

describe("Co-worker catalog states", () => {
  it("finds user-facing outcomes without requiring technical search terms", async () => {
    const agents = await agentCatalogClient.listAgents();
    expect(filterAgents(agents, "ZIP").map((a) => a.id)).toEqual(["1"]);
    expect(filterAgents(agents, "sources").map((a) => a.id)).toEqual([
      "7",
      "ansimk_scout_agent"
    ]);
    expect(filterAgents(agents, "  KNOWLEDGE ").map((a) => a.id)).toEqual([
      "7"
    ]);
  });

  it("does not show stale cards alongside an error or loading state", () => {
    const failed = renderToStaticMarkup(
      <AgentsPageView agents={[agent]} search="" isError onRetry={() => {}} />
    );
    expect(failed).toContain("Try again");
    expect(failed).toContain('role="alert"');
    expect(failed).not.toContain('role="listitem"');
    const loading = renderToStaticMarkup(
      <AgentsPageView agents={[agent]} search="" isLoading />
    );
    expect(loading).toContain("Loading co-workers");
    expect(loading).not.toContain('role="listitem"');
  });

  it("offers a clear action when search has no matches", () => {
    const markup = renderToStaticMarkup(
      <AgentsPageView
        agents={[agent]}
        search="missing"
        onSearchChange={() => {}}
      />
    );
    expect(markup).toContain("Clear search");
    expect(markup).toContain("0 of 1 co-workers");
    expect(markup).not.toContain('role="listitem"');
  });

  it("describes Chat availability without inventing runtime health", async () => {
    const rag = (await agentCatalogClient.listAgents()).find(
      (a) => a.id === "7"
    )!;
    const markup = renderToStaticMarkup(
      <AgentsPageView agents={[rag]} search="" />
    );
    expect(markup).toContain("Available in Chat");
    expect(markup).toContain("Text only");
    expect(markup).not.toContain(">Ready<");
    expect(markup).not.toContain("LangGraph");
  });
});
