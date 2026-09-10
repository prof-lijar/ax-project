import { afterEach, describe, expect, it, vi } from "vitest";

import {
  isBulkJobTerminal,
  weeklyReportBulkClient
} from "./weeklyReportBulkClient";

const job = {
  schema_version: "1",
  job_id: "0f02a906-af0a-4d7f-8bd3-acde141e58ac",
  status: "running",
  week_start: "2026-08-17",
  timezone: "Asia/Seoul",
  max_reports: 10000,
  discovered_count: 250,
  pending_count: 218,
  running_count: 32,
  completed_count: 0,
  fallback_count: 0,
  failed_count: 0,
  producer_done: false,
  selection_truncated: false,
  next_cursor: null,
  warnings: [],
  export: null,
  created_at: "2026-08-20T00:00:00Z",
  updated_at: "2026-08-20T00:00:01Z",
  expires_at: null
};

afterEach(() => vi.unstubAllGlobals());

describe("weeklyReportBulkClient", () => {
  it("submits and validates a 10,000-report job", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(job), { status: 201 })
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      weeklyReportBulkClient.submit({
        week_start: "2026-08-17",
        timezone: "Asia/Seoul",
        max_reports: 10000,
        idempotency_key: "ui-2026-08-17-12345678"
      })
    ).resolves.toMatchObject({ max_reports: 10000, running_count: 32 });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/weekly-report-bulk-api/v1/weekly-report/bulk/jobs");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toMatchObject({ persist_reports: false });
  });

  it("loads runtime limits and recent jobs", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            schema_version: "1",
            max_reports: 10000,
            source_page_size: 100,
            worker_concurrency: 32,
            status_poll_seconds: 2
          })
        )
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ schema_version: "1", jobs: [job] }))
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(weeklyReportBulkClient.runtime()).resolves.toMatchObject({
      worker_concurrency: 32
    });
    await expect(weeklyReportBulkClient.listJobs()).resolves.toHaveLength(1);
  });

  it("rejects malformed progress instead of showing misleading counts", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ ...job, running_count: -1 }))
      )
    );

    await expect(weeklyReportBulkClient.status(job.job_id)).rejects.toThrow(
      "invalid response"
    );
  });

  it("keeps a page-lifecycle cancellation request alive", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ...job, status: "cancelling" }))
    );
    vi.stubGlobal("fetch", fetchMock);

    await weeklyReportBulkClient.cancel(job.job_id, { keepalive: true });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect(init.keepalive).toBe(true);
  });

  it("classifies terminal states", () => {
    expect(isBulkJobTerminal("running")).toBe(false);
    expect(isBulkJobTerminal("completed")).toBe(true);
    expect(isBulkJobTerminal("cancelled")).toBe(true);
  });
});

it("aborts a stalled status request after 30 seconds", async () => {
  vi.useFakeTimers();
  let signal: AbortSignal | undefined;
  vi.stubGlobal("fetch", vi.fn((_url, init) => new Promise((_resolve, reject) => {
    signal = init.signal;
    signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
  })));
  try {
    const result = expect(weeklyReportBulkClient.status(job.job_id)).rejects.toThrow("timed out");
    await vi.advanceTimersByTimeAsync(30_000);
    await result;
    expect(signal?.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  } finally {
    vi.useRealTimers();
  }
});

it("preserves caller cancellation and clears the deadline", async () => {
  vi.useFakeTimers();
  const controller = new AbortController();
  vi.stubGlobal("fetch", vi.fn((_url, init) => new Promise((_resolve, reject) => {
    init.signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
  })));
  try {
    const result = expect(weeklyReportBulkClient.status(job.job_id, { signal: controller.signal })).rejects.toThrow("cancelled");
    controller.abort();
    await result;
    expect(vi.getTimerCount()).toBe(0);
  } finally {
    vi.useRealTimers();
  }
});


it("submits selected wards with report persistence disabled", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(job), { status: 201 }));
  vi.stubGlobal("fetch", fetchMock);
  await weeklyReportBulkClient.submit({
    week_start: "2026-08-31", timezone: "Asia/Seoul", max_reports: 3,
    ward_ids: [23, 45, 56], idempotency_key: "selected-ward-ui-test"
  });
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({
    ward_ids: [23, 45, 56], max_reports: 3, persist_reports: false
  });
});
