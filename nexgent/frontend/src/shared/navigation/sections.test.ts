import { describe, expect, it } from "vitest";

import { resolveSectionLocation, sectionPaths } from "./sections";

describe("section routing", () => {
  it("uses /agents as the canonical Agents route", () => {
    expect(sectionPaths.agents).toBe("/agents");
    expect(resolveSectionLocation("/agents")).toEqual({
      section: "agents",
      path: "/agents"
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
  });
});
