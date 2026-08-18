import { describe, expect, it } from "vitest";

import { getAgentsRoute } from "./App";

describe("App agent routing", () => {
  it("renders every catalog agent id with the dedicated detail page", () => {
    expect(getAgentsRoute("1")).toEqual({ kind: "detail", agentId: "1" });
    expect(getAgentsRoute("2")).toEqual({ kind: "detail", agentId: "2" });
  });

  it("renders the catalog when no detail id is active", () => {
    expect(getAgentsRoute(null)).toEqual({ kind: "catalog" });
  });
});
