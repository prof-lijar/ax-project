export const WEEKLY_REPORT_BULK_BROWSER_PROXY_PATH = "/weekly-report-bulk-api";

export type WeeklyReportBulkJobState =
  | "pending"
  | "preparing"
  | "running"
  | "finalizing"
  | "completed"
  | "partial"
  | "failed"
  | "cancelling"
  | "cancelled"
  | "expired";

export interface WeeklyReportBulkRuntime {
  schema_version: "1";
  max_reports: 10000;
  source_page_size: 100;
  worker_concurrency: number;
  status_poll_seconds: number;
}

export interface WeeklyReportBulkJobStatus {
  schema_version: "1";
  job_id: string;
  status: WeeklyReportBulkJobState;
  week_start: string;
  timezone: string;
  max_reports: number;
  discovered_count: number;
  pending_count: number;
  running_count: number;
  completed_count: number;
  fallback_count: number;
  failed_count: number;
  producer_done: boolean;
  selection_truncated: boolean;
  next_cursor: string | null;
  warnings: string[];
  export: {
    schema_version: "1";
    uri: string;
    artifact_type: "application/zip";
    checksum: string | null;
    version: string | null;
  } | null;
  created_at: string;
  updated_at: string;
  expires_at: string | null;
}

export interface SubmitWeeklyReportBulkJob {
  week_start: string;
  timezone: string;
  max_reports: number;
  idempotency_key: string;
}

interface RequestOptions {
  signal?: AbortSignal;
  keepalive?: boolean;
}

export class WeeklyReportBulkClientError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "WeeklyReportBulkClientError";
    this.status = status;
  }
}

export const weeklyReportBulkClient = {
  async runtime(options: RequestOptions = {}): Promise<WeeklyReportBulkRuntime> {
    return parseRuntime(
      await request("/v1/weekly-report/bulk/runtime", { signal: options.signal })
    );
  },

  async listJobs(
    limit = 20,
    options: RequestOptions = {}
  ): Promise<WeeklyReportBulkJobStatus[]> {
    const payload = await request(
      `/v1/weekly-report/bulk/jobs?limit=${encodeURIComponent(limit)}`,
      { signal: options.signal }
    );
    if (!isRecord(payload) || !Array.isArray(payload.jobs)) {
      throw malformedResponse();
    }
    return payload.jobs.map(parseJobStatus);
  },

  async submit(
    input: SubmitWeeklyReportBulkJob,
    options: RequestOptions = {}
  ): Promise<WeeklyReportBulkJobStatus> {
    return parseJobStatus(
      await request("/v1/weekly-report/bulk/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
        signal: options.signal
      })
    );
  },

  async status(
    jobId: string,
    options: RequestOptions = {}
  ): Promise<WeeklyReportBulkJobStatus> {
    return parseJobStatus(
      await request(`/v1/weekly-report/bulk/jobs/${encodeURIComponent(jobId)}`, {
        signal: options.signal
      })
    );
  },

  async cancel(
    jobId: string,
    options: RequestOptions = {}
  ): Promise<WeeklyReportBulkJobStatus> {
    return parseJobStatus(
      await request(
        `/v1/weekly-report/bulk/jobs/${encodeURIComponent(jobId)}/cancel`,
        {
          method: "POST",
          signal: options.signal,
          keepalive: options.keepalive
        }
      )
    );
  },

  exportUrl(jobId: string) {
    return apiUrl(
      `/v1/weekly-report/bulk/jobs/${encodeURIComponent(jobId)}/export`
    );
  }
};

export function isBulkJobTerminal(status: WeeklyReportBulkJobState) {
  return [
    "completed",
    "partial",
    "failed",
    "cancelled",
    "expired"
  ].includes(status);
}

async function request(path: string, init: RequestInit = {}) {
  try {
    const response = await fetch(apiUrl(path), {
      ...init,
      headers: { Accept: "application/json", ...init.headers }
    });
    if (!response.ok) {
      throw new WeeklyReportBulkClientError(
        await errorMessage(response),
        response.status
      );
    }
    return JSON.parse(await response.text()) as unknown;
  } catch (error) {
    if (error instanceof WeeklyReportBulkClientError) {
      throw error;
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new WeeklyReportBulkClientError("The bulk request was cancelled.");
    }
    if (error instanceof SyntaxError) {
      throw malformedResponse();
    }
    throw new WeeklyReportBulkClientError(
      "Unable to reach the Weekly Reporter bulk service."
    );
  }
}

function apiUrl(path: string) {
  const direct = import.meta.env.VITE_WEEKLY_REPORT_BULK_API_BASE_URL?.trim();
  const base = isTauriRuntime() && direct
    ? direct.replace(/\/+$/, "")
    : WEEKLY_REPORT_BULK_BROWSER_PROXY_PATH;
  return `${base}${path}`;
}

async function errorMessage(response: Response) {
  const fallback = `Bulk request failed with HTTP ${response.status}.`;
  const body = (await response.text()).trim();
  if (!body) {
    return fallback;
  }
  try {
    const payload = JSON.parse(body) as unknown;
    if (isRecord(payload) && typeof payload.detail === "string") {
      return payload.detail;
    }
  } catch {
    return body.slice(0, 300) || fallback;
  }
  return fallback;
}

function parseRuntime(value: unknown): WeeklyReportBulkRuntime {
  if (
    !isRecord(value) ||
    value.schema_version !== "1" ||
    value.max_reports !== 10000 ||
    value.source_page_size !== 100 ||
    !isBoundedInteger(value.worker_concurrency, 1, 512) ||
    typeof value.status_poll_seconds !== "number" ||
    value.status_poll_seconds < 0.5 ||
    value.status_poll_seconds > 30
  ) {
    throw malformedResponse();
  }
  return value as unknown as WeeklyReportBulkRuntime;
}

function parseJobStatus(value: unknown): WeeklyReportBulkJobStatus {
  if (
    !isRecord(value) ||
    value.schema_version !== "1" ||
    typeof value.job_id !== "string" ||
    !isBulkJobState(value.status) ||
    typeof value.week_start !== "string" ||
    typeof value.timezone !== "string" ||
    !isBoundedInteger(value.max_reports, 1, 10000) ||
    ![
      "discovered_count",
      "pending_count",
      "running_count",
      "completed_count",
      "fallback_count",
      "failed_count"
    ].every((field) => isBoundedInteger(value[field], 0, 10000)) ||
    typeof value.producer_done !== "boolean" ||
    typeof value.selection_truncated !== "boolean" ||
    !(value.next_cursor === null || typeof value.next_cursor === "string") ||
    !Array.isArray(value.warnings) ||
    !value.warnings.every((item) => typeof item === "string") ||
    !isExport(value.export) ||
    typeof value.created_at !== "string" ||
    typeof value.updated_at !== "string" ||
    !(value.expires_at === null || typeof value.expires_at === "string")
  ) {
    throw malformedResponse();
  }
  return value as unknown as WeeklyReportBulkJobStatus;
}

function isExport(value: unknown) {
  return (
    value === null ||
    (isRecord(value) &&
      value.schema_version === "1" &&
      typeof value.uri === "string" &&
      value.artifact_type === "application/zip" &&
      (value.checksum === null || typeof value.checksum === "string") &&
      (value.version === null || typeof value.version === "string"))
  );
}

function isBulkJobState(value: unknown): value is WeeklyReportBulkJobState {
  return typeof value === "string" && [
    "pending",
    "preparing",
    "running",
    "finalizing",
    "completed",
    "partial",
    "failed",
    "cancelling",
    "cancelled",
    "expired"
  ].includes(value);
}

function isBoundedInteger(value: unknown, minimum: number, maximum: number) {
  return Number.isInteger(value) && Number(value) >= minimum && Number(value) <= maximum;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function malformedResponse() {
  return new WeeklyReportBulkClientError(
    "The Weekly Reporter bulk service returned an invalid response."
  );
}

function isTauriRuntime() {
  return "__TAURI_INTERNALS__" in globalThis;
}
