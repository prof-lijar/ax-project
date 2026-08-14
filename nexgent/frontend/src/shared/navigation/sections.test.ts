import { describe, expect, it } from "vitest";

import {
  getAgentIdFromPath,
  resolveSectionLocation,
  sectionPaths
} from "./sections";

describe("section routing", () => {
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

  it("resolves the weekly reporter test route", () => {
    expect(sectionPaths["test-agent"]).toBe("/test-agent");
    expect(resolveSectionLocation("/test-agent/")).toEqual({
      section: "test-agent",
      path: "/test-agent"
    });
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
