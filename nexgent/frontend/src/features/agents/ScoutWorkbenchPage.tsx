import {
  AlertCircle,
  ArrowLeft,
  Bot,
  CalendarClock,
  ExternalLink,
  LoaderCircle,
  Play,
  Search,
  X
} from "lucide-react";
import { type FormEvent, type MouseEvent, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  useCancelScoutSchedule,
  useCreateScoutSchedule,
  useScoutRun,
  useScoutSchedules
} from "../../shared/api/queries";
import {
  ScoutClientError,
  type ScoutRunFailure,
  type ScoutRunResponse
} from "../../shared/api/scoutClient";
import {
  SCOUT_SCHEDULE_DAYS,
  SCOUT_SCHEDULE_TIMEZONE,
  ScoutScheduleClientError,
  type ScheduledScoutRun,
  type ScoutScheduleCreateRequest,
  type ScoutScheduleDayOfWeek,
  type ScoutScheduleRecord,
  type ScoutScheduleRecurrence,
  type ScoutScheduleStatus
} from "../../shared/api/scoutScheduleClient";
import { navigateToSection } from "../../shared/navigation/sections";
import styles from "./ScoutWorkbenchPage.module.css";

interface ScoutWorkbenchViewProps {
  topic: string;
  keywordText: string;
  additionalInstructions: string;
  isPending: boolean;
  elapsedSeconds: number;
  result: ScoutRunResponse | null;
  failureRun: ScoutRunFailure | null;
  formError: string | null;
  apiError: unknown;
  scheduleRecurrence: ScoutScheduleRecurrence;
  scheduleDate: string;
  scheduleTime: string;
  scheduleDayOfWeek: ScoutScheduleDayOfWeek;
  scheduleDayOfMonth: string;
  schedules: ScoutScheduleRecord[];
  schedulesPending: boolean;
  schedulesError: unknown;
  scheduleSubmitting: boolean;
  cancellingScheduleId: string | null;
  scheduleFormError: string | null;
  scheduleActionError: string | null;
  scheduleNotice: string | null;
  onTopicChange: (value: string) => void;
  onKeywordTextChange: (value: string) => void;
  onAdditionalInstructionsChange: (value: string) => void;
  onScheduleRecurrenceChange: (value: ScoutScheduleRecurrence) => void;
  onScheduleDateChange: (value: string) => void;
  onScheduleTimeChange: (value: string) => void;
  onScheduleDayOfWeekChange: (value: ScoutScheduleDayOfWeek) => void;
  onScheduleDayOfMonthChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onScheduleSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onCancelSchedule: (scheduleId: string) => void;
  onBack?: (event: MouseEvent<HTMLAnchorElement>) => void;
}

export function ScoutWorkbenchPage() {
  const [topic, setTopic] = useState("");
  const [keywordText, setKeywordText] = useState("");
  const [additionalInstructions, setAdditionalInstructions] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [latestResult, setLatestResult] = useState<ScoutRunResponse | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [scheduleRecurrence, setScheduleRecurrence] =
    useState<ScoutScheduleRecurrence>("once");
  const [scheduleDate, setScheduleDate] = useState("");
  const [scheduleTime, setScheduleTime] = useState("");
  const [scheduleDayOfWeek, setScheduleDayOfWeek] =
    useState<ScoutScheduleDayOfWeek>("monday");
  const [scheduleDayOfMonth, setScheduleDayOfMonth] = useState("1");
  const [scheduleFormError, setScheduleFormError] = useState<string | null>(null);
  const [scheduleActionError, setScheduleActionError] = useState<string | null>(null);
  const [scheduleNotice, setScheduleNotice] = useState<string | null>(null);
  const [cancellingScheduleId, setCancellingScheduleId] = useState<string | null>(null);
  const runMutation = useScoutRun();
  const schedulesQuery = useScoutSchedules();
  const createScheduleMutation = useCreateScoutSchedule();
  const cancelScheduleMutation = useCancelScoutSchedule();

  useEffect(() => {
    if (!runMutation.isPending) return;
    const startedAt = Date.now();
    setElapsedSeconds(0);
    const interval = window.setInterval(
      () => setElapsedSeconds(calculateElapsedSeconds(startedAt, Date.now())),
      1_000
    );
    return () => window.clearInterval(interval);
  }, [runMutation.isPending]);

  function updateTopic(value: string) {
    setTopic(value);
    setFormError(null);
    setScheduleFormError(null);
    runMutation.reset();
  }

  function updateKeywordText(value: string) {
    setKeywordText(value);
    setFormError(null);
    setScheduleFormError(null);
    runMutation.reset();
  }

  function updateAdditionalInstructions(value: string) {
    setAdditionalInstructions(value);
    setFormError(null);
    setScheduleFormError(null);
    runMutation.reset();
  }

  function clearScheduleFeedback() {
    setScheduleFormError(null);
    setScheduleActionError(null);
    setScheduleNotice(null);
  }

  function submitScoutRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (runMutation.isPending) return;
    const error = validateScoutForm(topic, keywordText, additionalInstructions);
    if (error) {
      setFormError(error);
      return;
    }
    setFormError(null);
    runMutation.reset();
    const normalizedInstructions = normalizeAdditionalInstructions(additionalInstructions);
    runMutation.mutate(
      {
        topic: topic.trim(),
        keywords: parseScoutKeywords(keywordText),
        ...(normalizedInstructions
          ? { additional_instructions: normalizedInstructions }
          : {})
      },
      { onSuccess: setLatestResult }
    );
  }

  async function submitScoutSchedule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (createScheduleMutation.isPending) return;
    const scheduleRequest = buildScoutScheduleRequest(
      topic,
      keywordText,
      additionalInstructions,
      scheduleRecurrence,
      scheduleDate,
      scheduleTime,
      scheduleDayOfWeek,
      scheduleDayOfMonth
    );
    if (scheduleRequest.error || !scheduleRequest.request) {
      setScheduleFormError(scheduleRequest.error);
      return;
    }
    setScheduleFormError(null);
    setScheduleActionError(null);
    setScheduleNotice(null);
    createScheduleMutation.reset();
    try {
      await createScoutScheduleAndRefresh(
        scheduleRequest.request,
        (request) => createScheduleMutation.mutateAsync(request),
        () => schedulesQuery.refetch()
      );
      setScheduleNotice(
        `Scout is scheduled ${formatScoutScheduleRule(scheduleRequest.request)}.`
      );
    } catch (error) {
      setScheduleActionError(getScoutScheduleErrorMessage(error));
    }
  }

  async function cancelScoutSchedule(scheduleId: string) {
    if (cancellingScheduleId) return;
    setCancellingScheduleId(scheduleId);
    setScheduleActionError(null);
    setScheduleNotice(null);
    cancelScheduleMutation.reset();
    try {
      await cancelScoutScheduleAndRefresh(
        scheduleId,
        (id) => cancelScheduleMutation.mutateAsync(id),
        () => schedulesQuery.refetch()
      );
      setScheduleNotice("The pending Scout schedule was cancelled.");
    } catch (error) {
      setScheduleActionError(
        error instanceof ScoutScheduleClientError && error.status === 409
          ? "The schedule had already started or changed state. Its latest status has been refreshed."
          : getScoutScheduleErrorMessage(error)
      );
    } finally {
      setCancellingScheduleId(null);
    }
  }

  function backToAgents(event: MouseEvent<HTMLAnchorElement>) {
    if (
      event.button !== 0 || event.metaKey || event.ctrlKey ||
      event.shiftKey || event.altKey
    ) return;
    event.preventDefault();
    navigateToSection("agents");
  }

  return (
    <ScoutWorkbenchView
      topic={topic}
      keywordText={keywordText}
      additionalInstructions={additionalInstructions}
      isPending={runMutation.isPending}
      elapsedSeconds={elapsedSeconds}
      result={latestResult}
      failureRun={getScoutFailureRun(runMutation.error)}
      formError={formError}
      apiError={runMutation.error}
      scheduleRecurrence={scheduleRecurrence}
      scheduleDate={scheduleDate}
      scheduleTime={scheduleTime}
      scheduleDayOfWeek={scheduleDayOfWeek}
      scheduleDayOfMonth={scheduleDayOfMonth}
      schedules={schedulesQuery.data?.schedules ?? []}
      schedulesPending={schedulesQuery.isPending}
      schedulesError={schedulesQuery.error}
      scheduleSubmitting={createScheduleMutation.isPending}
      cancellingScheduleId={cancellingScheduleId}
      scheduleFormError={scheduleFormError}
      scheduleActionError={scheduleActionError}
      scheduleNotice={scheduleNotice}
      onTopicChange={updateTopic}
      onKeywordTextChange={updateKeywordText}
      onAdditionalInstructionsChange={updateAdditionalInstructions}
      onScheduleRecurrenceChange={(value) => { setScheduleRecurrence(value); clearScheduleFeedback(); }}
      onScheduleDateChange={(value) => { setScheduleDate(value); clearScheduleFeedback(); }}
      onScheduleTimeChange={(value) => { setScheduleTime(value); clearScheduleFeedback(); }}
      onScheduleDayOfWeekChange={(value) => { setScheduleDayOfWeek(value); clearScheduleFeedback(); }}
      onScheduleDayOfMonthChange={(value) => { setScheduleDayOfMonth(value); clearScheduleFeedback(); }}
      onSubmit={submitScoutRun}
      onScheduleSubmit={submitScoutSchedule}
      onCancelSchedule={(scheduleId) => void cancelScoutSchedule(scheduleId)}
      onBack={backToAgents}
    />
  );
}

export function ScoutWorkbenchView(props: ScoutWorkbenchViewProps) {
  const {
    topic, keywordText, additionalInstructions, isPending, elapsedSeconds, result, failureRun,
    formError, apiError, scheduleRecurrence, scheduleDate, scheduleTime,
    scheduleDayOfWeek, scheduleDayOfMonth, schedules,
    schedulesPending, schedulesError, scheduleSubmitting, cancellingScheduleId,
    scheduleFormError, scheduleActionError, scheduleNotice, onTopicChange,
    onKeywordTextChange, onAdditionalInstructionsChange, onScheduleRecurrenceChange, onScheduleDateChange,
    onScheduleTimeChange, onScheduleDayOfWeekChange,
    onScheduleDayOfMonthChange, onSubmit, onScheduleSubmit, onCancelSchedule,
    onBack
  } = props;
  const errorMessage = formError ?? getScoutErrorMessage(apiError);
  const nextRecurringRun = calculateNextScoutRecurringRun(
    scheduleRecurrence,
    scheduleTime,
    scheduleDayOfWeek,
    scheduleDayOfMonth
  );

  return (
    <section className={styles.page}>
      <div className={styles.pageHeading}>
        <a className={styles.backLink} href="/agents" onClick={onBack}>
          <ArrowLeft size={16} aria-hidden /> Back to Agents
        </a>
        <header className={styles.pageHeader}>
          <span className={styles.titleIcon} aria-hidden><Bot size={22} /></span>
          <div>
            <h1>AnsimK Scout Agent</h1>
            <p>Research public web sources and create an evidence-grounded Markdown report.</p>
          </div>
        </header>
      </div>

      <div className={styles.workbench}>
        <aside className={styles.runPanel} aria-label="Scout run configuration">
          <div className={styles.agentIdentity}>
            <span aria-hidden><Search size={19} /></span>
            <div><strong>Research request</strong><small>Google ADK · standalone service</small></div>
          </div>
          <form className={styles.runForm} onSubmit={onSubmit} noValidate>
            <label htmlFor="scout-topic">
              <span>Topic <strong aria-hidden>*</strong></span>
              <textarea
                id="scout-topic" value={topic} rows={5} minLength={3}
                maxLength={500} required disabled={isPending}
                onChange={(event) => onTopicChange(event.target.value)}
                placeholder="고독사 예방 AI IoT 서비스 최근 동향"
                aria-describedby="scout-topic-help"
              />
              <small id="scout-topic-help">Required, 3–500 characters.</small>
            </label>
            <label htmlFor="scout-keywords">
              <span>Keywords</span>
              <textarea
                id="scout-keywords" value={keywordText} rows={5}
                disabled={isPending}
                onChange={(event) => onKeywordTextChange(event.target.value)}
                placeholder={"AI 돌봄\nIoT 모니터링\n고독사 예방"}
                aria-describedby="scout-keywords-help"
              />
              <small id="scout-keywords-help">Optional. Separate up to 10 keywords with commas or new lines.</small>
            </label>
            <label htmlFor="scout-additional-instructions">
              <span>Additional research instructions</span>
              <textarea
                id="scout-additional-instructions" value={additionalInstructions}
                rows={4} maxLength={2_000} disabled={isPending}
                onChange={(event) => onAdditionalInstructionsChange(event.target.value)}
                aria-describedby="scout-additional-instructions-help"
              />
              <small id="scout-additional-instructions-help">
                Optional. Guides this run or schedule but cannot change Scout's source and safety rules.
              </small>
            </label>
            {errorMessage && <InlineError message={errorMessage} />}
            {failureRun && <ScoutFailureDetails run={failureRun} />}
            <button className={styles.runButton} type="submit" disabled={isPending}>
              {isPending
                ? <LoaderCircle className={styles.spinner} size={17} aria-hidden />
                : <Play size={16} aria-hidden />}
              {isPending ? "Running Scout…" : "Run Now"}
            </button>
          </form>
          {isPending && (
            <div className={styles.runningState} role="status" aria-live="polite">
              <LoaderCircle className={styles.spinner} size={18} aria-hidden />
              <div>
                <strong>Scout가 웹 자료를 조사하고 있습니다...</strong>
                <small>Elapsed {formatElapsedDuration(elapsedSeconds)} · This synchronous run may take more than a minute.</small>
              </div>
            </div>
          )}

          <div className={styles.scheduleDivider} />
          <form className={styles.scheduleForm} onSubmit={onScheduleSubmit} noValidate>
            <header className={styles.scheduleFormHeading}>
              <CalendarClock size={17} aria-hidden />
              <div><strong>Schedule Scout</strong><small>Run this same request once or on a recurring schedule.</small></div>
            </header>
            <div className={styles.scheduleFields}>
              <label htmlFor="scout-schedule-recurrence">
                <span>Repeat</span>
                <select id="scout-schedule-recurrence" value={scheduleRecurrence}
                  onChange={(event) => onScheduleRecurrenceChange(event.target.value as ScoutScheduleRecurrence)}>
                  <option value="once">Once</option>
                  <option value="daily">Daily</option>
                  <option value="weekly">Weekly</option>
                  <option value="monthly">Monthly</option>
                </select>
              </label>
              {scheduleRecurrence === "once" && (
                <label htmlFor="scout-schedule-date">
                  <span>Schedule date</span>
                  <input id="scout-schedule-date" type="date" required value={scheduleDate}
                    onChange={(event) => onScheduleDateChange(event.target.value)} />
                </label>
              )}
              {scheduleRecurrence === "weekly" && (
                <label htmlFor="scout-schedule-weekday">
                  <span>Day of week</span>
                  <select id="scout-schedule-weekday" value={scheduleDayOfWeek}
                    onChange={(event) => onScheduleDayOfWeekChange(event.target.value as ScoutScheduleDayOfWeek)}>
                    {SCOUT_SCHEDULE_DAYS.map((day) => (
                      <option key={day} value={day}>{capitalize(day)}</option>
                    ))}
                  </select>
                </label>
              )}
              {scheduleRecurrence === "monthly" && (
                <label htmlFor="scout-schedule-month-day">
                  <span>Day of month</span>
                  <input id="scout-schedule-month-day" type="number" min="1" max="31" required
                    value={scheduleDayOfMonth}
                    onChange={(event) => onScheduleDayOfMonthChange(event.target.value)} />
                </label>
              )}
              <label htmlFor="scout-schedule-time">
                <span>Schedule time</span>
                <input id="scout-schedule-time" type="time" step="60" required value={scheduleTime}
                  onChange={(event) => onScheduleTimeChange(event.target.value)} />
              </label>
            </div>
            <p className={styles.timezoneNote}>Timezone: <strong>{SCOUT_SCHEDULE_TIMEZONE}</strong> (KST)</p>
            {nextRecurringRun !== null && (
              <div className={styles.schedulePreview} aria-live="polite">
                <strong>{formatScoutNextRun(nextRecurringRun)}</strong>
                <span>{formatScoutRecurrenceDescription(
                  scheduleRecurrence,
                  scheduleDayOfWeek,
                  scheduleDayOfMonth
                )}</span>
              </div>
            )}
            {(scheduleFormError || scheduleActionError) &&
              <InlineError message={scheduleFormError ?? scheduleActionError ?? ""} />}
            {scheduleNotice && <p className={styles.scheduleNotice} role="status">{scheduleNotice}</p>}
            <button className={styles.scheduleButton} type="submit"
              disabled={scheduleSubmitting || isPending}>
              {scheduleSubmitting
                ? <LoaderCircle className={styles.spinner} size={17} aria-hidden />
                : <CalendarClock size={16} aria-hidden />}
              {scheduleSubmitting ? "Scheduling…" : "Schedule Scout"}
            </button>
          </form>
        </aside>

        <main className={styles.resultPanel} aria-live="polite">
          {result ? <ScoutResult result={result} /> : (
            <div className={styles.emptyResult}>
              <Search size={24} aria-hidden />
              <h2>Ready for a research topic</h2>
              <p>The latest completed report, sources, and run references will appear here.</p>
            </div>
          )}
        </main>
      </div>

      <ScheduledJobsSection
        schedules={schedules} isPending={schedulesPending} error={schedulesError}
        cancellingScheduleId={cancellingScheduleId} onCancel={onCancelSchedule}
      />
    </section>
  );
}

function InlineError({ message }: { message: string }) {
  return <p className={styles.error} role="alert"><AlertCircle size={16} aria-hidden /><span>{message}</span></p>;
}

function ScoutResult({ result }: { result: ScoutRunResponse }) {
  return (
    <div className={styles.resultContent}>
      <section className={styles.reportSection} aria-labelledby="scout-report">
        <header className={styles.sectionHeading}><h2 id="scout-report">Report</h2><span>Markdown</span></header>
        <MarkdownReport report={result.report} />
      </section>
      <SourcesList sources={result.sources} headingId="scout-sources" />
      <section className={styles.metadataSection} aria-labelledby="scout-run">
        <header className={styles.sectionHeading}><h2 id="scout-run">Run details</h2><span>{result.status}</span></header>
        <ScoutRunMetadata run={result} statusLabel="Success" />
      </section>
    </div>
  );
}

function ScheduledJobsSection({ schedules, isPending, error, cancellingScheduleId, onCancel }: {
  schedules: ScoutScheduleRecord[]; isPending: boolean; error: unknown;
  cancellingScheduleId: string | null; onCancel: (scheduleId: string) => void;
}) {
  return (
    <section className={styles.schedulesPanel} aria-labelledby="scout-schedules">
      <header className={styles.schedulesHeading}>
        <div><h2 id="scout-schedules">Scheduled Scout jobs</h2><p>Persisted status from the standalone Scheduling API.</p></div>
        <span>{schedules.length}</span>
      </header>
      {isPending && schedules.length === 0 ? (
        <p className={styles.scheduleListMessage} role="status">Loading scheduled jobs…</p>
      ) : error ? (
        <InlineError message={getScoutScheduleErrorMessage(error)} />
      ) : schedules.length === 0 ? (
        <p className={styles.scheduleListMessage}>No scheduled Scout jobs have been persisted yet.</p>
      ) : (
        <div className={styles.scheduleList}>
          {schedules.map((schedule) => (
            <ScheduledJobCard key={schedule.schedule_id} schedule={schedule}
              cancelling={cancellingScheduleId === schedule.schedule_id} onCancel={onCancel} />
          ))}
        </div>
      )}
    </section>
  );
}

function ScheduledJobCard({ schedule, cancelling, onCancel }: {
  schedule: ScoutScheduleRecord; cancelling: boolean; onCancel: (scheduleId: string) => void;
}) {
  return (
    <article className={styles.scheduleCard} data-status={schedule.status}>
      <header className={styles.scheduleCardHeader}>
        <div><span className={styles.statusBadge}>{formatScheduleStatus(schedule.status)}</span>
          <span className={styles.recurrenceBadge}>{capitalize(schedule.recurrence)}</span>
          <strong>{formatPersistedScheduleRule(schedule)}</strong></div>
        {schedule.status === "pending" && (
          <button className={styles.cancelButton} type="button" disabled={cancelling}
            onClick={() => onCancel(schedule.schedule_id)}>
            {cancelling ? <LoaderCircle className={styles.spinner} size={14} aria-hidden /> : <X size={14} aria-hidden />}
            {cancelling ? "Cancelling…" : "Cancel"}
          </button>
        )}
      </header>
      <div className={styles.scheduleRequest}>
        <div><span>Topic</span><p>{schedule.topic}</p></div>
        {schedule.keywords.length > 0 && <div><span>Keywords</span><p>{schedule.keywords.join(", ")}</p></div>}
        {schedule.additional_instructions && (
          <div><span>Instructions</span><p>{schedule.additional_instructions}</p></div>
        )}
      </div>
      {schedule.status === "pending" && <p className={styles.honestStatus}>
        {schedule.recurrence === "once" ? "Waiting for the scheduled time." :
          `Active. Next run: ${formatScheduledWallTime(schedule.run_at)}.`}
      </p>}
      {schedule.status === "running" && <p className={styles.honestStatus}>Scout is running.</p>}
      {schedule.error_message && <p className={styles.scheduleError}>{sanitizeSchedulingError(schedule.error_message)}</p>}
      {schedule.scout_run && (
        <ScheduledScoutResult run={schedule.scout_run} scheduleStatus={schedule.status}
        />
      )}
      <small className={styles.scheduleId}>Schedule ID: {schedule.schedule_id}</small>
    </article>
  );
}

function ScheduledScoutResult({ run, scheduleStatus }: {
  run: ScheduledScoutRun; scheduleStatus: ScoutScheduleStatus;
}) {
  return (
    <div className={styles.scheduledResult}>
      <ScoutRunMetadata run={run} statusLabel={
        scheduleStatus === "pending"
          ? `Latest run ${run.status === "success" ? "succeeded" : "failed"}`
          : formatScheduleStatus(scheduleStatus)
      } />
      {run.status === "success" && (
        <>
          <ul className={styles.scheduledSources} aria-label="Scheduled sources">
            {run.sources.map((source) => <li key={source}><a href={source} target="_blank" rel="noreferrer">
              {source}<ExternalLink size={13} aria-hidden /></a></li>)}
          </ul>
          <details className={styles.scheduledReport}><summary>View scheduled report</summary>
            <MarkdownReport report={run.report} /></details>
        </>
      )}
    </div>
  );
}

function ScoutRunMetadata({ run, statusLabel }: {
  run: ScoutRunResponse | ScheduledScoutRun; statusLabel: string;
}) {
  const successfulRun = run.status === "success" ? run : null;
  return (
    <dl className={styles.metadataList}>
      <div><dt>Status</dt><dd>{statusLabel}</dd></div>
      <div><dt>Duration</dt><dd>{formatCompletedDuration(run.duration_seconds)}</dd></div>
      <div><dt>Completed</dt><dd>{formatScoutCompletedAt(run.completed_at)}</dd></div>
      <div><dt>Sources</dt><dd>{run.source_count}</dd></div>
      <div><dt>Run ID</dt><dd><code>{run.run_id}</code></dd></div>
      {successfulRun && <div><dt>Report artifact</dt><dd><code>{successfulRun.report_artifact}</code></dd></div>}
      <div><dt>Execution log</dt><dd><code>{run.log_artifact}</code></dd></div>
    </dl>
  );
}

function MarkdownReport({ report }: { report: string }) {
  return (
    <div className={styles.markdown}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
        a: ({ children, ...props }) => <a {...props} target="_blank" rel="noreferrer">{children}</a>
      }}>{report}</ReactMarkdown>
    </div>
  );
}

function SourcesList({ sources, headingId }: { sources: string[]; headingId: string }) {
  return (
    <section className={styles.sourcesSection} aria-labelledby={headingId}>
      <header className={styles.sectionHeading}><h2 id={headingId}>Sources</h2><span>{sources.length}</span></header>
      <ul className={styles.sourceList}>{sources.map((source) => <li key={source}>
        <a href={source} target="_blank" rel="noreferrer"><span>{source}</span><ExternalLink size={14} aria-hidden /></a>
      </li>)}</ul>
    </section>
  );
}

function ScoutFailureDetails({ run }: { run: ScoutRunFailure }) {
  return (
    <section className={styles.failureDetails} aria-label="Latest failed attempt">
      <strong>Latest attempt failed</strong>
      <dl className={styles.failureMetadata}>
        <div><dt>Duration</dt><dd>{formatCompletedDuration(run.duration_seconds)}</dd></div>
        <div><dt>Completed</dt><dd>{formatScoutCompletedAt(run.completed_at)}</dd></div>
        <div><dt>Sources</dt><dd>{run.source_count}</dd></div>
        <div><dt>Run ID</dt><dd><code>{run.run_id}</code></dd></div>
        <div><dt>Execution log</dt><dd><code>{run.log_artifact}</code></dd></div>
      </dl>
    </section>
  );
}

export function parseScoutKeywords(value: string) {
  const keywords: string[] = [];
  const seen = new Set<string>();
  for (const part of value.split(/[,\n]/)) {
    const keyword = part.trim();
    const key = keyword.toLocaleLowerCase();
    if (keyword && !seen.has(key)) { seen.add(key); keywords.push(keyword); }
  }
  return keywords;
}

export function normalizeAdditionalInstructions(value: string) {
  return value.trim();
}

export function validateScoutForm(
  topic: string,
  keywordText: string,
  additionalInstructions = ""
) {
  const normalizedTopic = topic.trim();
  if (normalizedTopic.length < 3 || normalizedTopic.length > 500)
    return "Enter a topic containing 3 to 500 characters.";
  const keywords = parseScoutKeywords(keywordText);
  if (keywords.length > 10) return "Enter no more than 10 keywords.";
  if (keywords.some((keyword) => keyword.length > 100))
    return "Each keyword must contain no more than 100 characters.";
  if (normalizeAdditionalInstructions(additionalInstructions).length > 2_000)
    return "Additional research instructions must contain no more than 2,000 characters.";
  return null;
}

export function buildScoutScheduleRunAt(date: string, time: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !/^\d{2}:\d{2}$/.test(time)) return null;
  const [year, month, day] = date.split("-").map(Number);
  const [hour, minute] = time.split(":").map(Number);
  const calendar = new Date(Date.UTC(year, month - 1, day, hour, minute));
  if (
    calendar.getUTCFullYear() !== year || calendar.getUTCMonth() !== month - 1 ||
    calendar.getUTCDate() !== day || calendar.getUTCHours() !== hour ||
    calendar.getUTCMinutes() !== minute
  ) return null;
  return `${date}T${time}:00`;
}

export function buildScoutScheduleTime(time: string) {
  if (!/^\d{2}:\d{2}$/.test(time)) return null;
  const [hour, minute] = time.split(":").map(Number);
  if (hour > 23 || minute > 59) return null;
  return `${time}:00`;
}

const KST_OFFSET_MILLISECONDS = 9 * 60 * 60 * 1_000;
const SCOUT_WEEKDAY_NUMBERS: Record<ScoutScheduleDayOfWeek, number> = {
  sunday: 0,
  monday: 1,
  tuesday: 2,
  wednesday: 3,
  thursday: 4,
  friday: 5,
  saturday: 6
};
const SHORT_MONTH_NAMES = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
] as const;

export function calculateNextScoutRecurringRun(
  recurrence: ScoutScheduleRecurrence,
  time: string,
  dayOfWeek: ScoutScheduleDayOfWeek,
  dayOfMonth: string,
  now = Date.now()
) {
  if (recurrence === "once" || !buildScoutScheduleTime(time)) return null;
  const [hour, minute] = time.split(":").map(Number);
  const seoulNow = new Date(now + KST_OFFSET_MILLISECONDS);
  const year = seoulNow.getUTCFullYear();
  const month = seoulNow.getUTCMonth();
  const day = seoulNow.getUTCDate();
  const toInstant = (candidateYear: number, candidateMonth: number, candidateDay: number) =>
    Date.UTC(candidateYear, candidateMonth, candidateDay, hour, minute) -
    KST_OFFSET_MILLISECONDS;

  if (recurrence === "daily") {
    const today = toInstant(year, month, day);
    return today > now ? today : toInstant(year, month, day + 1);
  }

  if (recurrence === "weekly") {
    const selectedWeekday = SCOUT_WEEKDAY_NUMBERS[dayOfWeek];
    const daysUntilSelected =
      (selectedWeekday - seoulNow.getUTCDay() + 7) % 7;
    const thisOccurrence = toInstant(year, month, day + daysUntilSelected);
    return thisOccurrence > now
      ? thisOccurrence
      : toInstant(year, month, day + daysUntilSelected + 7);
  }

  const selectedDay = Number(dayOfMonth);
  if (!Number.isInteger(selectedDay) || selectedDay < 1 || selectedDay > 31) {
    return null;
  }
  for (let monthOffset = 0; monthOffset < 24; monthOffset += 1) {
    const monthStart = new Date(Date.UTC(year, month + monthOffset, 1));
    const candidateYear = monthStart.getUTCFullYear();
    const candidateMonth = monthStart.getUTCMonth();
    const candidateCalendar = new Date(
      Date.UTC(candidateYear, candidateMonth, selectedDay)
    );
    if (candidateCalendar.getUTCMonth() !== candidateMonth) continue;
    const candidate = toInstant(candidateYear, candidateMonth, selectedDay);
    if (candidate > now) return candidate;
  }
  return null;
}

export function formatScoutNextRun(nextRun: number) {
  const seoulDate = new Date(nextRun + KST_OFFSET_MILLISECONDS);
  const hour = seoulDate.getUTCHours();
  const displayHour = hour % 12 || 12;
  const minute = String(seoulDate.getUTCMinutes()).padStart(2, "0");
  return `Next run: ${SHORT_MONTH_NAMES[seoulDate.getUTCMonth()]} ${seoulDate.getUTCDate()}, ${seoulDate.getUTCFullYear()} at ${displayHour}:${minute} ${hour < 12 ? "AM" : "PM"} KST`;
}

export function formatScoutRecurrenceDescription(
  recurrence: ScoutScheduleRecurrence,
  dayOfWeek: ScoutScheduleDayOfWeek,
  dayOfMonth: string
) {
  if (recurrence === "weekly") return `Repeats every ${capitalize(dayOfWeek)}`;
  if (recurrence === "monthly")
    return `Repeats on day ${Number(dayOfMonth)} of every month`;
  return "Repeats daily";
}

export function validateScoutScheduleForm(
  topic: string,
  keywordText: string,
  additionalInstructions: string,
  recurrence: ScoutScheduleRecurrence,
  date: string,
  time: string,
  dayOfWeek: ScoutScheduleDayOfWeek,
  dayOfMonth: string,
  now = Date.now()
): { error: string | null; runAt: string | null } {
  const scoutError = validateScoutForm(topic, keywordText, additionalInstructions);
  if (scoutError) return { error: scoutError, runAt: null };
  if (!time) return { error: "Choose a schedule time.", runAt: null };
  if (!buildScoutScheduleTime(time))
    return { error: "Enter a valid schedule time.", runAt: null };
  if (recurrence === "daily") return { error: null, runAt: null };
  if (recurrence === "weekly") {
    return SCOUT_SCHEDULE_DAYS.includes(dayOfWeek)
      ? { error: null, runAt: null }
      : { error: "Choose a day of week.", runAt: null };
  }
  if (recurrence === "monthly") {
    const parsedDay = Number(dayOfMonth);
    return Number.isInteger(parsedDay) && parsedDay >= 1 && parsedDay <= 31
      ? { error: null, runAt: null }
      : { error: "Choose a day of month from 1 to 31.", runAt: null };
  }
  if (!date) return { error: "Choose a schedule date.", runAt: null };
  const runAt = buildScoutScheduleRunAt(date, time);
  if (!runAt) return { error: "Enter a valid schedule date and time.", runAt: null };
  const seoulInstant = Date.parse(`${runAt}+09:00`);
  if (!Number.isFinite(seoulInstant) || seoulInstant <= now)
    return { error: "Choose a future date and time in Asia/Seoul.", runAt: null };
  return { error: null, runAt };
}

export function buildScoutScheduleRequest(
  topic: string,
  keywordText: string,
  additionalInstructions: string,
  recurrence: ScoutScheduleRecurrence,
  date: string,
  time: string,
  dayOfWeek: ScoutScheduleDayOfWeek,
  dayOfMonth: string,
  now = Date.now()
) {
  const validation = validateScoutScheduleForm(
    topic,
    keywordText,
    additionalInstructions,
    recurrence,
    date,
    time,
    dayOfWeek,
    dayOfMonth,
    now
  );
  const scheduleTime = buildScoutScheduleTime(time);
  if (validation.error || !scheduleTime) {
    return { error: validation.error, request: null };
  }
  const normalizedInstructions =
    normalizeAdditionalInstructions(additionalInstructions);
  const common = {
    topic: topic.trim(),
    keywords: parseScoutKeywords(keywordText),
    ...(normalizedInstructions
      ? { additional_instructions: normalizedInstructions }
      : {}),
    recurrence,
    timezone: SCOUT_SCHEDULE_TIMEZONE
  };
  if (recurrence === "once") {
    if (!validation.runAt) {
      return { error: "Enter a valid schedule date and time.", request: null };
    }
    return {
      error: null,
      request: { ...common, recurrence, run_at: validation.runAt }
    } as const;
  }
  if (recurrence === "weekly") {
    return {
      error: null,
      request: {
        ...common,
        recurrence,
        schedule_time: scheduleTime,
        day_of_week: dayOfWeek
      }
    } as const;
  }
  if (recurrence === "monthly") {
    return {
      error: null,
      request: {
        ...common,
        recurrence,
        schedule_time: scheduleTime,
        day_of_month: Number(dayOfMonth)
      }
    } as const;
  }
  return {
    error: null,
    request: { ...common, recurrence, schedule_time: scheduleTime }
  } as const;
}

export function formatScoutScheduleRule(request: ScoutScheduleCreateRequest) {
  if (request.recurrence === "once" && request.run_at) {
    return `once for ${formatScheduledWallTime(request.run_at)}`;
  }
  const time = formatScheduleTime(request.schedule_time);
  if (request.recurrence === "weekly" && request.day_of_week) {
    return `weekly on ${capitalize(request.day_of_week)} at ${time}`;
  }
  if (request.recurrence === "monthly" && request.day_of_month) {
    return `monthly on day ${request.day_of_month} at ${time}`;
  }
  return `daily at ${time}`;
}

export function formatPersistedScheduleRule(schedule: ScoutScheduleRecord) {
  if (schedule.recurrence === "once") {
    return formatScheduledWallTime(schedule.run_at);
  }
  return formatScoutScheduleRule({
    topic: schedule.topic,
    keywords: schedule.keywords,
    recurrence: schedule.recurrence,
    schedule_time: schedule.schedule_time ?? undefined,
    day_of_week: schedule.day_of_week ?? undefined,
    day_of_month: schedule.day_of_month ?? undefined,
    timezone: schedule.timezone
  });
}

function formatScheduleTime(value: string | undefined) {
  return `${value?.slice(0, 5) ?? "--:--"} KST`;
}

function capitalize(value: string) {
  return `${value.charAt(0).toUpperCase()}${value.slice(1)}`;
}

export async function createScoutScheduleAndRefresh(
  request: ScoutScheduleCreateRequest,
  create: (value: ScoutScheduleCreateRequest) => Promise<ScoutScheduleRecord>,
  refetch: () => Promise<unknown>
) {
  const created = await create(request);
  await refetch().catch(() => undefined);
  return created;
}

export async function cancelScoutScheduleAndRefresh(
  scheduleId: string,
  cancel: (value: string) => Promise<ScoutScheduleRecord>,
  refetch: () => Promise<unknown>
) {
  try {
    const cancelled = await cancel(scheduleId);
    await refetch().catch(() => undefined);
    return cancelled;
  } catch (error) {
    await refetch().catch(() => undefined);
    throw error;
  }
}

export function getScoutErrorMessage(error: unknown) {
  if (error instanceof ScoutClientError) {
    if (error.status === 503)
      return "Scout is not ready. Confirm that the standalone service and model configuration are available.";
    return error.message;
  }
  if (error instanceof Error) return "The Scout run could not be completed. Please try again.";
  return null;
}

export function getScoutScheduleErrorMessage(error: unknown) {
  if (error instanceof ScoutScheduleClientError) {
    if (error.status === 503)
      return "Scout scheduling is not ready. Confirm that the standalone Scheduling API is available.";
    return error.message;
  }
  return "The Scout scheduling request could not be completed. Please try again.";
}

export function calculateElapsedSeconds(startedAt: number, now: number) {
  return Math.max(0, Math.floor((now - startedAt) / 1_000));
}

export function formatElapsedDuration(seconds: number) { return formatDuration(Math.floor(seconds)); }
export function formatCompletedDuration(seconds: number) { return formatDuration(Math.round(seconds)); }
function formatDuration(seconds: number) {
  const safeSeconds = Math.max(0, seconds);
  return `${String(Math.floor(safeSeconds / 60)).padStart(2, "0")}:${String(safeSeconds % 60).padStart(2, "0")}`;
}

export function formatScoutCompletedAt(value: string) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23"
  }).formatToParts(new Date(value));
  const values = Object.fromEntries(parts.filter((part) => part.type !== "literal").map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day} ${values.hour}:${values.minute}:${values.second} KST`;
}

export function formatScheduledWallTime(runAt: string) {
  return `${runAt.replace("T", " ").replace(/\.\d+$/, "")} KST`;
}

export function formatScheduleStatus(status: ScoutScheduleStatus) {
  const labels: Record<ScoutScheduleStatus, string> = {
    pending: "Pending", running: "Running", succeeded: "Succeeded",
    failed: "Failed", cancelled: "Cancelled", missed: "Missed"
  };
  return labels[status];
}

function sanitizeSchedulingError(value: string) {
  return value.replace(/\s+/g, " ").trim().slice(0, 400);
}

function getScoutFailureRun(error: unknown) {
  return error instanceof ScoutClientError ? error.run : null;
}
