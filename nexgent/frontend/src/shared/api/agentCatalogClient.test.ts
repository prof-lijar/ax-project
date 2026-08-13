import { describe, expect, it } from "vitest";

import {
  agentCatalogClient,
  normalizeAgentCatalog,
  type AgentCatalogRecord
} from "./agentCatalogClient";

describe("agentCatalogClient", () => {
  it("returns one deterministic Weekly Reporter preview", async () => {
    const first = await agentCatalogClient.listAgents();
    const second = await agentCatalogClient.listAgents();

    expect(first).toEqual(second);
    expect(first).not.toBe(second);
    expect(first).toHaveLength(1);
    expect(first[0]).toMatchObject({
      id: "ansimk-weekly-reporter",
      graphId: "ansimk_weekly_reporter",
      observationMode: "preview",
      readiness: "ready"
    });
    expect(first[0].limitations).toContain(
      "Scheduling and delivery are not connected"
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
