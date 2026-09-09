import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { WeeklyReportBulkJobStatus } from "../../shared/api/weeklyReportBulkClient";
import {
  calculateBulkProgress,
  RunStatusIndicator,
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


describe("Run Agent completion", () => {
  const job = {
    status: "completed",
    max_reports: 10000,
    discovered_count: 20,
    producer_done: true,
    completed_count: 20,
    failed_count: 0,
    created_at: "2026-09-08T00:00:00Z",
    updated_at: "2026-09-08T00:02:03Z"
  } as WeeklyReportBulkJobStatus;

  it.each(["completed", "partial", "failed", "cancelled", "expired"] as const)(
    "freezes elapsed time for %s even when viewed later",
    (status) => {
      const result = calculateBulkProgress({ ...job, status }, Date.parse("2026-09-09T00:00:00Z"));
      expect(result.elapsedSeconds).toBe(123);
      expect(result.etaLabel).toBe("Finished");
      expect(result).toEqual(calculateBulkProgress({ ...job, status }, Date.parse("2026-09-10T00:00:00Z")));
    }
  );

  it("reaches 100 percent when fewer wards exist than the request limit", () => {
    expect(calculateBulkProgress(job, Date.now()).percent).toBe(100);
  });

  it("does not claim failed reports were successful", () => {
    const markup = renderToStaticMarkup(createElement(RunStatusIndicator, { job: { ...job, status: "partial" } }));
    expect(markup).toContain("Completed with failures");
    expect(markup).not.toContain("loader-circle");
  });

  it("shows a running indicator until packaging finishes", () => {
    const markup = renderToStaticMarkup(createElement(RunStatusIndicator, { job: { ...job, status: "finalizing" } }));
    expect(markup).toContain("Packaging");
    expect(markup).toContain("loader-circle");
  });
});
