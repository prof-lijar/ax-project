import { describe, expect, it } from "vitest";

import type { WeeklyReportBulkJobStatus } from "../../shared/api/weeklyReportBulkClient";
import {
  calculateBulkProgress,
  parseBulkReportLimit
} from "./BulkWeeklyReportPanel";

describe("bulk weekly report inputs", () => {
  it.each([["1", 1], ["1000", 1000], ["10000", 10000]])(
    "accepts %s reports",
    (input, expected) => expect(parseBulkReportLimit(input)).toBe(expected)
  );

  it.each(["", "0", "10001", "1.5", "-2", "abc"])(
    "rejects %p",
    (input) => expect(parseBulkReportLimit(input)).toBeNull()
  );
});

describe("bulk weekly report progress", () => {
  it("calculates end-to-end throughput and projection", () => {
    const job = {
      status: "running",
      max_reports: 1000,
      completed_count: 100,
      failed_count: 0,
      created_at: "2026-08-20T00:00:00Z"
    } as WeeklyReportBulkJobStatus;

    expect(
      calculateBulkProgress(job, Date.parse("2026-08-20T00:01:40Z"))
    ).toEqual({
      percent: 10,
      elapsedSeconds: 100,
      reportsPerSecond: 1,
      etaLabel: "15m 0s"
    });
  });
});
