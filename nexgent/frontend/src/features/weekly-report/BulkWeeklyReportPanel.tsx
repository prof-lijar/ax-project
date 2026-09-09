import {
  AlertTriangle,
  CalendarDays,
  CheckCircle2,
  CircleStop,
  Clock3,
  Download,
  Files,
  Gauge,
  LoaderCircle,
  Play,
  RefreshCw,
  ServerCog,
  Users
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import {
  isBulkJobTerminal,
  weeklyReportBulkClient,
  WeeklyReportBulkClientError,
  type WeeklyReportBulkJobStatus,
  type WeeklyReportBulkRuntime
} from "../../shared/api/weeklyReportBulkClient";
import { pollWeeklyReportJob } from "./pollWeeklyReportJob";
import styles from "./BulkWeeklyReportPanel.module.css";

const TIMEZONES = ["Asia/Seoul", "UTC", "America/New_York", "Europe/London"];
const DEFAULT_BULK_REPORT_LIMIT = 10_000;

export function BulkWeeklyReportPanel() {
  const [weekStart, setWeekStart] = useState(getLatestMonday);
  const [timezone, setTimezone] = useState("Asia/Seoul");
  const [reportLimitInput, setReportLimitInput] = useState(
    String(DEFAULT_BULK_REPORT_LIMIT)
  );
  const [wardIdsInput, setWardIdsInput] = useState("");
  const [approved, setApproved] = useState(false);
  const [runtime, setRuntime] = useState<WeeklyReportBulkRuntime | null>(null);
  const [jobs, setJobs] = useState<WeeklyReportBulkJobStatus[]>([]);
  const [selectedJob, setSelectedJob] =
    useState<WeeklyReportBulkJobStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());
  const wardIds = parseWardIds(wardIdsInput);
  const reportLimit = wardIds === null ? null : wardIds?.length ?? parseBulkReportLimit(reportLimitInput);
  const weekStartIsValid = isMonday(weekStart);
  const activeJobId =
    selectedJob && !isBulkJobTerminal(selectedJob.status)
      ? selectedJob.job_id
      : null;
  const activeJobIdRef = useRef<string | null>(activeJobId);
  activeJobIdRef.current = activeJobId;

  useEffect(() => {
    const controller = new AbortController();
    void loadDashboard(controller.signal);
    return () => controller.abort();

    async function loadDashboard(signal: AbortSignal) {
      setIsLoading(true);
      try {
        const [runtimeResult, recentJobs] = await Promise.all([
          weeklyReportBulkClient.runtime({ signal }),
          weeklyReportBulkClient.listJobs(20, { signal })
        ]);
        setRuntime(runtimeResult);
        setJobs(recentJobs);
        setSelectedJob((current) =>
          current
            ? recentJobs.find((job) => job.job_id === current.job_id) ?? current
            : recentJobs[0] ?? null
        );
        setErrorMessage(null);
      } catch (error) {
        setErrorMessage(errorText(error));
      } finally {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!activeJobId) return;
    setNow(Date.now());
    const interval = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(interval);
  }, [activeJobId]);

  useEffect(() => {
    const stopActiveJob = () => {
      const jobId = activeJobIdRef.current;
      if (jobId) {
        void weeklyReportBulkClient.cancel(jobId, { keepalive: true });
      }
    };
    window.addEventListener("pagehide", stopActiveJob);
    return () => {
      window.removeEventListener("pagehide", stopActiveJob);
      stopActiveJob();
    };
  }, []);

  useEffect(() => {
    if (!activeJobId) return;
    return pollWeeklyReportJob(
      activeJobId,
      (runtime?.status_poll_seconds ?? 2) * 1_000,
      (updated) => {
        setSelectedJob(updated);
        setJobs((current) => upsertJob(current, updated));
        setErrorMessage(null);
      },
      (error) => setErrorMessage(errorText(error))
    );
  }, [runtime?.status_poll_seconds, activeJobId]);

  const metrics = useMemo(
    () => calculateBulkProgress(selectedJob, now),
    [selectedJob, now]
  );

  async function submitJob() {
    if (
      reportLimit === null ||
      !weekStartIsValid ||
      !approved ||
      isSubmitting ||
      isLoading ||
      !runtime ||
      activeJobId !== null
    ) {
      return;
    }
    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      const job = await weeklyReportBulkClient.submit({
        week_start: weekStart,
        timezone,
        max_reports: reportLimit,
        ...(wardIds ? { ward_ids: wardIds } : {}),
        idempotency_key: createIdempotencyKey(weekStart)
      });
      setSelectedJob(job);
      setJobs((current) => upsertJob(current, job));
      setApproved(false);
    } catch (error) {
      setErrorMessage(errorText(error));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function cancelJob() {
    if (!selectedJob || isBulkJobTerminal(selectedJob.status) || isCancelling) {
      return;
    }
    setIsCancelling(true);
    setErrorMessage(null);
    try {
      const job = await weeklyReportBulkClient.cancel(selectedJob.job_id);
      setSelectedJob(job);
      setJobs((current) => upsertJob(current, job));
    } catch (error) {
      setErrorMessage(errorText(error));
    } finally {
      setIsCancelling(false);
    }
  }

  async function refreshDashboard() {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      if (activeJobId) {
        await weeklyReportBulkClient.cancel(activeJobId);
      }
      const [runtimeResult, recentJobs] = await Promise.all([
        weeklyReportBulkClient.runtime(),
        weeklyReportBulkClient.listJobs()
      ]);
      setRuntime(runtimeResult);
      setJobs(recentJobs);
      setSelectedJob((current) =>
        current
          ? recentJobs.find((job) => job.job_id === current.job_id) ?? current
          : recentJobs[0] ?? null
      );
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(errorText(error));
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className={styles.workbench}>
      <aside className={styles.runPanel} aria-label="Bulk run configuration">
        <div className={styles.identity}>
          <span aria-hidden><ServerCog size={20} /></span>
          <div>
            <strong>Test report generation</strong>
            <small>ZIP export only · reports are not saved to the database</small>
          </div>
        </div>

        <form
          className={styles.form}
          onSubmit={(event) => {
            event.preventDefault();
            void submitJob();
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
                aria-invalid={!weekStartIsValid}
              />
            </div>
            <small className={weekStartIsValid ? undefined : styles.fieldError}>
              {weekStartIsValid
                ? "Monday-to-Sunday reporting period"
                : "Choose a Monday."}
            </small>
          </label>

          <label>
            <span>Timezone</span>
            <select value={timezone} onChange={(event) => setTimezone(event.target.value)}>
              {TIMEZONES.map((item) => <option key={item}>{item}</option>)}
            </select>
          </label>

          <label>
            <span>Ward IDs (optional)</span>
            <div className={styles.fieldControl}>
              <Users size={16} aria-hidden />
              <input
                type="text"
                placeholder="23, 45, 56"
                value={wardIdsInput}
                onChange={(event) => setWardIdsInput(event.target.value)}
                aria-invalid={wardIds === null}
                aria-describedby="ward-ids-help"
              />
            </div>
            <small id="ward-ids-help" className={wardIds === null ? styles.fieldError : undefined}>
              {wardIds === null
                ? "Enter up to 25 unique positive whole-number IDs, separated by commas."
                : wardIds
                  ? `Only these ${wardIds.length} wards will be requested. ZIP only; no report database save.`
                  : "Leave blank for automatic selection, or enter up to 25 ward IDs."}
            </small>
          </label>

          <label>
            <span>Maximum reports</span>
            <div className={styles.fieldControl}>
              <Files size={16} aria-hidden />
              <input
                type="number"
                min="1"
                max="10000"
                step="1"
                inputMode="numeric"
                disabled={wardIdsInput.trim().length > 0}
                value={wardIds ? String(wardIds.length) : reportLimitInput}
                onChange={(event) => setReportLimitInput(event.target.value)}
                aria-invalid={reportLimit === null}
              />
            </div>
            <small className={reportLimit === null ? styles.fieldError : undefined}>
              {reportLimit === null
                ? "Enter a whole number from 1 to 10,000."
                : wardIds
                  ? "Report count matches the selected ward IDs."
                : reportLimit === 10_000
                  ? "All available reports, up to 10,000 per run."
                  : `${formatNumber(reportLimit)} eligible wards at most.`}
            </small>
          </label>

          <div className={styles.runtimeSummary}>
            <span><Gauge size={14} /> Worker concurrency</span>
            <strong>{runtime?.worker_concurrency ?? "—"}</strong>
            <small>Source pages contain up to 100 wards; workers process staged reports concurrently.</small>
          </div>

          <label className={styles.approval}>
            <input
              type="checkbox"
              checked={approved}
              onChange={(event) => setApproved(event.target.checked)}
            />
            <span>
              I approve this live run. It sends allowlisted care-derived facts
              to the configured private model and may reduce Chat capacity.
            </span>
          </label>

          <button
            className={styles.runButton}
            type="submit"
            disabled={
              isSubmitting ||
              activeJobId !== null ||
              isLoading ||
              runtime === null ||
              reportLimit === null ||
              !weekStartIsValid ||
              !approved
            }
          >
            {isSubmitting || activeJobId ? <LoaderCircle className={styles.spin} size={17} aria-hidden /> : <Play size={17} aria-hidden />}
            {isSubmitting ? "Starting…" : activeJobId ? "Running…" : "Run Agent"}
          </button>
        </form>

        <div className={styles.safetyNote}>
          <AlertTriangle size={15} />
          <p>
            This is a real model-backed load run. Start with 100–1,000 before
            using 10,000, then watch throughput and Chat latency.
          </p>
        </div>
      </aside>

      <main className={styles.dashboard}>
        <header className={styles.dashboardHeader}>
          <div>
            <span className={runtime ? styles.onlineDot : styles.offlineDot} aria-hidden />
            <strong>{runtime ? "Bulk service ready" : "Bulk service unavailable"}</strong>
            <small>
              {runtime
                ? `${runtime.worker_concurrency} concurrent consumers · page size ${runtime.source_page_size}`
                : "Start the bulk API, job database, and worker."}
            </small>
          </div>
          <button type="button" onClick={() => void refreshDashboard()} disabled={isLoading}>
            <RefreshCw className={isLoading ? styles.spin : undefined} size={15} />
            {activeJobId ? "Stop & refresh" : "Refresh"}
          </button>
        </header>

        {errorMessage && (
          <div className={styles.errorBanner} role="alert">
            <AlertTriangle size={16} />
            <span>{errorMessage}</span>
          </div>
        )}

        {selectedJob ? (
          <section className={styles.currentJob} aria-live="polite">
            <div className={styles.jobHeading}>
              <div>
                <RunStatusIndicator job={selectedJob} />
                <h2>{formatNumber(selectedJob.max_reports)}-report run</h2>
                <code>{selectedJob.job_id}</code>
              </div>
              <div className={styles.jobActions}>
                {!isBulkJobTerminal(selectedJob.status) && (
                  <button
                    className={styles.cancelButton}
                    type="button"
                    onClick={() => void cancelJob()}
                    disabled={isCancelling}
                  >
                    <CircleStop size={16} />
                    {isCancelling ? "Cancelling" : "Cancel"}
                  </button>
                )}
                {selectedJob.export && (
                  <a
                    className={styles.downloadButton}
                    href={weeklyReportBulkClient.exportUrl(selectedJob.job_id)}
                    download
                  >
                    <Download size={16} /> Download ZIP
                  </a>
                )}
              </div>
            </div>

            <div className={styles.progressMeta}>
              <span>{metrics.percent}% terminal</span>
              <span>{formatDuration(metrics.elapsedSeconds)} elapsed</span>
            </div>
            <div
              className={styles.progressTrack}
              role="progressbar"
              aria-label="Report generation progress"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={metrics.percent}
            >
              <span style={{ width: `${metrics.percent}%` }} />
            </div>

            <dl className={styles.metricGrid}>
              <Metric label="Completed" value={formatNumber(selectedJob.completed_count)} icon={<CheckCircle2 size={16} />} />
              <Metric label="Running now" value={`${selectedJob.running_count}/${runtime?.worker_concurrency ?? "—"}`} icon={<Users size={16} />} />
              <Metric label="Discovered" value={formatNumber(selectedJob.discovered_count)} icon={<Files size={16} />} />
              <Metric label="Reports / sec" value={metrics.reportsPerSecond.toFixed(2)} icon={<Gauge size={16} />} />
              <Metric label="Fallback" value={formatNumber(selectedJob.fallback_count)} icon={<AlertTriangle size={16} />} />
              <Metric label="Failed" value={formatNumber(selectedJob.failed_count)} icon={<CircleStop size={16} />} />
              <Metric label="Queued" value={formatNumber(selectedJob.pending_count)} icon={<Clock3 size={16} />} />
              <Metric label="Projected finish" value={metrics.etaLabel} icon={<Clock3 size={16} />} />
            </dl>

            <div className={styles.pipeline}>
              <PipelineStep
                complete={selectedJob.producer_done}
                active={!selectedJob.producer_done && !isBulkJobTerminal(selectedJob.status)}
                label={`Discover wards in pages of 100 · ${formatNumber(selectedJob.discovered_count)}`}
              />
              <PipelineStep
                complete={selectedJob.producer_done && selectedJob.pending_count === 0 && selectedJob.running_count === 0}
                active={selectedJob.running_count > 0}
                label={`Generate with bounded concurrency · ${selectedJob.running_count} active`}
              />
              <PipelineStep
                complete={Boolean(selectedJob.export)}
                active={selectedJob.status === "finalizing"}
                label="Verify artifacts and assemble ZIP"
              />
            </div>

            {selectedJob.selection_truncated && (
              <p className={styles.warningCount} role="status">
                The report limit was reached. More wards are available; this run does not include all reports.
              </p>
            )}

            {selectedJob.warnings.length > 0 && (
              <details className={styles.warningCount}>
                <summary>{selectedJob.warnings.length} source warning(s)</summary>
                <ul>{selectedJob.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
              </details>
            )}
          </section>
        ) : (
          <section className={styles.emptyState}>
            <span><ServerCog size={28} /></span>
            <h2>No bulk run selected</h2>
            <p>
              Submit a durable job to process repeated 100-ward source pages with
              concurrent workers. Refresh, navigation, or Cancel stops an active run.
            </p>
          </section>
        )}

        <section className={styles.recentJobs}>
          <div className={styles.sectionHeading}>
            <strong>Recent runs</strong>
            <small>Newest first · only the latest 5 ZIP files are kept</small>
          </div>
          {jobs.length === 0 ? (
            <p>No durable runs yet.</p>
          ) : (
            <div className={styles.jobList}>
              {jobs.map((job) => (
                <button
                  className={job.job_id === selectedJob?.job_id ? styles.jobSelected : styles.jobRow}
                  type="button"
                  key={job.job_id}
                  disabled={isSubmitting || (activeJobId !== null && job.job_id !== activeJobId)}
                  onClick={() => setSelectedJob(job)}
                >
                  <span>
                    <strong>{formatNumber(job.max_reports)} reports</strong>
                    <small>{job.week_start} · {job.timezone}</small>
                  </span>
                  <span>
                    <strong>{formatNumber(job.completed_count)} done</strong>
                    <small>{statusLabel(job.status)}</small>
                  </span>
                </button>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export function RunStatusIndicator({ job }: { job: WeeklyReportBulkJobStatus }) {
  const active = !isBulkJobTerminal(job.status);
  const successful = job.status === "completed";
  const Icon = active ? LoaderCircle : successful ? CheckCircle2 : AlertTriangle;
  return (
    <span
      className={`${styles.statusBadge} ${active ? styles.statusActive : successful ? "" : styles.statusWarning}`}
      role="status"
    >
      <Icon size={13} className={active ? styles.spin : undefined} aria-hidden />
      {statusLabel(job.status)}
    </span>
  );
}

function Metric({ label, value, icon }: { label: string; value: string; icon: ReactNode }) {
  return <div><dt>{icon}{label}</dt><dd>{value}</dd></div>;
}

function PipelineStep({ complete, active, label }: { complete: boolean; active: boolean; label: string }) {
  return (
    <div className={styles.pipelineStep}>
      <span className={complete ? styles.stepDone : active ? styles.stepActive : styles.stepIdle}>
        {complete ? <CheckCircle2 size={13} /> : null}
      </span>
      <span>{label}</span>
    </div>
  );
}

export function parseWardIds(value: string): number[] | undefined | null {
  if (!value.trim()) return undefined;
  const tokens = value.split(",").map((token) => token.trim());
  if (tokens.length > 25 || tokens.some((token) => !/^\d+$/.test(token))) return null;
  const ids = tokens.map(Number);
  if (ids.some((id) => !Number.isSafeInteger(id) || id < 1) || new Set(ids).size !== ids.length) return null;
  return ids.sort((a, b) => a - b);
}

export function parseBulkReportLimit(value: string): number | null {
  if (!/^\d+$/.test(value)) {
    return null;
  }
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= 1 && parsed <= 10_000
    ? parsed
    : null;
}

export function calculateBulkProgress(
  job: WeeklyReportBulkJobStatus | null,
  now: number
) {
  if (!job) {
    return { percent: 0, elapsedSeconds: 0, reportsPerSecond: 0, etaLabel: "—" };
  }
  const startedAt = Date.parse(job.created_at);
  const endedAt = isBulkJobTerminal(job.status) ? Date.parse(job.updated_at) : now;
  const elapsedSeconds = Number.isFinite(startedAt) && Number.isFinite(endedAt)
    ? Math.max(0, Math.floor((endedAt - startedAt) / 1_000))
    : 0;
  const terminalCount = job.completed_count + job.failed_count;
  const target = job.producer_done ? job.discovered_count : job.max_reports;
  const percent = target > 0
    ? Math.min(100, Math.floor((terminalCount / target) * 100))
    : job.status === "completed" ? 100 : 0;
  const reportsPerSecond = elapsedSeconds > 0 ? terminalCount / elapsedSeconds : 0;
  const remaining = Math.max(0, target - terminalCount);
  const etaSeconds = reportsPerSecond > 0 ? remaining / reportsPerSecond : null;
  return {
    percent,
    elapsedSeconds,
    reportsPerSecond,
    etaLabel: isBulkJobTerminal(job.status)
      ? "Finished"
      : etaSeconds === null
        ? "Measuring"
        : formatDuration(Math.ceil(etaSeconds))
  };
}

function createIdempotencyKey(weekStart: string) {
  const random = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `ui-${weekStart}-${random}`;
}

function upsertJob(
  jobs: WeeklyReportBulkJobStatus[],
  updated: WeeklyReportBulkJobStatus
) {
  return [updated, ...jobs.filter((job) => job.job_id !== updated.job_id)].slice(0, 20);
}

function statusLabel(status: WeeklyReportBulkJobStatus["status"]) {
  return ({
    pending: "Queued",
    preparing: "Discovering",
    running: "Generating",
    finalizing: "Packaging",
    completed: "Completed",
    partial: "Completed with failures",
    failed: "Failed",
    cancelling: "Cancelling",
    cancelled: "Cancelled",
    expired: "Expired"
  } as const)[status];
}

function errorText(error: unknown) {
  return error instanceof WeeklyReportBulkClientError || error instanceof Error
    ? error.message
    : "The bulk job could not be updated.";
}

function isMonday(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return false;
  }
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.getUTCDay() === 1;
}

function getLatestMonday() {
  const today = new Date();
  const completedMonday = new Date(today);
  const daysSinceMonday = (today.getDay() + 6) % 7;
  completedMonday.setDate(today.getDate() - daysSinceMonday - 7);
  return completedMonday.toISOString().slice(0, 10);
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("en-US").format(value);
}

function formatDuration(seconds: number) {
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${Math.floor(seconds % 60)}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}
