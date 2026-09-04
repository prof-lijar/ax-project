import { describe, expect, it } from "vitest";

import {
  agentCatalogClient,
  RAG_CHAT_GRAPH_ID
} from "../../shared/api/agentCatalogClient";
import { getChatCapableAgents, usesRagChat } from "./ChatPage";

describe("ChatPage agent routing", () => {
  it("offers only explicitly Chat-capable catalog agents", async () => {
    const agents = await agentCatalogClient.listAgents();

    expect(getChatCapableAgents(agents).map((agent) => agent.name)).toEqual(
      ["RAG Agent"]
    );
    expect(
      getChatCapableAgents(agents).some(
        (agent) => agent.id === "ansimk_scout_agent"
      )
    ).toBe(false);
  });

  it("routes only the real RAG Agent through dedicated RAG Chat", () => {
    expect(usesRagChat(RAG_CHAT_GRAPH_ID)).toBe(true);
    expect(usesRagChat(null)).toBe(false);
    expect(usesRagChat("chat")).toBe(false);
    expect(usesRagChat("ansimk_weekly_reporter")).toBe(false);
    expect(usesRagChat("preview_data_analyst")).toBe(false);
  });
});
