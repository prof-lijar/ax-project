import {
  AlertTriangle,
  ArrowLeft,
  Bot,
  CalendarDays,
  Check,
  ChevronRight,
  CircleStop,
  Clock3,
  Files,
  FlaskConical,
  Layers3,
  Play,
  RefreshCw,
  Sparkles,
  MapPin
} from "lucide-react";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent
} from "react";

import {
  AgentServerError,
  agentServerClient
} from "../../shared/api/agentServerClient";
import { useAgentServerHealth } from "../../shared/api/queries";
import { navigateToSection } from "../../shared/navigation/sections";
import type {
  WardWeeklyReport,
  WeeklyReportBatchResult,
  WeeklyReportProgressEvent,
  WeeklyReportRequest
} from "../../shared/types/weeklyReport";
import { ChatMarkdown } from "../chat/ChatMarkdown";
import { BulkWeeklyReportPanel } from "./BulkWeeklyReportPanel";
import styles from "./TestAgentPage.module.css";

const TIMEZONES = ["Asia/Seoul", "UTC", "America/New_York", "Europe/London"];
const DEFAULT_REPORT_LIMIT = 3;
const MIN_REPORT_LIMIT = 1;
const MAX_REPORT_LIMIT = 25;

interface TestAgentPageProps {
  mode?: "test" | "agent";
}

export function TestAgentPage({ mode = "test" }: TestAgentPageProps) {
  const [weekStart, setWeekStart] = useState(getLatestMonday);
  const [timezone, setTimezone] = useState("Asia/Seoul");
  const [reportLimitInput, setReportLimitInput] = useState(
    String(DEFAULT_REPORT_LIMIT)
  );
  const [runMode, setRunMode] = useState<"preview" | "bulk">("preview");
  const [result, setResult] = useState<WeeklyReportBatchResult | null>(null);
  const [selectedWardId, setSelectedWardId] = useState<number | null>(null);
  const [progress, setProgress] = useState<WeeklyReportProgressEvent[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const abortControllerRef = useRef<AbortController | null>(null);
  const healthQuery = useAgentServerHealth();
  const weekStartIsValid = isMonday(weekStart);
  const reportLimit = parseReportLimit(reportLimitInput);
  const reportLimitIsValid = reportLimit !== null;
  const isAgentPage = mode === "agent";

  const selectedReport = useMemo(
    () => selectWeeklyReport(result, selectedWardId),
    [result, selectedWardId]
  );

  useEffect(() => {
    if (!isRunning) {
      return;
    }
    const startedAt = Date.now();
    setElapsedSeconds(0);
    const interval = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(interval);
  }, [isRunning]);

  useEffect(
    () => () => {
      abortControllerRef.current?.abort();
    },
    []
  );

  async function runReporter() {
    const request = buildWeeklyReportRequest(
      weekStart,
      timezone,
      reportLimitInput
    );
    if (!weekStartIsValid || request === null || isRunning) {
      return;
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;
    setIsRunning(true);
    setErrorMessage(null);
    setResult(null);
    setSelectedWardId(null);
    setProgress([]);

    try {
      const batch = await agentServerClient.runWeeklyReport(
        request,
        {
          signal: controller.signal,
          onProgress: (event) => setProgress((current) => [...current, event])
        }
      );
      setResult(batch);
      setSelectedWardId(batch.reports[0]?.ward_id ?? null);
    } catch (error) {
      if (error instanceof AgentServerError && error.code === "cancelled") {
        setErrorMessage("Run cancelled. Adjust the inputs or start it again.");
      } else {
        setErrorMessage(
          error instanceof Error
            ? error.message
            : "The Weekly Reporter could not complete the run."
        );
        void healthQuery.refetch();
      }
    } finally {
      abortControllerRef.current = null;
      setIsRunning(false);
    }
  }

  function backToAgents(event: MouseEvent<HTMLAnchorElement>) {
    if (
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    ) {
      return;
    }
    event.preventDefault();
    navigateToSection("agents");
  }

  return (
    <section className={styles.page}>
      <div className={styles.pageHeading}>
        {isAgentPage && (
          <a className={styles.backLink} href="/agents" onClick={backToAgents}>
            <ArrowLeft size={16} aria-hidden />
            Back to Agents
          </a>
        )}
        <header className={styles.pageHeader}>
          <div className={styles.titleGroup}>
            <span className={styles.titleIcon} aria-hidden>
              {isAgentPage ? <Bot size={22} /> : <FlaskConical size={22} />}
            </span>
            <div>
              <h1>{isAgentPage ? "Weekly Reporter" : "Weekly Reporter test"}</h1>
              <p>
                {runMode === "bulk"
                  ? "Start a durable concurrent run, watch live throughput, and download the verified export."
                  : isAgentPage
                  ? "Choose a batch size, generate live weekly summaries, and review one subscriber at a time."
                  : "Run a reporting week and inspect every generated ward report."}
              </p>
            </div>
          </div>
          <ServerStatus
            isPending={healthQuery.isPending}
            isError={healthQuery.isError}
            isFetching={healthQuery.isFetching}
            onRetry={() => void healthQuery.refetch()}
          />
        </header>
      </div>

      <div className={styles.modeSwitch} aria-label="Weekly Reporter run mode">
        <button
          className={runMode === "preview" ? styles.modeActive : undefined}
          type="button"
          onClick={() => setRunMode("preview")}
        >
          <FlaskConical size={15} />
          Quick preview
          <small>1–25 reports</small>
        </button>
        <button
          className={runMode === "bulk" ? styles.modeActive : undefined}
          type="button"
          onClick={() => setRunMode("bulk")}
        >
          <Layers3 size={15} />
          Bulk generation
          <small>up to 10,000</small>
        </button>
      </div>

      {runMode === "bulk" ? (
        <BulkWeeklyReportPanel />
      ) : (
      <div className={styles.workbench}>
        <aside className={styles.runPanel} aria-label="Run configuration">
          <div className={styles.agentIdentity}>
            <span aria-hidden><Bot size={20} /></span>
            <div>
              <strong>Weekly Reporter</strong>
              <code>ansimk_weekly_reporter</code>
            </div>
          </div>

          <form
            className={styles.runForm}
            onSubmit={(event) => {
              event.preventDefault();
              void runReporter();
            }}
          >
            <label>
              <span>Week starts</span>
              <div className={styles.fieldControl}>
                <CalendarDays size={16} aria-hidden />
                <input
                  type="date"
                  value={weekStart}
                  onChange={(event) => setWeekStart(event.target.value)}
                  aria-describedby="week-start-help"
                  disabled={isRunning}
                />
              </div>
              <small
                id="week-start-help"
                className={weekStartIsValid ? undefined : styles.fieldError}
              >
                {weekStartIsValid
                  ? `${formatDate(weekStart)} — ${formatDate(addDays(weekStart, 6))}`
                  : "Choose a Monday to match the agent contract."}
              </small>
            </label>

            <label>
              <span>Timezone</span>
              <select
                value={timezone}
                onChange={(event) => setTimezone(event.target.value)}
                disabled={isRunning}
              >
                {TIMEZONES.map((item) => (
                  <option key={item} value={item}>{item}</option>
                ))}
              </select>
              <small>Applied to the Monday-to-Monday activity window.</small>
            </label>

            <label>
              <span>Reports to generate</span>
              <div className={styles.fieldControl}>
                <Files size={16} aria-hidden />
                <input
                  type="number"
                  min={MIN_REPORT_LIMIT}
                  max={MAX_REPORT_LIMIT}
                  step="1"
                  inputMode="numeric"
                  value={reportLimitInput}
                  onChange={(event) => setReportLimitInput(event.target.value)}
                  aria-describedby="report-limit-help"
                  aria-invalid={!reportLimitIsValid}
                  disabled={isRunning}
                />
              </div>
              <small
                id="report-limit-help"
                className={reportLimitIsValid ? undefined : styles.fieldError}
              >
                {reportLimitIsValid
                  ? "Choose 1–25 eligible subscribers for this batch."
                  : "Enter a whole number from 1 to 25."}
              </small>
            </label>

            {isRunning ? (
              <button
                className={styles.stopButton}
                type="button"
                onClick={() => abortControllerRef.current?.abort()}
              >
                <CircleStop size={17} />
                Cancel run
              </button>
            ) : (
              <button
                className={styles.runButton}
                type="submit"
                disabled={
                  !weekStartIsValid || !reportLimitIsValid || healthQuery.isError
                }
              >
                <Play size={17} fill="currentColor" />
                {reportLimit === null
                  ? "Choose report count"
                  : `Generate ${reportCountLabel(reportLimit)}`}
              </button>
            )}
          </form>

          <RunProgress
            progress={progress}
            isRunning={isRunning}
            elapsedSeconds={elapsedSeconds}
            hasResult={result !== null}
            requestedCount={reportLimit ?? DEFAULT_REPORT_LIMIT}
          />
        </aside>

        <main className={styles.resultPanel}>
          {errorMessage ? (
            <ErrorState message={errorMessage} onRetry={() => void runReporter()} />
          ) : isRunning ? (
            <RunningState
              progress={progress}
              elapsedSeconds={elapsedSeconds}
              requestedCount={reportLimit ?? DEFAULT_REPORT_LIMIT}
            />
          ) : result && selectedReport ? (
            <ReportResult
              result={result}
              selectedReport={selectedReport}
              onSelectReport={setSelectedWardId}
            />
          ) : result ? (
            <NoReportsState result={result} />
          ) : (
            <EmptyState
              weekStart={weekStart}
              isAgentPage={isAgentPage}
              requestedCount={reportLimit ?? DEFAULT_REPORT_LIMIT}
            />
          )}
        </main>
      </div>
      )}
    </section>
  );
}

export function selectWeeklyReport(
  result: WeeklyReportBatchResult | null,
  selectedWardId: number | null
) {
  return (
    result?.reports.find((report) => report.ward_id === selectedWardId) ??
    result?.reports[0] ??
    null
  );
}

export function parseReportLimit(value: string): number | null {
  if (!/^\d+$/.test(value)) {
    return null;
  }
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) &&
    parsed >= MIN_REPORT_LIMIT &&
    parsed <= MAX_REPORT_LIMIT
    ? parsed
    : null;
}

export function buildWeeklyReportRequest(
  weekStart: string,
  timezone: string,
  reportLimitInput: string
): WeeklyReportRequest | null {
  const limit = parseReportLimit(reportLimitInput);
  return limit === null
    ? null
    : { week_start: weekStart, timezone, limit };
}

function ServerStatus({
  isPending,
  isError,
  isFetching,
  onRetry
}: {
  isPending: boolean;
  isError: boolean;
  isFetching: boolean;
  onRetry: () => void;
}) {
  return (
    <div className={styles.serverStatus} aria-live="polite">
      <span
        className={
          isPending
            ? styles.statusChecking
            : isError
              ? styles.statusOffline
              : styles.statusOnline
        }
        aria-hidden
      />
      <span>{isPending ? "Checking server" : isError ? "Server offline" : "Server ready"}</span>
      {isError && (
        <button type="button" onClick={onRetry} disabled={isFetching}>
          <RefreshCw size={13} /> Retry
        </button>
      )}
    </div>
  );
}

function RunProgress({
  progress,
  isRunning,
  elapsedSeconds,
  hasResult,
  requestedCount
}: {
  progress: WeeklyReportProgressEvent[];
  isRunning: boolean;
  elapsedSeconds: number;
  hasResult: boolean;
  requestedCount: number;
}) {
  if (progress.length === 0 && !isRunning && !hasResult) {
    return (
      <div className={styles.contractNote}>
        <strong>Live data</strong>
        <p>
          The graph reads approved weekly metadata through the private source
          service. This run will request up to {requestedCount} eligible
          subscribers.
        </p>
      </div>
    );
  }

  const loaded = progress.find((event) => event.event === "risk_data_loaded");
  const wardCount =
    loaded?.event === "risk_data_loaded" ? loaded.ward_count : requestedCount;
  const readyCount = progress.filter(
    (event) => event.event === "ward_report_ready"
  ).length;
  const completed = progress.some((event) => event.event === "batch_completed");

  return (
    <div className={styles.progressBlock} aria-live="polite">
      <div className={styles.progressHeading}>
        <strong>{completed ? "Run complete" : "Run progress"}</strong>
        <span><Clock3 size={13} /> {elapsedSeconds}s</span>
      </div>
      <ProgressRow
        complete={progress.length > 0}
        active={isRunning && progress.length === 0}
        label="Start batch"
      />
      <ProgressRow
        complete={Boolean(loaded)}
        active={isRunning && progress.length > 0 && !loaded}
        label="Load weekly summaries"
      />
      <ProgressRow
        complete={readyCount === wardCount}
        active={isRunning && Boolean(loaded) && readyCount < wardCount}
        label={`Write reports · ${readyCount}/${wardCount}`}
      />
      <ProgressRow
        complete={completed}
        active={isRunning && readyCount === wardCount}
        label="Aggregate results"
      />
    </div>
  );
}

function ProgressRow({
  complete,
  active,
  label
}: {
  complete: boolean;
  active: boolean;
  label: string;
}) {
  return (
    <div className={styles.progressRow}>
      <span className={complete ? styles.progressDone : active ? styles.progressActive : styles.progressIdle}>
        {complete ? <Check size={12} /> : null}
      </span>
      <span>{label}</span>
    </div>
  );
}

function RunningState({
  progress,
  elapsedSeconds,
  requestedCount
}: {
  progress: WeeklyReportProgressEvent[];
  elapsedSeconds: number;
  requestedCount: number;
}) {
  const loaded = progress.find((event) => event.event === "risk_data_loaded");
  const total =
    loaded?.event === "risk_data_loaded" ? loaded.ward_count : requestedCount;
  const progressTotal = Math.max(total, 1);
  const ready = progress.filter(
    (event) => event.event === "ward_report_ready"
  ).length;
  const heading = !loaded
    ? "Loading weekly summaries"
    : total === 0
      ? "No eligible weekly summaries found"
      : ready >= total
        ? "Aggregating completed reports"
        : `Writing reports · ${ready}/${total} complete`;
  return (
    <div className={styles.centerState} aria-live="polite">
      <span className={styles.runningIcon}><Sparkles size={26} /></span>
      <h2>{heading}</h2>
      <p>The agent is comparing verified weekly activity, environment, risk, and dispatch metadata.</p>
      <div className={styles.pulseTrack}><span style={{ width: `${Math.max(12, ready * (90 / progressTotal))}%` }} /></div>
      <small>{elapsedSeconds}s elapsed · reports appear when the batch is complete</small>
    </div>
  );
}

function EmptyState({
  weekStart,
  isAgentPage,
  requestedCount
}: {
  weekStart: string;
  isAgentPage: boolean;
  requestedCount: number;
}) {
  return (
    <div className={styles.centerState}>
      <span className={styles.emptyIcon}><CalendarDays size={28} /></span>
      <h2>{isAgentPage ? "Ready for a live run" : "Ready for a test run"}</h2>
      <p>Run the week of {weekStart ? formatDate(weekStart) : "your choice"} to review report quality and metrics.</p>
      <div className={styles.expectationList}>
        <span><Check size={14} /> Up to {reportCountLabel(requestedCount)}</span>
        <span><Check size={14} /> Current and prior week comparison</span>
        <span><Check size={14} /> Verified narrative mode</span>
      </div>
    </div>
  );
}

function NoReportsState({ result }: { result: WeeklyReportBatchResult }) {
  return (
    <div className={styles.centerState} role="status">
      <span className={styles.emptyIcon}><CalendarDays size={28} /></span>
      <h2>No eligible reports for this week</h2>
      <p>
        The source returned no subscriber summaries for {formatDate(result.week_start)}.
        Choose another completed Monday and try again.
      </p>
      {result.warnings.length > 0 && (
        <small>{result.warnings.join(" · ")}</small>
      )}
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className={styles.centerState} role="alert">
      <span className={styles.errorIcon}><AlertTriangle size={26} /></span>
      <h2>Run did not finish</h2>
      <p>{message}</p>
      <button className={styles.retryButton} type="button" onClick={onRetry}>
        <RefreshCw size={16} /> Try again
      </button>
    </div>
  );
}

export function ReportResult({
  result,
  selectedReport,
  onSelectReport
}: {
  result: WeeklyReportBatchResult;
  selectedReport: WardWeeklyReport;
  onSelectReport: (wardId: number) => void;
}) {
  const fallbackCount = result.reports.filter(
    (report) => report.generation_mode === "template_fallback"
  ).length;
  return (
    <div className={styles.reportWorkspace}>
      <header className={styles.resultHeader}>
        <div>
          <span className={styles.successLabel}><Check size={13} /> Completed</span>
          <h2>{formatDate(result.week_start)} weekly reports</h2>
          <p>
            {result.reports.length} subscriber reports · {result.timezone} · {fallbackCount ? `${fallbackCount} deterministic fallback` : "All model-generated"}
            {result.next_cursor ? " · More subscribers available" : ""}
          </p>
        </div>
      </header>

      {result.warnings.length > 0 && (
        <div className={styles.warningBanner} role="note">
          <AlertTriangle size={16} />
          <div><strong>{fallbackCount ? "Generation notes" : "Data notes"}</strong><span>{result.warnings.join(" · ")}</span></div>
        </div>
      )}

      <div className={styles.reportBody}>
        <nav className={styles.peopleList} aria-label="Generated subscriber reports">
          <span className={styles.peopleLabel}>Subscribers</span>
          {result.reports.map((report) => {
            const selected = report.ward_id === selectedReport.ward_id;
            return (
              <button
                key={report.ward_id}
                className={selected ? styles.personActive : styles.person}
                type="button"
                onClick={() => onSelectReport(report.ward_id)}
                aria-current={selected ? "true" : undefined}
              >
                <span className={styles.personAvatar}><MapPin size={16} /></span>
                <span><strong>{report.display_name}</strong><small>{report.generation_mode === "llm" ? "Model narrative" : "Template fallback"}</small></span>
                <ChevronRight size={15} />
              </button>
            );
          })}
        </nav>

        <article className={styles.reportDocument}>
          <header className={styles.documentHeader}>
            <div>
              <span>Report preview</span>
              <h3>{selectedReport.display_name}</h3>
            </div>
            <span className={selectedReport.generation_mode === "llm" ? styles.modeLlm : styles.modeFallback}>
              {selectedReport.generation_mode === "llm" ? "LLM" : "Fallback"}
            </span>
          </header>

          <MetricStrip report={selectedReport} />
          <div className={styles.markdownDocument} lang="ko">
            <ChatMarkdown content={selectedReport.markdown} />
          </div>

          <footer className={styles.reportProvenance}>
            <span>Source coverage: {selectedReport.metrics.current.covered_days}/7 days</span>
            <span>Prompt: {selectedReport.generation.prompt_version}</span>
            <span>{selectedReport.generation.validation_status === "passed" ? "Narrative validated" : "Deterministic fallback"}</span>
          </footer>
        </article>
      </div>
    </div>
  );
}

function MetricStrip({ report }: { report: WardWeeklyReport }) {
  const { current, delta } = report.metrics;
  const metrics = [
    {
      label: "Data coverage",
      value: `${current.covered_days}/7 days`,
      delta: comparison(delta.covered_days),
      tone: "neutral"
    },
    {
      label: "Danger days",
      value: `${current.danger_days} days`,
      delta: comparison(delta.danger_days),
      tone: delta.danger_days > 0 ? "negative" : delta.danger_days < 0 ? "positive" : "neutral"
    },
    {
      label: "Movement average",
      value: formatAverage(current.movement_count_avg, "/day"),
      delta: comparison(delta.movement_count_avg),
      tone: "neutral"
    },
    {
      label: "Open dispatches",
      value: String(current.unresolved_dispatch_count),
      delta: comparison(delta.unresolved_dispatch_count),
      tone: delta.unresolved_dispatch_count > 0 ? "negative" : delta.unresolved_dispatch_count < 0 ? "positive" : "neutral"
    }
  ];
  return (
    <dl className={styles.metricStrip}>
      {metrics.map((metric) => (
        <div key={metric.label}>
          <dt>{metric.label}</dt>
          <dd>{metric.value}</dd>
          <small className={metric.tone === "positive" ? styles.deltaPositive : metric.tone === "negative" ? styles.deltaNegative : styles.deltaNeutral}>{metric.delta}</small>
        </div>
      ))}
    </dl>
  );
}

function getLatestMonday() {
  const now = new Date();
  const date = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const daysSinceMonday = (date.getDay() + 6) % 7;
  date.setDate(date.getDate() - daysSinceMonday - 7);
  return toDateInputValue(date);
}

function isMonday(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return false;
  }
  return new Date(`${value}T00:00:00Z`).getUTCDay() === 1;
}

function addDays(value: string, days: number) {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

function toDateInputValue(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function comparison(value: number | null) {
  if (value === null) {
    return "No prior comparison";
  }
  if (value === 0) {
    return "No change vs prior";
  }
  return `${value > 0 ? "+" : ""}${formatNumber(value)} vs prior`;
}

function formatAverage(value: number | null, suffix: string) {
  return value === null ? "No data" : `${formatNumber(value)}${suffix}`;
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("en", { maximumFractionDigits: 1 }).format(value);
}

function reportCountLabel(count: number) {
  return `${count} ${count === 1 ? "report" : "reports"}`;
}
