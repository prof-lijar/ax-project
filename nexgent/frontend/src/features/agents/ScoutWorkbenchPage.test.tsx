import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { getScoutScheduleRefetchInterval } from "../../shared/api/queries";
import {
  ScoutClientError,
  type ScoutRunFailure,
  type ScoutRunResponse
} from "../../shared/api/scoutClient";
import type {
  ScheduledScoutRunFailure,
  ScheduledScoutRunSuccess,
  ScoutScheduleRecord,
  ScoutScheduleStatus
} from "../../shared/api/scoutScheduleClient";
import {
  buildScoutScheduleRequest,
  calculateNextScoutRecurringRun,
  cancelScoutScheduleAndRefresh,
  calculateElapsedSeconds,
  createScoutScheduleAndRefresh,
  formatCompletedDuration,
  formatElapsedDuration,
  formatScoutNextRun,
  formatScoutRecurrenceDescription,
  formatPersistedScheduleRule,
  formatScoutCompletedAt,
  parseScoutKeywords,
  ScoutWorkbenchView,
  validateScoutForm,
  validateScoutScheduleForm
} from "./ScoutWorkbenchPage";

const result: ScoutRunResponse = {
  run_id: "20260828T103000Z-abc123",
  status: "success",
  started_at: "2026-08-28T01:30:00+00:00",
  completed_at: "2026-08-28T01:31:17.896000+00:00",
  duration_seconds: 77.896,
  source_count: 1,
  report: "# Scout Report\n\n## Topic\n\n고독사 예방\n\n## Summary\n\n**근거 기반** 요약입니다.\n\n## Key Findings\n\n- 첫 번째 결과\n\n## Sources\n\n- https://example.com/source",
  sources: ["https://example.com/source"],
  report_artifact: "runs/20260828T103000Z-abc123/report.md",
  log_artifact: "runs/20260828T103000Z-abc123/execution.jsonl"
};

const failedRun: ScoutRunFailure = {
  run_id: "20260828T103200Z-failed",
  status: "failed",
  started_at: "2026-08-28T01:32:00+00:00",
  completed_at: "2026-08-28T01:32:12.341000+00:00",
  duration_seconds: 12.341,
  source_count: 0,
  log_artifact: "runs/20260828T103200Z-failed/execution.jsonl"
};

describe("ScoutWorkbenchPage Run Now", () => {
  it("requires a non-empty topic", () => {
    expect(validateScoutForm("", "AI 돌봄")).toBe(
      "Enter a topic containing 3 to 500 characters."
    );
    expect(validateScoutForm("  ok  ", "")).toBe(
      "Enter a topic containing 3 to 500 characters."
    );
  });

  it("renders and validates optional subordinate research instructions", () => {
    const markup = renderView({
      additionalInstructions: "Organize findings by competitor."
    });

    expect(markup).toContain('id="scout-additional-instructions"');
    expect(markup).toContain("Additional research instructions");
    expect(markup).toContain(
      "Optional. Guides this run or schedule but cannot change Scout&#x27;s source and safety rules."
    );
    expect(validateScoutForm("valid topic", "", "x".repeat(2_001))).toBe(
      "Additional research instructions must contain no more than 2,000 characters."
    );
    expect(validateScoutForm("valid topic", "", " \n ")).toBeNull();
  });

  it("parses comma- and newline-separated keywords and removes duplicates", () => {
    expect(parseScoutKeywords("AI 돌봄, IoT 모니터링\n고독사 예방, ai 돌봄")).toEqual([
      "AI 돌봄",
      "IoT 모니터링",
      "고독사 예방"
    ]);
  });

  it("keeps Run Now visually separate and renders its successful result", () => {
    const markup = renderView({ result });

    expect(markup).toContain(">Run Now</button>");
    expect(markup).toContain("Schedule Scout");
    expect(markup).toContain("<h1>Scout Report</h1>");
    expect(markup).toContain('href="https://example.com/source"');
    expect(markup).toContain(result.run_id);
    expect(markup).toContain(result.report_artifact);
    expect(markup).toContain(result.log_artifact);
    const labels = [
      "Status",
      "Duration",
      "Completed",
      "Sources",
      "Run ID",
      "Report artifact",
      "Execution log"
    ];
    const positions = labels.map((label) => markup.lastIndexOf(`<dt>${label}</dt>`));
    expect(positions.every((position) => position >= 0)).toBe(true);
    expect(positions).toEqual([...positions].sort((left, right) => left - right));
    expect(markup).toContain("01:18");
    expect(markup).toContain("2026-08-28 10:31:17 KST");
  });

  it("disables Run Now inputs and shows only honest elapsed status", () => {
    const markup = renderView({ isPending: true, elapsedSeconds: 47 });

    expect(markup).toContain("Scout가 웹 자료를 조사하고 있습니다...");
    expect(markup).toContain("Running Scout…");
    expect(markup).toContain("Elapsed 00:47");
    expect(markup).not.toContain("% complete");
  });

  it("formats elapsed and authoritative terminal timing", () => {
    expect(calculateElapsedSeconds(1_000, 48_999)).toBe(47);
    expect(calculateElapsedSeconds(2_000, 1_000)).toBe(0);
    expect(formatElapsedDuration(47)).toBe("00:47");
    expect(formatCompletedDuration(77.896)).toBe("01:18");
    expect(formatScoutCompletedAt(result.completed_at)).toBe(
      "2026-08-28 10:31:17 KST"
    );
  });

  it("preserves the previous Run Now result through later errors", () => {
    const runError = renderView({
      result,
      apiError: new ScoutClientError("backend detail", 503)
    });
    const scheduleError = renderView({
      result,
      scheduleActionError: "Scheduling API unavailable."
    });

    expect(runError).toContain("Scout is not ready.");
    expect(runError).toContain(result.run_id);
    expect(runError).not.toContain("backend detail");
    expect(scheduleError).toContain("Scheduling API unavailable.");
    expect(scheduleError).toContain(result.run_id);
    expect(scheduleError).toContain("<h1>Scout Report</h1>");
  });

  it("shows failed Run Now timing separately from the preserved report", () => {
    const markup = renderView({
      result,
      failureRun: failedRun,
      apiError: new ScoutClientError("Scout run failed.", 502, failedRun)
    });

    expect(markup).toContain("Latest attempt failed");
    expect(markup).toContain(failedRun.run_id);
    expect(markup).toContain("00:12");
    expect(markup).toContain(result.run_id);
    expect(markup).toContain("<h1>Scout Report</h1>");
  });
});

describe("Scout scheduling form", () => {
  it("renders Once/Daily/Weekly/Monthly and the fixed Asia/Seoul timezone", () => {
    const markup = renderView();

    expect(markup).toContain('id="scout-schedule-recurrence"');
    expect(markup).toContain('<option value="once" selected="">Once</option>');
    expect(markup).toContain('<option value="daily">Daily</option>');
    expect(markup).toContain('<option value="weekly">Weekly</option>');
    expect(markup).toContain('<option value="monthly">Monthly</option>');
    expect(markup).toContain('id="scout-schedule-date"');
    expect(markup).toContain('type="date"');
    expect(markup).toContain('id="scout-schedule-time"');
    expect(markup).toContain('type="time"');
    expect(markup).toContain("Timezone: <strong>Asia/Seoul</strong> (KST)");
  });

  it("rejects past Seoul wall-clock values", () => {
    expect(
      validateScoutScheduleForm(
        "valid topic",
        "",
        "",
        "once",
        "2026-08-29",
        "09:00",
        "monday",
        "1",
        Date.parse("2026-08-29T00:00:01Z")
      )
    ).toEqual({
      error: "Choose a future date and time in Asia/Seoul.",
      runAt: null
    });
  });

  it("builds an unchanged local payload without browser timezone conversion", () => {
    const built = buildScoutScheduleRequest(
      "  고독사 예방 AI IoT 서비스 최근 동향  ",
      "AI 돌봄\nIoT 모니터링",
      "  Focus on public-sector deployment cases.  ",
      "once",
      "2026-08-29",
      "09:00",
      "monday",
      "1",
      Date.parse("2026-08-28T00:00:00Z")
    );

    expect(built).toEqual({
      error: null,
      request: {
        topic: "고독사 예방 AI IoT 서비스 최근 동향",
        keywords: ["AI 돌봄", "IoT 모니터링"],
        additional_instructions: "Focus on public-sector deployment cases.",
        recurrence: "once",
        run_at: "2026-08-29T09:00:00",
        timezone: "Asia/Seoul"
      }
    });
  });

  it("refetches the persisted schedule list after successful creation", async () => {
    const request = buildScoutScheduleRequest(
      "valid topic",
      "AI 돌봄",
      "",
      "once",
      "2026-08-29",
      "09:00",
      "monday",
      "1",
      Date.parse("2026-08-28T00:00:00Z")
    ).request!;
    const created = scheduleRecord("pending");
    const create = vi.fn().mockResolvedValue(created);
    const refetch = vi.fn().mockResolvedValue(undefined);

    await expect(
      createScoutScheduleAndRefresh(request, create, refetch)
    ).resolves.toEqual(created);
    expect(create).toHaveBeenCalledWith(request);
    expect(refetch).toHaveBeenCalledOnce();
  });

  it.each([
    [
      "daily",
      "monday",
      "1",
      { recurrence: "daily", schedule_time: "09:00:00" }
    ],
    [
      "weekly",
      "wednesday",
      "1",
      {
        recurrence: "weekly",
        schedule_time: "09:00:00",
        day_of_week: "wednesday"
      }
    ],
    [
      "monthly",
      "monday",
      "31",
      { recurrence: "monthly", schedule_time: "09:00:00", day_of_month: 31 }
    ]
  ] as const)("builds a %s schedule request", (recurrence, day, monthDay, rule) => {
    const built = buildScoutScheduleRequest(
      "valid topic",
      "AI",
      "",
      recurrence,
      "",
      "09:00",
      day,
      monthDay
    );

    expect(built.request).toEqual({
      topic: "valid topic",
      keywords: ["AI"],
      timezone: "Asia/Seoul",
      ...rule
    });
  });

  it("renders the recurrence-specific controls", () => {
    expect(renderView({ scheduleRecurrence: "daily" })).not.toContain(
      'id="scout-schedule-date"'
    );
    expect(renderView({ scheduleRecurrence: "weekly" })).toContain(
      'id="scout-schedule-weekday"'
    );
    expect(renderView({ scheduleRecurrence: "monthly" })).toContain(
      'id="scout-schedule-month-day"'
    );
  });

  it("renders a compact KST next-run preview for recurring schedules", () => {
    const now = vi.spyOn(Date, "now").mockReturnValue(
      Date.parse("2026-09-01T10:00:00+09:00")
    );
    try {
      const markup = renderView({
        scheduleRecurrence: "weekly",
        scheduleTime: "17:11",
        scheduleDayOfWeek: "monday"
      });

      expect(markup).toContain("Next run: Sep 7, 2026 at 5:11 PM KST");
      expect(markup).toContain("Repeats every Monday");
    } finally {
      now.mockRestore();
    }
  });

  it("does not add a recurrence preview to Once", () => {
    const markup = renderView({
      scheduleRecurrence: "once",
      scheduleTime: "17:11"
    });

    expect(markup).not.toContain("Next run:");
    expect(markup).not.toContain("Repeats daily");
  });
});

describe("Scout recurring next-run calculation", () => {
  it.each([
    [
      "Daily later today",
      "daily",
      "17:11",
      "monday",
      "1",
      "2026-09-01T16:00:00+09:00",
      "2026-09-01T17:11:00+09:00"
    ],
    [
      "Daily after today's time",
      "daily",
      "17:11",
      "monday",
      "1",
      "2026-09-01T18:00:00+09:00",
      "2026-09-02T17:11:00+09:00"
    ],
    [
      "Weekly selected weekday later today",
      "weekly",
      "17:11",
      "monday",
      "1",
      "2026-09-07T16:00:00+09:00",
      "2026-09-07T17:11:00+09:00"
    ],
    [
      "Weekly selected weekday after today's time",
      "weekly",
      "17:11",
      "monday",
      "1",
      "2026-09-07T18:00:00+09:00",
      "2026-09-14T17:11:00+09:00"
    ],
    [
      "Weekly future weekday",
      "weekly",
      "17:11",
      "monday",
      "1",
      "2026-09-01T10:00:00+09:00",
      "2026-09-07T17:11:00+09:00"
    ],
    [
      "Monthly later this month",
      "monthly",
      "17:11",
      "monday",
      "15",
      "2026-09-01T10:00:00+09:00",
      "2026-09-15T17:11:00+09:00"
    ],
    [
      "Monthly after this month's occurrence",
      "monthly",
      "17:11",
      "monday",
      "15",
      "2026-09-15T18:00:00+09:00",
      "2026-10-15T17:11:00+09:00"
    ],
    [
      "Monthly day 31 skips September",
      "monthly",
      "17:11",
      "monday",
      "31",
      "2026-08-31T18:00:00+09:00",
      "2026-10-31T17:11:00+09:00"
    ]
  ] as const)(
    "%s",
    (_label, recurrence, time, weekday, monthDay, now, expected) => {
      const nextRun = calculateNextScoutRecurringRun(
        recurrence,
        time,
        weekday,
        monthDay,
        Date.parse(now)
      );

      expect(nextRun).toBe(Date.parse(expected));
    }
  );

  it("formats the preview and recurrence descriptions explicitly in KST", () => {
    expect(formatScoutNextRun(Date.parse("2026-09-01T17:11:00+09:00"))).toBe(
      "Next run: Sep 1, 2026 at 5:11 PM KST"
    );
    expect(formatScoutRecurrenceDescription("daily", "monday", "1")).toBe(
      "Repeats daily"
    );
    expect(formatScoutRecurrenceDescription("monthly", "monday", "31")).toBe(
      "Repeats on day 31 of every month"
    );
  });
});

describe("persisted Scout schedules", () => {
  it.each([
    ["pending", "Pending"],
    ["running", "Running"],
    ["cancelled", "Cancelled"],
    ["missed", "Missed"]
  ] as const)("renders server status %s as %s", (status, label) => {
    const markup = renderView({ schedules: [scheduleRecord(status)] });
    expect(markup).toContain(`>${label}</span>`);
  });

  it("renders succeeded authoritative Scout timing, sources, and artifacts", () => {
    const scoutRun = successfulScheduledRun();
    const markup = renderView({
      schedules: [scheduleRecord("succeeded", scoutRun)]
    });

    expect(markup).toContain(">Succeeded</span>");
    expect(markup).toContain("01:18");
    expect(markup).toContain("2026-08-28 10:31:17 KST");
    expect(markup).toContain(scoutRun.run_id);
    expect(markup).toContain(scoutRun.report_artifact);
    expect(markup).toContain(scoutRun.log_artifact);
    expect(markup).toContain('href="https://example.com/scheduled"');
    expect(markup).toContain("View scheduled report");
  });

  it("renders failed Scout authoritative timing when supplied", () => {
    const scoutRun = failedScheduledRun();
    const markup = renderView({ schedules: [scheduleRecord("failed", scoutRun)] });

    expect(markup).toContain(">Failed</span>");
    expect(markup).toContain("00:12");
    expect(markup).toContain("2026-08-28 10:32:12 KST");
    expect(markup).toContain(scoutRun.run_id);
    expect(markup).toContain(scoutRun.log_artifact);
  });

  it("renders an active recurring schedule and its latest result", () => {
    const recurring = scheduleRecord("pending", successfulScheduledRun());
    recurring.recurrence = "weekly";
    recurring.schedule_time = "09:30:00";
    recurring.day_of_week = "wednesday";
    recurring.run_at = "2026-09-02T09:30:00";

    const markup = renderView({ schedules: [recurring] });

    expect(formatPersistedScheduleRule(recurring)).toBe(
      "weekly on Wednesday at 09:30 KST"
    );
    expect(markup).toContain("Weekly");
    expect(markup).toContain("Active. Next run: 2026-09-02 09:30:00 KST.");
    expect(markup).toContain("Latest run succeeded");
    expect(markup).toContain(successfulScheduledRun().run_id);
    expect(markup).toContain(">Cancel</button>");
  });

  it("does not fabricate Scout timing for a pre-run failed schedule", () => {
    const schedule = scheduleRecord("failed");
    schedule.error_code = "scout_unreachable";
    schedule.error_message = "Scout service was unavailable.";
    const markup = renderView({ schedules: [schedule] });

    expect(markup).toContain("Scout service was unavailable.");
    expect(markup).not.toContain("<dt>Duration</dt>");
    expect(markup).not.toContain("<dt>Run ID</dt>");
  });

  it("shows Cancel only for pending schedules and retains cancelled audit rows", () => {
    const schedules = ([
      "pending", "running", "succeeded", "failed", "cancelled", "missed"
    ] as ScoutScheduleStatus[]).map((status, index) =>
      scheduleRecord(
        status,
        status === "succeeded" ? successfulScheduledRun() :
          status === "failed" ? failedScheduledRun() : null,
        index
      )
    );
    const markup = renderView({ schedules });

    expect((markup.match(/>Cancel<\/button>/g) ?? [])).toHaveLength(1);
    expect(markup).toContain(">Cancelled</span>");
  });

  it("refetches authoritative state when a cancellation loses a race", async () => {
    const cancel = vi.fn().mockRejectedValue(new Error("already running"));
    const refetch = vi.fn().mockResolvedValue(undefined);

    await expect(
      cancelScoutScheduleAndRefresh(
        "00000000-0000-4000-8000-000000000001",
        cancel,
        refetch
      )
    ).rejects.toThrow("already running");
    expect(refetch).toHaveBeenCalledOnce();
  });

  it("polls while server records are pending/running and stops for terminal audit", () => {
    expect(getScoutScheduleRefetchInterval([scheduleRecord("pending")])).toBe(4_000);
    expect(getScoutScheduleRefetchInterval([scheduleRecord("running")])).toBe(4_000);
    expect(getScoutScheduleRefetchInterval([scheduleRecord("cancelled")])).toBe(false);
    expect(getScoutScheduleRefetchInterval([])).toBe(false);
  });

  it("reconstructs displayed records entirely from GET-backed view data", () => {
    const persisted = scheduleRecord("cancelled");
    const emptyMarkup = renderView({ schedules: [] });
    const reloadedMarkup = renderView({ schedules: [persisted] });

    expect(emptyMarkup).not.toContain(persisted.schedule_id);
    expect(reloadedMarkup).toContain(persisted.schedule_id);
    expect(reloadedMarkup).toContain("Cancelled");
  });
});

function renderView({
  isPending = false,
  elapsedSeconds = 0,
  result = null,
  failureRun = null,
  formError = null,
  apiError = null,
  schedules = [],
  schedulesPending = false,
  schedulesError = null,
  scheduleSubmitting = false,
  cancellingScheduleId = null,
  scheduleFormError = null,
  scheduleActionError = null,
  scheduleNotice = null,
  scheduleRecurrence = "once",
  scheduleTime = "",
  scheduleDayOfWeek = "monday",
  scheduleDayOfMonth = "1",
  additionalInstructions = ""
}: Partial<{
  isPending: boolean;
  elapsedSeconds: number;
  result: ScoutRunResponse | null;
  failureRun: ScoutRunFailure | null;
  formError: string | null;
  apiError: unknown;
  schedules: ScoutScheduleRecord[];
  schedulesPending: boolean;
  schedulesError: unknown;
  scheduleSubmitting: boolean;
  cancellingScheduleId: string | null;
  scheduleFormError: string | null;
  scheduleActionError: string | null;
  scheduleNotice: string | null;
  scheduleRecurrence: ScoutScheduleRecord["recurrence"];
  scheduleTime: string;
  scheduleDayOfWeek: ScoutScheduleRecord["day_of_week"] & string;
  scheduleDayOfMonth: string;
  additionalInstructions: string;
}> = {}) {
  return renderToStaticMarkup(
    <ScoutWorkbenchView
      topic="고독사 예방 AI IoT 서비스 최근 동향"
      keywordText={"AI 돌봄\nIoT 모니터링"}
      additionalInstructions={additionalInstructions}
      isPending={isPending}
      elapsedSeconds={elapsedSeconds}
      result={result}
      failureRun={failureRun}
      formError={formError}
      apiError={apiError}
      scheduleRecurrence={scheduleRecurrence}
      scheduleDate=""
      scheduleTime={scheduleTime}
      scheduleDayOfWeek={scheduleDayOfWeek}
      scheduleDayOfMonth={scheduleDayOfMonth}
      schedules={schedules}
      schedulesPending={schedulesPending}
      schedulesError={schedulesError}
      scheduleSubmitting={scheduleSubmitting}
      cancellingScheduleId={cancellingScheduleId}
      scheduleFormError={scheduleFormError}
      scheduleActionError={scheduleActionError}
      scheduleNotice={scheduleNotice}
      onTopicChange={vi.fn()}
      onKeywordTextChange={vi.fn()}
      onAdditionalInstructionsChange={vi.fn()}
      onScheduleRecurrenceChange={vi.fn()}
      onScheduleDateChange={vi.fn()}
      onScheduleTimeChange={vi.fn()}
      onScheduleDayOfWeekChange={vi.fn()}
      onScheduleDayOfMonthChange={vi.fn()}
      onSubmit={vi.fn()}
      onScheduleSubmit={vi.fn()}
      onCancelSchedule={vi.fn()}
    />
  );
}

function scheduleRecord(
  status: ScoutScheduleStatus,
  scoutRun: ScoutScheduleRecord["scout_run"] = null,
  index = 1
): ScoutScheduleRecord {
  return {
    schedule_id: `00000000-0000-4000-8000-00000000000${index}`,
    topic: "고독사 예방 AI IoT 서비스 최근 동향",
    keywords: ["AI 돌봄", "IoT 모니터링"],
    additional_instructions: "Organize findings by competitor.",
    recurrence: "once",
    run_at: "2026-08-29T09:00:00",
    schedule_time: null,
    day_of_week: null,
    day_of_month: null,
    timezone: "Asia/Seoul",
    trigger_at: "2026-08-29T00:00:00Z",
    status,
    created_at: "2026-08-28T01:00:00Z",
    updated_at: "2026-08-28T01:01:00Z",
    dispatch_started_at: status === "running" ? "2026-08-29T00:00:00Z" : null,
    terminal_at: ["succeeded", "failed", "cancelled", "missed"].includes(status)
      ? "2026-08-29T00:02:00Z"
      : null,
    error_code: null,
    error_message: null,
    scout_run: scoutRun
  };
}

function successfulScheduledRun(): ScheduledScoutRunSuccess {
  return {
    run_id: "20260828T103000Z-scheduled",
    status: "success",
    started_at: "2026-08-28T01:30:00Z",
    completed_at: "2026-08-28T01:31:17.896Z",
    duration_seconds: 77.896,
    source_count: 1,
    report: "# Scout Report\n\n## Topic\n\nScheduled research",
    sources: ["https://example.com/scheduled"],
    report_artifact: "runs/20260828T103000Z-scheduled/report.md",
    log_artifact: "runs/20260828T103000Z-scheduled/execution.jsonl"
  };
}

function failedScheduledRun(): ScheduledScoutRunFailure {
  return {
    run_id: "20260828T103200Z-scheduled-failed",
    status: "failed",
    started_at: "2026-08-28T01:32:00Z",
    completed_at: "2026-08-28T01:32:12.341Z",
    duration_seconds: 12.341,
    source_count: 0,
    log_artifact: "runs/20260828T103200Z-scheduled-failed/execution.jsonl"
  };
}
