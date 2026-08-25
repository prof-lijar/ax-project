import { describe, expect, it } from "vitest";

import {
  agentCatalogClient,
  normalizeAgentCatalog,
  type AgentCatalogRecord
} from "./agentCatalogClient";

describe("agentCatalogClient", () => {
  it("returns only Weekly Reporter and the real RAG Agent", async () => {
    const first = await agentCatalogClient.listAgents();
    const second = await agentCatalogClient.listAgents();

    expect(first).toEqual(second);
    expect(first).not.toBe(second);
    expect(first).toHaveLength(2);
    expect(first.map(({ id, graphId }) => ({ id, graphId }))).toEqual([
      { id: "1", graphId: "ansimk_weekly_reporter" },
      { id: "7", graphId: "rag_chat" }
    ]);
    expect(first[0]).toMatchObject({
      id: "1",
      graphId: "ansimk_weekly_reporter",
      observationMode: "live",
      readiness: "ready"
    });
    expect(first[0].limitations).toContain(
      "Scheduling and delivery are not connected"
    );
    expect(first[1]).toMatchObject({
      id: "7",
      name: "RAG Agent",
      graphId: "rag_chat",
      description:
        "Answers one-turn questions from the indexed RAG corpus using grounded retrieval and source provenance.",
      readiness: null,
      currentWork: null,
      lastObservedAt: null,
      observationMode: null,
      recentRuns: []
    });
    expect(first[1].limitations).not.toContain(
      "Agent Server-to-RAG runtime connectivity still needs live validation"
    );
  });

  it("normalizes unknown catalog and run states to safe fallbacks", () => {
    const record: AgentCatalogRecord = {
      id: "future-agent",
      name: "Future agent",
      role: "Preview",
      description: "Unknown runtime state",
      graphId: "future_agent",
      readiness: "unexpected",
      currentWork: "Not connected",
      runtimeLabel: "LangGraph",
      lastObservedAt: null,
      observationMode: "preview",
      capabilities: [],
      inputs: [],
      outputDescription: "None",
      configuration: [],
      limitations: [],
      recentRuns: [
        {
          id: "run-unknown",
          status: "unexpected",
          trigger: "Preview",
          startedAt: "2026-08-13T09:00:00+09:00",
          duration: "0 sec",
          resultSummary: "No result",
          warningCount: 0
        }
      ]
    };

    expect(normalizeAgentCatalog([record])[0]).toMatchObject({
      readiness: "draft",
      recentRuns: [{ status: "failed" }]
    });
  });
});
