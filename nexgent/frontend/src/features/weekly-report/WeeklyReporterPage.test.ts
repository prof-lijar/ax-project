import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  WeeklyReporterPage,
} from "./WeeklyReporterPage";
import { formatWeeklySchedule } from "./WeeklyReportSchedulePanel";

describe("Weekly Reporter page", () => {
  it("offers the UI-only weekly schedule and durable bulk generation", () => {
    const markup = renderToStaticMarkup(createElement(WeeklyReporterPage));

    expect(markup).toContain("Default schedule");
    expect(markup).toContain("Monday");
    expect(markup).toContain("03:00");
    expect(markup).toContain("Weekly");
    expect(markup).toContain("Asia/Seoul");
    expect(markup).toContain("Every Monday at 3:00 AM");
    expect(markup).toContain(
      "Server cron is configured for every Monday at 3:00 AM",
    );
    expect(markup).toContain("Test report generation");
    expect(markup).toContain("Run Agent");
    expect(markup).toContain("All available reports, up to 10,000 per run.");
    expect(markup).not.toContain("Quick preview");
    expect(markup).not.toContain("ansimk_weekly_reporter");
  });

  it("formats afternoon weekly schedules", () => {
    expect(formatWeeklySchedule("friday", "15:30")).toBe(
      "Every Friday at 3:30 PM",
    );
  });
});
