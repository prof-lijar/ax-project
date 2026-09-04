import { describe, expect, it } from "vitest";

import { navItems } from "../../app/routes";
import {
  getAgentIdFromPath,
  resolveSectionLocation,
  sectionPaths
} from "./sections";

describe("section routing", () => {
  it("omits the retired Tasks, Approvals, and Activity sections", () => {
    expect(navItems.map(({ id }) => id)).not.toEqual(
      expect.arrayContaining(["tasks", "approvals", "activity"])
    );
    expect(resolveSectionLocation("/tasks")).toBeNull();
    expect(resolveSectionLocation("/approvals")).toBeNull();
    expect(resolveSectionLocation("/activity")).toBeNull();
  });

  it("uses /agents as the canonical Agents route", () => {
    expect(sectionPaths.agents).toBe("/agents");
    expect(resolveSectionLocation("/agents")).toEqual({
      section: "agents",
      path: "/agents"
    });
  });

  it("keeps agent detail paths in the Agents section", () => {
    expect(resolveSectionLocation("/agents/1/")).toEqual({
      section: "agents",
      path: "/agents/1"
    });
    expect(getAgentIdFromPath("/agents/1")).toBe("1");
    expect(getAgentIdFromPath("/agents/data%20agent")).toBe("data agent");
  });

  it("redirects the retired Weekly Reporter test route", () => {
    expect(resolveSectionLocation("/test-agent/")).toEqual({
      section: "agents",
      path: "/agents/1"
    });
    expect(navItems.map(({ id }) => id)).not.toContain("test-agent");
  });

  it("resolves the RAG route and keeps it immediately before Settings", () => {
    expect(sectionPaths.rag).toBe("/rag");
    expect(resolveSectionLocation("/rag")).toEqual({
      section: "rag",
      path: "/rag"
    });
    expect(resolveSectionLocation("/rag/")).toEqual({
      section: "rag",
      path: "/rag"
    });

    const ragIndex = navItems.findIndex((item) => item.id === "rag");
    expect(ragIndex).toBeGreaterThan(-1);
    expect(navItems[ragIndex]).toMatchObject({ label: "RAG", path: "/rag" });
    expect(navItems[ragIndex + 1]?.id).toBe("settings");
  });

  it("redirects the legacy Co-workers route, including a trailing slash", () => {
    expect(resolveSectionLocation("/co-workers/")).toEqual({
      section: "agents",
      path: "/agents"
    });
  });

  it("leaves unknown paths unresolved", () => {
    expect(resolveSectionLocation("/not-a-section")).toBeNull();
    expect(resolveSectionLocation("/agents/1/runs")).toBeNull();
  });
});
