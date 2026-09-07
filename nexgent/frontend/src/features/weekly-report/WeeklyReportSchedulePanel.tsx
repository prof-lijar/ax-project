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
          <h2 id="weekly-schedule-title">Default schedule</h2>
          <p>Choose when this agent should prepare the weekly report.</p>
        </div>
        <span className={styles.prototypeBadge}>Server cron</span>
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
            <strong>Scheduled runs</strong>
            <small>The server default runs automatically each week.</small>
          </span>
        </label>

        <div className={styles.fields}>
          <label className={styles.field}>
            <span>Day</span>
            <select
              value={weekday}
              disabled={!enabled}
              onChange={(event) => setWeekday(event.target.value as Weekday)}
            >
              {WEEKDAYS.map((day) => (
                <option key={day} value={day}>
                  {capitalize(day)}
                </option>
              ))}
            </select>
          </label>

          <label className={styles.field}>
            <span>Time</span>
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
            <span>Repeat</span>
            <span className={styles.inputWithIcon}>
              <Repeat2 size={15} aria-hidden />
              <select defaultValue="weekly" disabled={!enabled}>
                <option value="weekly">Weekly</option>
              </select>
            </span>
          </label>

          <div className={styles.field}>
            <span>Time zone</span>
            <span className={styles.timezoneValue}>
              <strong>Asia/Seoul</strong>
              <small>Korean Standard Time</small>
            </span>
          </div>
        </div>

        <footer className={styles.footer}>
          <div className={styles.summary}>
            <small>{enabled ? "Planned schedule" : "Schedule paused"}</small>
            <strong>
              {enabled
                ? formatWeeklySchedule(weekday, time)
                : "Automatic runs are off"}
            </strong>
          </div>
          <button type="submit" disabled aria-describedby="schedule-ui-note">
            <Save size={15} aria-hidden />
            Save schedule
          </button>
        </footer>

        <p className={styles.connectionNote} id="schedule-ui-note">
          Server cron is configured for every Monday at 3:00 AM. UI changes
          are previews only and are not saved yet.
        </p>
      </form>
    </section>
  );
}

export function formatWeeklySchedule(weekday: Weekday, time: string) {
  const match = /^(\d{2}):(\d{2})$/.exec(time);
  if (!match) {
    return "Every " + capitalize(weekday) + " · choose a time";
  }

  const hour = Number(match[1]);
  const minute = match[2];
  const period = hour >= 12 ? "PM" : "AM";
  const displayHour = hour % 12 || 12;

  return (
    "Every " +
    capitalize(weekday) +
    " at " +
    displayHour +
    ":" +
    minute +
    " " +
    period
  );
}

function capitalize(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}
