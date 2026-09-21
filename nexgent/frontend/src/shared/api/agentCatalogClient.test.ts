import { describe, expect, it } from "vitest";

import {
  agentCatalogClient,
  normalizeAgentCatalog,
  type AgentCatalogRecord
} from "./agentCatalogClient";

describe("agentCatalogClient", () => {
  it("returns Weekly Reporter, RAG Agent, the ADK Scout, and Sumin", async () => {
    const first = await agentCatalogClient.listAgents();
    const second = await agentCatalogClient.listAgents();

    expect(first).toEqual(second);
    expect(first).not.toBe(second);
    expect(first).toHaveLength(4);
    expect(first.map(({ id, graphId }) => ({ id, graphId }))).toEqual([
      { id: "1", graphId: "ansimk_weekly_reporter" },
      { id: "7", graphId: "rag_chat" },
      { id: "ansimk_scout_agent", graphId: "ansimk_scout_agent" },
      { id: "sumin", graphId: "sumin" }
    ]);
    expect(first[0]).toMatchObject({
      id: "1",
      graphId: "ansimk_weekly_reporter",
      canRunInChat: false,
      observationMode: null,
      readiness: "ready"
    });
    expect(first[0].limitations).toContain(
      "Scheduling and Slack delivery are separate workflows"
    );
    expect(first[1]).toMatchObject({
      id: "7",
      name: "RAG Agent",
      graphId: "rag_chat",
      canRunInChat: true,
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
    expect(first[2]).toMatchObject({
      id: "ansimk_scout_agent",
      name: "AnsimK Scout Agent",
      graphId: "ansimk_scout_agent",
      canRunInChat: false,
      runtimeLabel: "Google ADK",
      readiness: null,
      observationMode: null
    });
    expect(first[2].inputs).toContainEqual({
      name: "additional_instructions",
      description: "Optional per-run or scheduled research guidance",
      required: false
    });
    expect(first[3]).toMatchObject({
      id: "sumin",
      name: "Sumin",
      graphId: "sumin",
      canRunInChat: false,
      runtimeLabel: "Slack Socket Mode",
      readiness: null,
      observationMode: null
    });
    expect(first[3].capabilities).toContain(
      "Archive Slack uploads in channel folders"
    );
  });

  it("normalizes unknown catalog and run states to safe fallbacks", () => {
    const record: AgentCatalogRecord = {
      id: "future-agent",
      name: "Future agent",
      role: "Preview",
      description: "Unknown runtime state",
      graphId: "future_agent",
      canRunInChat: false,
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
