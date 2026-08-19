import { describe, expect, it } from "vitest";

import type { WeeklyReportBatchResult } from "../../shared/types/weeklyReport";
import {
  buildWeeklyReportRequest,
  parseReportLimit,
  selectWeeklyReport
} from "./TestAgentPage";

const threeReportBatch = {
  reports: [
    { ward_id: 101 },
    { ward_id: 202 },
    { ward_id: 303 }
  ]
} as unknown as WeeklyReportBatchResult;

describe("Weekly Reporter report selection", () => {
  it("shows the first of three generated reports by default", () => {
    expect(selectWeeklyReport(threeReportBatch, null)?.ward_id).toBe(101);
  });

  it("shows the explicitly selected report and falls back safely", () => {
    expect(selectWeeklyReport(threeReportBatch, 303)?.ward_id).toBe(303);
    expect(selectWeeklyReport(threeReportBatch, 999)?.ward_id).toBe(101);
  });
});

describe("Weekly Reporter batch size", () => {
  it.each([
    ["1", 1],
    ["3", 3],
    ["12", 12],
    ["25", 25]
  ])("accepts %s reports", (input, expected) => {
    expect(parseReportLimit(input)).toBe(expected);
  });

  it.each(["", "0", "26", "3.5", "-1", "abc", " 3 "])(
    "rejects an invalid report count of %p",
    (input) => {
      expect(parseReportLimit(input)).toBeNull();
    }
  );

  it("passes the selected count into the weekly reporter request", () => {
    expect(
      buildWeeklyReportRequest("2026-08-03", "Asia/Seoul", "12")
    ).toEqual({
      week_start: "2026-08-03",
      timezone: "Asia/Seoul",
      limit: 12
    });
  });

  it("does not build a request for an invalid count", () => {
    expect(
      buildWeeklyReportRequest("2026-08-03", "Asia/Seoul", "26")
    ).toBeNull();
  });
});
