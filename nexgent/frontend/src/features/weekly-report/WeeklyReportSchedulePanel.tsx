import { t, useLanguage } from "../../shared/i18n";
import { CalendarClock, Clock3, Repeat2, Save } from "lucide-react";
import { useState, type FormEvent } from "react";

import styles from "./WeeklyReportSchedulePanel.module.css";

const WEEKDAYS = [
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
] as const;

type Weekday = (typeof WEEKDAYS)[number];

export function WeeklyReportSchedulePanel() {
  useLanguage((state) => state.language);
  const [enabled, setEnabled] = useState(true);
  const [weekday, setWeekday] = useState<Weekday>("monday");
  const [time, setTime] = useState("03:00");

  function preventPrototypeSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
  }

  return (
    <section className={styles.panel} aria-labelledby="weekly-schedule-title">
      <header className={styles.panelHeader}>
        <span className={styles.headerIcon} aria-hidden>
          <CalendarClock size={19} />
        </span>
        <div>
          <h2 id="weekly-schedule-title">{t("Default schedule")}</h2>
          <p>{t("Choose when this agent should prepare the weekly report.")}</p>
        </div>
        <span className={styles.prototypeBadge}>{t("Server cron")}</span>
      </header>

      <form className={styles.form} onSubmit={preventPrototypeSubmit}>
        <label className={styles.enabledControl}>
          <input
            type="checkbox"
            checked={enabled}
            onChange={(event) => setEnabled(event.target.checked)}
          />
          <span className={styles.switchTrack} aria-hidden>
            <span className={styles.switchThumb} />
          </span>
          <span>
            <strong>{t("Scheduled runs")}</strong>
            <small>{t("The server default runs automatically each week.")}</small>
          </span>
        </label>

        <div className={styles.fields}>
          <label className={styles.field}>
            <span>{t("Day")}</span>
            <select
              value={weekday}
              disabled={!enabled}
              onChange={(event) => setWeekday(event.target.value as Weekday)}
            >
              {WEEKDAYS.map((day) => (
                <option key={day} value={day}>
                  {t(capitalize(day))}
                </option>
              ))}
            </select>
          </label>

          <label className={styles.field}>
            <span>{t("Time")}</span>
            <span className={styles.inputWithIcon}>
              <Clock3 size={15} aria-hidden />
              <input
                type="time"
                step="60"
                value={time}
                disabled={!enabled}
                onChange={(event) => setTime(event.target.value)}
              />
            </span>
          </label>

          <label className={styles.field}>
            <span>{t("Repeat")}</span>
            <span className={styles.inputWithIcon}>
              <Repeat2 size={15} aria-hidden />
              <select defaultValue="weekly" disabled={!enabled}>
                <option value="weekly">{t("Weekly")}</option>
              </select>
            </span>
          </label>

          <div className={styles.field}>
            <span>{t("Time zone")}</span>
            <span className={styles.timezoneValue}>
              <strong>Asia/Seoul</strong>
              <small>{t("Korean Standard Time")}</small>
            </span>
          </div>
        </div>

        <footer className={styles.footer}>
          <div className={styles.summary}>
            <small>{enabled ? t("Planned schedule") : t("Schedule paused")}</small>
            <strong>
              {enabled
                ? formatWeeklySchedule(weekday, time)
                : t("Automatic runs are off")}
            </strong>
          </div>
          <button type="submit" disabled aria-describedby="schedule-ui-note">
            <Save size={15} aria-hidden />
            {t("Save schedule")}
          </button>
        </footer>

        <p className={styles.connectionNote} id="schedule-ui-note">
          {t("Server cron is configured for every Monday at 3:00 AM. UI changes are previews only and are not saved yet.")}
        </p>
      </form>
    </section>
  );
}

export function formatWeeklySchedule(weekday: Weekday, time: string) {
  const match = /^(\d{2}):(\d{2})$/.exec(time);
  if (!match) {
    return t("Every {day} · choose a time", { day: t(capitalize(weekday)) });
  }

  const hour = Number(match[1]);
  const minute = match[2];
  const period = t(hour >= 12 ? "PM" : "AM");
  const displayHour = hour % 12 || 12;

  return t("Every {day} at {hour}:{minute} {period}", {
    day: t(capitalize(weekday)), hour: displayHour, minute, period
  });
}

function capitalize(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}
