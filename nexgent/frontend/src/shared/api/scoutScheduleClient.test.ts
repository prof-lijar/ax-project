import { afterEach, describe, expect, it, vi } from "vitest";

import {
  SCOUT_SCHEDULE_STATUSES,
  ScoutScheduleClientError,
  resolveScoutSchedulerServerBaseUrl,
  scoutScheduleClient,
  type ScoutScheduleRecord
} from "./scoutScheduleClient";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("scoutScheduleClient", () => {
  it("serializes create requests without converting local run_at", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(scheduleRecord()));
    vi.stubGlobal("fetch", fetchMock);

    await scoutScheduleClient.create({
      topic: "  고독사 예방 AI IoT 서비스 최근 동향  ",
      keywords: [" AI 돌봄 ", "IoT 모니터링"],
      additional_instructions: "  Organize findings by competitor.  ",
      recurrence: "once",
      run_at: "2026-08-29T09:00:00",
      timezone: "Asia/Seoul"
    });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/scout-scheduler-api/v1/scout/schedules");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      topic: "고독사 예방 AI IoT 서비스 최근 동향",
      keywords: ["AI 돌봄", "IoT 모니터링"],
      additional_instructions: "Organize findings by competitor.",
      recurrence: "once",
      run_at: "2026-08-29T09:00:00",
      timezone: "Asia/Seoul"
    });
  });

  it("omits blank additional instructions from create requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(scheduleRecord()));
    vi.stubGlobal("fetch", fetchMock);

    await scoutScheduleClient.create({
      topic: "valid topic",
      keywords: [],
      additional_instructions: " \n ",
      recurrence: "once",
      run_at: "2026-08-29T09:00:00",
      timezone: "Asia/Seoul"
    });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).not.toHaveProperty(
      "additional_instructions"
    );
  });

  it.each([
    ["daily", { schedule_time: "09:15:00" }],
    ["weekly", { schedule_time: "10:30:00", day_of_week: "friday" }],
    ["monthly", { schedule_time: "18:45:00", day_of_month: 31 }]
  ] as const)("serializes a %s recurrence rule", async (recurrence, fields) => {
    const record = scheduleRecord({ recurrence, ...fields, run_at: "2026-09-01T09:15:00" });
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(record));
    vi.stubGlobal("fetch", fetchMock);

    await scoutScheduleClient.create({
      topic: "Recurring Scout topic",
      keywords: [],
      recurrence,
      timezone: "Asia/Seoul",
      ...fields
    });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({
      topic: "Recurring Scout topic",
      keywords: [],
      recurrence,
      timezone: "Asia/Seoul",
      ...fields
    });
  });

  it("uses the configured standalone Scheduling API base URL", async () => {
    vi.stubEnv(
      "VITE_SCOUT_SCHEDULER_API_BASE_URL",
      "  http://192.168.0.18:8092/  "
    );
    vi.resetModules();
    const { scoutScheduleClient: configuredClient } = await import(
      "./scoutScheduleClient"
    );
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ schedules: [] })
    );
    vi.stubGlobal("fetch", fetchMock);

    await configuredClient.list();

    expect(fetchMock).toHaveBeenCalledWith(
      "/scout-scheduler-api/v1/scout/schedules",
      expect.objectContaining({ method: "GET" })
    );
    expect(resolveScoutSchedulerServerBaseUrl("http://host:8092///")).toBe(
      "/scout-scheduler-api"
    );
  });

  it("parses all supported server-persisted statuses", async () => {
    const schedules = SCOUT_SCHEDULE_STATUSES.map((status, index) =>
      scheduleRecord({
        schedule_id: `00000000-0000-4000-8000-00000000000${index}`,
        status,
        terminal_at: ["succeeded", "failed", "cancelled", "missed"].includes(status)
          ? "2026-08-28T01:01:00Z"
          : null,
        scout_run:
          status === "succeeded"
            ? successfulScoutRun()
            : status === "failed"
              ? failedScoutRun()
              : null
      })
    );
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ schedules }))
    );

    await expect(scoutScheduleClient.list()).resolves.toEqual({ schedules });
  });

  it("lists and accepts valid successful authoritative Scout metadata", async () => {
    const schedule = scheduleRecord({
      status: "succeeded",
      terminal_at: "2026-08-28T01:02:00Z",
      scout_run: successfulScoutRun()
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ schedules: [schedule] }))
    );

    await expect(scoutScheduleClient.list()).resolves.toEqual({
      schedules: [schedule]
    });
  });

  it("accepts legacy schedule records without additional instructions", async () => {
    const schedule = scheduleRecord();
    const { additional_instructions: _omitted, ...legacySchedule } = schedule;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ schedules: [legacySchedule] }))
    );

    const response = await scoutScheduleClient.list();

    expect(response.schedules[0].additional_instructions).toBeNull();
  });

  it("cancels the UUID schedule without removing its returned audit record", async () => {
    const cancelled = scheduleRecord({
      status: "cancelled",
      terminal_at: "2026-08-28T01:02:00Z"
    });
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(cancelled));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      scoutScheduleClient.cancel(cancelled.schedule_id)
    ).resolves.toEqual(cancelled);
    expect(fetchMock).toHaveBeenCalledWith(
      `/scout-scheduler-api/v1/scout/schedules/${cancelled.schedule_id}`,
      expect.objectContaining({ method: "DELETE" })
    );
  });

  it("accepts an active recurring schedule with latest Scout metadata", async () => {
    const schedule = scheduleRecord({
      recurrence: "daily",
      schedule_time: "09:15:00",
      run_at: "2026-09-01T09:15:00",
      trigger_at: "2026-09-01T00:15:00Z",
      status: "pending",
      terminal_at: "2026-08-31T00:16:00Z",
      scout_run: successfulScoutRun()
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ schedules: [schedule] }))
    );

    await expect(scoutScheduleClient.list()).resolves.toEqual({
      schedules: [schedule]
    });
  });

  it.each([
    ["malformed status", { status: "complete" }],
    ["malformed schedule timestamp", { updated_at: "yesterday" }],
    [
      "malformed Scout timestamp",
      { status: "succeeded", scout_run: successfulScoutRun({ completed_at: "bad" }) }
    ],
    [
      "negative duration",
      { status: "succeeded", scout_run: successfulScoutRun({ duration_seconds: -1 }) }
    ],
    [
      "negative source count",
      { status: "succeeded", scout_run: successfulScoutRun({ source_count: -1 }) }
    ],
    [
      "mismatched source count",
      { status: "succeeded", scout_run: successfulScoutRun({ source_count: 2 }) }
    ],
    [
      "unexpected failed-run sources",
      { status: "failed", scout_run: { ...failedScoutRun(), sources: ["https://example.com"] } }
    ]
  ])("rejects %s", async (_label, updates) => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ schedules: [scheduleRecord(updates)] })
      )
    );

    await expect(scoutScheduleClient.list()).rejects.toMatchObject({
      message: "The Scout scheduling service returned an unexpected response."
    });
  });

  it.each(["failed", "missed", "cancelled"] as const)(
    "allows %s schedules without fabricated Scout metadata",
    async (status) => {
      const schedule = scheduleRecord({
        status,
        terminal_at: "2026-08-28T01:02:00Z",
        error_code: status === "failed" ? "scout_unreachable" : null,
        error_message:
          status === "failed" ? "Scout service was unavailable." : null,
        scout_run: null
      });
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(jsonResponse({ schedules: [schedule] }))
      );

      const response = await scoutScheduleClient.list();
      expect(response.schedules[0].scout_run).toBeNull();
    }
  );

  it("surfaces safe cancellation conflicts", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ detail: "Only a pending schedule may be cancelled." }, 409)
      )
    );

    await expect(
      scoutScheduleClient.cancel("00000000-0000-4000-8000-000000000001")
    ).rejects.toMatchObject({
      status: 409,
      message: "Only a pending schedule may be cancelled."
    });
  });

  it("rejects malformed create input before using the network", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      scoutScheduleClient.create({
        topic: "valid topic",
        keywords: [],
        recurrence: "once",
        run_at: "2026-08-29T09:00:00Z",
        timezone: "Asia/Seoul"
      })
    ).rejects.toBeInstanceOf(ScoutScheduleClientError);
    await expect(
      scoutScheduleClient.create({
        topic: "valid topic",
        keywords: [],
        additional_instructions: "x".repeat(2_001),
        recurrence: "once",
        run_at: "2026-08-29T09:00:00",
        timezone: "Asia/Seoul"
      })
    ).rejects.toBeInstanceOf(ScoutScheduleClientError);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

function scheduleRecord(
  updates: Record<string, unknown> = {}
): ScoutScheduleRecord {
  return {
    schedule_id: "00000000-0000-4000-8000-000000000001",
    topic: "고독사 예방 AI IoT 서비스 최근 동향",
    keywords: ["AI 돌봄", "IoT 모니터링"],
    additional_instructions: null,
    recurrence: "once",
    run_at: "2026-08-29T09:00:00",
    schedule_time: null,
    day_of_week: null,
    day_of_month: null,
    timezone: "Asia/Seoul",
    trigger_at: "2026-08-29T00:00:00Z",
    status: "pending",
    created_at: "2026-08-28T01:00:00Z",
    updated_at: "2026-08-28T01:00:00Z",
    dispatch_started_at: null,
    terminal_at: null,
    error_code: null,
    error_message: null,
    scout_run: null,
    ...updates
  } as ScoutScheduleRecord;
}

function successfulScoutRun(updates: Record<string, unknown> = {}) {
  return {
    run_id: "20260828T103000Z-abc123",
    status: "success",
    started_at: "2026-08-28T01:30:00Z",
    completed_at: "2026-08-28T01:31:17.896Z",
    duration_seconds: 77.896,
    source_count: 1,
    report: "# Scout Report\n\n## Topic\n\nAI 돌봄",
    sources: ["https://example.com/source"],
    report_artifact: "runs/20260828T103000Z-abc123/report.md",
    log_artifact: "runs/20260828T103000Z-abc123/execution.jsonl",
    ...updates
  };
}

function failedScoutRun() {
  return {
    run_id: "20260828T103200Z-failed",
    status: "failed",
    started_at: "2026-08-28T01:32:00Z",
    completed_at: "2026-08-28T01:32:12.341Z",
    duration_seconds: 12.341,
    source_count: 0,
    log_artifact: "runs/20260828T103200Z-failed/execution.jsonl"
  };
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}
