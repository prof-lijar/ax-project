import { describe, expect, it } from "vitest";

import {
  agentCatalogClient,
  RAG_CHAT_GRAPH_ID
} from "../../shared/api/agentCatalogClient";
import { usesRagChat } from "./ChatPage";

describe("ChatPage agent routing", () => {
  it("receives only Weekly Reporter and RAG Agent from the shared catalog", async () => {
    const agents = await agentCatalogClient.listAgents();

    expect(agents.map((agent) => agent.name)).toEqual([
      "Weekly Reporter",
      "RAG Agent"
    ]);
  });

  it("routes only the real RAG Agent through dedicated RAG Chat", () => {
    expect(usesRagChat(RAG_CHAT_GRAPH_ID)).toBe(true);
    expect(usesRagChat(null)).toBe(false);
    expect(usesRagChat("chat")).toBe(false);
    expect(usesRagChat("ansimk_weekly_reporter")).toBe(false);
    expect(usesRagChat("preview_data_analyst")).toBe(false);
  });
});
