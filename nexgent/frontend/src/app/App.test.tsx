import { describe, expect, it } from "vitest";

import { getAgentsRoute } from "./App";

describe("App agent routing", () => {
  it("renders Weekly Reporter with its live workbench", () => {
    expect(getAgentsRoute("1")).toEqual({ kind: "weekly-reporter" });
  });

  it("keeps other catalog agents on the generic detail page", () => {
    expect(getAgentsRoute("2")).toEqual({ kind: "detail", agentId: "2" });
  });

  it("opens Scout in its dedicated workbench", () => {
    expect(getAgentsRoute("ansimk_scout_agent")).toEqual({ kind: "scout" });
  });

  it("renders the catalog when no detail id is active", () => {
    expect(getAgentsRoute(null)).toEqual({ kind: "catalog" });
  });
});
