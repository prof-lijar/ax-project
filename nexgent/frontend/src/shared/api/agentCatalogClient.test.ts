import { describe, expect, it } from "vitest";

import {
  agentCatalogClient,
  normalizeAgentCatalog,
  type AgentCatalogRecord
} from "./agentCatalogClient";

describe("agentCatalogClient", () => {
  it("returns six deterministic previews with route IDs separate from graph IDs", async () => {
    const first = await agentCatalogClient.listAgents();
    const second = await agentCatalogClient.listAgents();

    expect(first).toEqual(second);
    expect(first).not.toBe(second);
    expect(first).toHaveLength(6);
    expect(first.map(({ id, graphId }) => ({ id, graphId }))).toEqual([
      { id: "1", graphId: "ansimk_weekly_reporter" },
      { id: "2", graphId: "preview_data_analyst" },
      { id: "3", graphId: "preview_report_qa" },
      { id: "4", graphId: "preview_document_assistant" },
      { id: "5", graphId: "preview_database_assistant" },
      { id: "6", graphId: "preview_risk_monitoring_agent" }
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
