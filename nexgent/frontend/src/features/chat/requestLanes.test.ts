import { describe, expect, it } from "vitest";

import { RequestLanes } from "./requestLanes";

describe("RequestLanes", () => {
  it("allows chat and Weekly Reporter to run independently", () => {
    const lanes = new RequestLanes();
    const weeklyReport = lanes.start("weekly-report");
    const chat = lanes.start("chat");

    expect(weeklyReport).not.toBeNull();
    expect(chat).not.toBeNull();
    lanes.cancel("chat");
    expect(chat?.signal.aborted).toBe(true);
    expect(weeklyReport?.signal.aborted).toBe(false);
  });

  it("permits only one request within each lane", () => {
    const lanes = new RequestLanes();
    const first = lanes.start("chat");

    expect(lanes.start("chat")).toBeNull();
    if (first) {
      lanes.finish("chat", first);
    }
    expect(lanes.start("chat")).not.toBeNull();
  });

  it("cancels both lanes during page teardown", () => {
    const lanes = new RequestLanes();
    const chat = lanes.start("chat");
    const weeklyReport = lanes.start("weekly-report");

    lanes.cancelAll();

    expect(chat?.signal.aborted).toBe(true);
    expect(weeklyReport?.signal.aborted).toBe(true);
  });
});
