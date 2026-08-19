import type {
  WardWeeklyReport,
  WeeklyReportBatchResult,
  WeeklyReportProgressEvent,
  WeeklyReportRequest
} from "../types/weeklyReport";
import { backendUrl } from "./nextcloudBackendClient";

export const DEFAULT_AGENT_SERVER_BASE_URL = "http://192.168.0.18:2024";

export type AgentServerErrorCode =
  | "attachment_error"
  | "cancelled"
  | "http_error"
  | "malformed_stream"
  | "network_error"
  | "request_error";

export class AgentServerError extends Error {
  readonly code: AgentServerErrorCode;
  readonly status?: number;
  readonly serverCode?: string;
  readonly filename?: string;
  readonly originalCause?: unknown;

  constructor(
    code: AgentServerErrorCode,
    message: string,
    options?: {
      cause?: unknown;
      filename?: string;
      serverCode?: string;
      status?: number;
    }
  ) {
    super(message);
    this.name = "AgentServerError";
    this.code = code;
    this.status = options?.status;
    this.serverCode = options?.serverCode;
    this.filename = options?.filename;
    this.originalCause = options?.cause;
  }
}

interface RequestOptions {
  signal?: AbortSignal;
}

interface ChatRequestOptions extends RequestOptions {
  files?: readonly File[];
  onResponse?: (response: string) => void;
}

interface WeeklyReportRequestOptions extends RequestOptions {
  onProgress?: (event: WeeklyReportProgressEvent) => void;
}

interface SseEvent {
  event: string;
  data: string;
}

const configuredBaseUrl = (
  import.meta.env.VITE_AGENT_SERVER_BASE_URL?.trim() ||
  DEFAULT_AGENT_SERVER_BASE_URL
).replace(/\/+$/, "");

export const agentServerClient = {
  async checkHealth({ signal }: RequestOptions = {}): Promise<boolean> {
    try {
      const response = await fetch(agentServerUrl("/ok"), {
        method: "GET",
        headers: { Accept: "application/json" },
        signal
      });

      if (!response.ok) {
        throw await httpError(response, "Health check failed");
      }
      return true;
    } catch (error) {
      throw normalizeRequestError(error, signal, "Unable to reach the Agent Server.");
    }
  },

  async streamChat(
    message: string,
    { files = [], signal, onResponse }: ChatRequestOptions = {}
  ): Promise<string> {
    try {
      const body = new FormData();
      body.append("prompt", message);
      for (const file of files) {
        body.append("files", file, file.name);
      }

      const response = await fetch(backendUrl("/api/chat/stream"), {
        method: "POST",
        headers: { Accept: "text/event-stream" },
        body,
        signal
      });

      if (!response.ok) {
        throw await httpError(response, "Chat request failed");
      }
      if (!response.body) {
        throw new AgentServerError(
          "malformed_stream",
          "The Agent Server returned an empty response stream."
        );
      }

      return await readFinalAssistantResponse(response.body, onResponse);
    } catch (error) {
      throw normalizeRequestError(
        error,
        signal,
        "The Agent Server could not complete the request."
      );
    }
  },

  async runWeeklyReport(
    input: WeeklyReportRequest,
    { signal, onProgress }: WeeklyReportRequestOptions = {}
  ): Promise<WeeklyReportBatchResult> {
    try {
      const response = await fetch(agentServerUrl("/runs/stream"), {
        method: "POST",
        headers: {
          Accept: "text/event-stream",
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          assistant_id: "ansimk_weekly_reporter",
          input,
          config: { max_concurrency: 4 },
          stream_mode: ["custom", "values"],
          stream_subgraphs: true,
          on_disconnect: "cancel"
        }),
        signal
      });

      if (!response.ok) {
        throw await httpError(response, "Weekly report request failed");
      }
      if (!response.body) {
        throw new AgentServerError(
          "malformed_stream",
          "The Agent Server returned an empty response stream."
        );
      }

      return await readWeeklyReportResult(response.body, onProgress);
    } catch (error) {
      throw normalizeRequestError(
        error,
        signal,
        "The Weekly Reporter could not complete the request."
      );
    }
  }
};

export async function readFinalAssistantResponse(
  stream: ReadableStream<Uint8Array>,
  onResponse?: (response: string) => void
): Promise<string> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let finalResponse: string | null = null;
  let streamedResponse = "";
  let fullyRead = false;
  const parser = new SseParser((event) => {
    if (event.event === "custom" || event.event === "error") {
      const deltaEvent = parseJsonEvent(event.data, "streamed chat data");
      const requestError = parseStreamedRequestError(deltaEvent);
      if (requestError) {
        throw requestError;
      }
      if (event.event === "error") {
        throw new AgentServerError(
          "malformed_stream",
          "The chat service returned an invalid error event."
        );
      }
      if (
        isRecord(deltaEvent) &&
        typeof deltaEvent.response_complete === "string"
      ) {
        finalResponse = deltaEvent.response_complete;
        if (finalResponse !== streamedResponse) {
          streamedResponse = finalResponse;
          onResponse?.(finalResponse);
        }
        return;
      }
      if (
        typeof deltaEvent !== "object" ||
        deltaEvent === null ||
        !("response_delta" in deltaEvent) ||
        typeof (deltaEvent as { response_delta?: unknown }).response_delta !==
          "string"
      ) {
        throw new AgentServerError(
          "malformed_stream",
          "The Agent Server returned an invalid response delta."
        );
      }
      streamedResponse += (
        deltaEvent as { response_delta: string }
      ).response_delta;
      onResponse?.(streamedResponse);
      return;
    }
    if (event.event !== "values") {
      return;
    }

    const value = parseJsonEvent(event.data, "chat data");
    if (typeof value !== "object" || value === null) {
      throw new AgentServerError(
        "malformed_stream",
        "The Agent Server returned an invalid chat event."
      );
    }

    if (!("response" in value)) {
      return;
    }

    const response = (value as { response?: unknown }).response;
    if (typeof response !== "string") {
      throw new AgentServerError(
        "malformed_stream",
        "The Agent Server returned an invalid assistant response."
      );
    }
    finalResponse = response;
    if (response !== streamedResponse) {
      streamedResponse = response;
      onResponse?.(response);
    }
  });

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      parser.push(decoder.decode(value, { stream: true }));
    }
    parser.push(decoder.decode());
    parser.finish();
    fullyRead = true;
  } finally {
    if (!fullyRead) {
      try {
        await reader.cancel();
      } catch {
        // Preserve the original stream/parser error.
      }
    }
    reader.releaseLock();
  }

  if (finalResponse === null) {
    throw new AgentServerError(
      "malformed_stream",
      "The Agent Server stream ended without an assistant response."
    );
  }

  return finalResponse;
}

function parseStreamedRequestError(value: unknown): AgentServerError | null {
  if (!isRecord(value)) {
    return null;
  }

  const nested = isRecord(value.error) ? value.error : value;
  const code = nested.code ?? nested.error_code;
  const message = nested.message ?? nested.error_message;
  if (typeof code !== "string" || typeof message !== "string") {
    return null;
  }
  const filename = typeof nested.filename === "string" ? nested.filename : undefined;
  return new AgentServerError(
    "request_error",
    structuredErrorMessage(message, filename),
    { filename, serverCode: code }
  );
}

export async function readWeeklyReportResult(
  stream: ReadableStream<Uint8Array>,
  onProgress?: (event: WeeklyReportProgressEvent) => void
): Promise<WeeklyReportBatchResult> {
  let finalResult: WeeklyReportBatchResult | null = null;

  await readSseStream(stream, (event) => {
    if (isCustomStreamEvent(event.event)) {
      const data = parseJsonEvent(event.data, "weekly report progress data");
      const progress = parseWeeklyReportProgress(data);
      onProgress?.(progress);
      return;
    }
    if (event.event !== "values") {
      return;
    }

    const value = parseJsonEvent(event.data, "weekly report data");
    if (!isRecord(value) || value.status !== "completed") {
      return;
    }
    finalResult = parseWeeklyReportResult(value);
  });

  if (finalResult === null) {
    throw new AgentServerError(
      "malformed_stream",
      "The Agent Server stream ended without a weekly report result."
    );
  }
  return finalResult;
}

function isCustomStreamEvent(eventName: string) {
  return eventName === "custom" || eventName.startsWith("custom|");
}

async function readSseStream(
  stream: ReadableStream<Uint8Array>,
  onEvent: (event: SseEvent) => void
) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  const parser = new SseParser(onEvent);

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      parser.push(decoder.decode(value, { stream: true }));
    }
    parser.push(decoder.decode());
    parser.finish();
  } finally {
    reader.releaseLock();
  }
}

function parseWeeklyReportProgress(value: unknown): WeeklyReportProgressEvent {
  if (!isRecord(value) || typeof value.event !== "string") {
    throw malformedWeeklyReportData("progress event");
  }

  if (value.event === "batch_started" && typeof value.week_start === "string") {
    return { event: value.event, week_start: value.week_start };
  }
  if (
    value.event === "risk_data_loaded" &&
    typeof value.ward_count === "number" &&
    typeof value.selection_truncated === "boolean"
  ) {
    return {
      event: value.event,
      ward_count: value.ward_count,
      selection_truncated: value.selection_truncated
    };
  }
  if (value.event === "ward_report_fallback") {
    return { event: value.event };
  }
  if (value.event === "ward_report_ready" && isGenerationMode(value.generation_mode)) {
    return {
      event: value.event,
      generation_mode: value.generation_mode
    };
  }
  if (
    value.event === "batch_completed" &&
    typeof value.report_count === "number" &&
    typeof value.fallback_count === "number"
  ) {
    return {
      event: value.event,
      report_count: value.report_count,
      fallback_count: value.fallback_count
    };
  }
  throw malformedWeeklyReportData("progress event");
}

function parseWeeklyReportResult(value: Record<string, unknown>) {
  if (
    value.status !== "completed" ||
    typeof value.week_start !== "string" ||
    typeof value.week_end !== "string" ||
    typeof value.timezone !== "string" ||
    !Array.isArray(value.reports) ||
    value.reports.length > 25 ||
    !Array.isArray(value.skipped) ||
    !value.skipped.every(isSkippedWard) ||
    !(value.next_cursor === null || typeof value.next_cursor === "string") ||
    !Array.isArray(value.warnings) ||
    !value.warnings.every((warning) => typeof warning === "string")
  ) {
    throw malformedWeeklyReportData("result");
  }

  const reports = value.reports.map(parseWardWeeklyReport);
  return {
    status: value.status,
    week_start: value.week_start,
    week_end: value.week_end,
    timezone: value.timezone,
    reports,
    skipped: value.skipped,
    next_cursor: value.next_cursor,
    warnings: value.warnings as string[]
  } satisfies WeeklyReportBatchResult;
}

function parseWardWeeklyReport(value: unknown): WardWeeklyReport {
  if (
    !isRecord(value) ||
    typeof value.ward_id !== "number" ||
    typeof value.display_name !== "string" ||
    typeof value.markdown !== "string" ||
    !isGenerationMode(value.generation_mode) ||
    !isWeeklyNarrative(value.narrative) ||
    !isGenerationMetadata(value.generation) ||
    !isRecord(value.metrics) ||
    !isMetricSnapshot(value.metrics.current) ||
    !isMetricSnapshot(value.metrics.previous) ||
    !isMetricDelta(value.metrics.delta) ||
    typeof value.metrics.ward_id !== "number" ||
    typeof value.metrics.display_name !== "string" ||
    typeof value.metrics.week_start !== "string" ||
    typeof value.metrics.week_end !== "string"
  ) {
    throw malformedWeeklyReportData("ward report");
  }
  return value as unknown as WardWeeklyReport;
}

function isMetricSnapshot(value: unknown) {
  return (
    hasNumberFields(value, [
      "covered_days",
      "daily_summary_count",
      "device_count",
      "temperature_count",
      "humidity_count",
      "light_count",
      "risk_detected_count",
      "risk_resolved_count",
      "danger_days",
      "dispatch_request_count",
      "unresolved_dispatch_count"
    ]) &&
    hasNullableNumberFields(value, [
      "temperature_avg",
      "temperature_min",
      "temperature_max",
      "humidity_avg",
      "humidity_min",
      "humidity_max",
      "light_avg",
      "light_min",
      "light_max",
      "light_on_time_minutes_avg",
      "movement_count_avg",
      "remote_control_count_avg",
      "night_awake_count_avg",
      "risk_score_avg"
    ]) &&
    hasNullableStringFields(value, ["wake_up_time_avg", "sleep_time_avg"])
  );
}

function isMetricDelta(value: unknown) {
  return (
    hasNumberFields(value, [
      "covered_days",
      "risk_detected_count",
      "risk_resolved_count",
      "danger_days",
      "dispatch_request_count",
      "unresolved_dispatch_count"
    ]) &&
    hasNullableNumberFields(value, [
      "temperature_avg",
      "humidity_avg",
      "light_avg",
      "light_on_time_minutes_avg",
      "movement_count_avg",
      "remote_control_count_avg",
      "wake_up_time_minutes",
      "sleep_time_minutes",
      "night_awake_count_avg",
      "risk_score_avg"
    ])
  );
}

function hasNumberFields(value: unknown, fields: string[]) {
  return (
    isRecord(value) &&
    fields.every((field) => typeof value[field] === "number")
  );
}

function hasNullableNumberFields(value: unknown, fields: string[]) {
  return (
    isRecord(value) &&
    fields.every(
      (field) => value[field] === null || typeof value[field] === "number"
    )
  );
}

function hasNullableStringFields(value: unknown, fields: string[]) {
  return (
    isRecord(value) &&
    fields.every(
      (field) => value[field] === null || typeof value[field] === "string"
    )
  );
}

function isWeeklyNarrative(value: unknown) {
  return (
    isRecord(value) &&
    typeof value.headline === "string" &&
    typeof value.analysis_text === "string" &&
    Array.isArray(value.observations) &&
    value.observations.every((item) => typeof item === "string") &&
    Array.isArray(value.suggestions) &&
    value.suggestions.every((item) => typeof item === "string")
  );
}

function isGenerationMetadata(value: unknown) {
  return (
    isRecord(value) &&
    typeof value.prompt_version === "string" &&
    (value.model === null || typeof value.model === "string") &&
    (value.validation_status === "passed" || value.validation_status === "fallback") &&
    (value.fallback_reason === null || typeof value.fallback_reason === "string")
  );
}

function isSkippedWard(value: unknown) {
  return (
    isRecord(value) &&
    typeof value.ward_id === "number" &&
    (value.reason === "not_found" || value.reason === "source_error")
  );
}

function isGenerationMode(value: unknown): value is WardWeeklyReport["generation_mode"] {
  return value === "llm" || value === "template_fallback";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function malformedWeeklyReportData(description: string) {
  return new AgentServerError(
    "malformed_stream",
    `The Agent Server returned an invalid weekly report ${description}.`
  );
}

function parseJsonEvent(data: string, description: string): unknown {
  try {
    return JSON.parse(data);
  } catch (error) {
    throw new AgentServerError(
      "malformed_stream",
      `The Agent Server returned malformed ${description}.`,
      { cause: error }
    );
  }
}

class SseParser {
  private buffer = "";
  private eventName = "";
  private dataLines: string[] = [];

  constructor(private readonly onEvent: (event: SseEvent) => void) {}

  push(chunk: string) {
    this.buffer += chunk;

    let newlineIndex = this.buffer.indexOf("\n");
    while (newlineIndex !== -1) {
      const rawLine = this.buffer.slice(0, newlineIndex);
      this.buffer = this.buffer.slice(newlineIndex + 1);
      this.consumeLine(rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine);
      newlineIndex = this.buffer.indexOf("\n");
    }
  }

  finish() {
    if (this.buffer.length > 0) {
      const line = this.buffer.endsWith("\r")
        ? this.buffer.slice(0, -1)
        : this.buffer;
      this.consumeLine(line);
      this.buffer = "";
    }
    this.dispatch();
  }

  private consumeLine(line: string) {
    if (line === "") {
      this.dispatch();
      return;
    }
    if (line.startsWith(":")) {
      return;
    }

    const colonIndex = line.indexOf(":");
    const field = colonIndex === -1 ? line : line.slice(0, colonIndex);
    let value = colonIndex === -1 ? "" : line.slice(colonIndex + 1);
    if (value.startsWith(" ")) {
      value = value.slice(1);
    }

    if (field === "event") {
      this.eventName = value;
    } else if (field === "data") {
      this.dataLines.push(value);
    }
  }

  private dispatch() {
    if (this.dataLines.length > 0) {
      this.onEvent({
        event: this.eventName || "message",
        data: this.dataLines.join("\n")
      });
    }
    this.eventName = "";
    this.dataLines = [];
  }
}

function agentServerUrl(path: string) {
  const baseUrl = isTauriRuntime() ? configuredBaseUrl : "/agent-server";
  return `${baseUrl}${path}`;
}

function isTauriRuntime() {
  return (
    typeof window !== "undefined" &&
    "__TAURI_INTERNALS__" in (window as Window & { __TAURI_INTERNALS__?: unknown })
  );
}

async function httpError(response: Response, prefix: string) {
  let detail = "";
  let errorCode: AgentServerErrorCode = "http_error";
  let filename: string | undefined;
  let serverCode: string | undefined;
  try {
    const rawBody = (await response.text()).trim();
    if (rawBody) {
      try {
        const parsed = JSON.parse(rawBody) as unknown;
        if (isRecord(parsed)) {
          const nested = isRecord(parsed.detail)
            ? parsed.detail
            : isRecord(parsed.error)
              ? parsed.error
              : parsed;
          const message = nested.message ?? nested.detail;
          if (typeof message === "string") {
            detail = message.slice(0, 300);
          }
          if (typeof nested.code === "string") {
            errorCode = "attachment_error";
            serverCode = nested.code;
          }
          if (typeof nested.filename === "string") {
            filename = nested.filename;
          }
        }
      } catch {
        detail = rawBody.slice(0, 300);
      }
    }
  } catch {
    // The status code still provides a useful error if the body cannot be read.
  }
  const suffix = detail ? `: ${structuredErrorMessage(detail, filename)}` : ".";
  return new AgentServerError(
    errorCode,
    `${prefix} (${response.status})${suffix}`,
    { filename, serverCode, status: response.status }
  );
}

function structuredErrorMessage(message: string, filename?: string) {
  if (!filename || message.includes(filename)) {
    return message;
  }
  return `${filename}: ${message}`;
}

function normalizeRequestError(
  error: unknown,
  signal: AbortSignal | undefined,
  fallbackMessage: string
) {
  if (error instanceof AgentServerError) {
    return error;
  }
  if (signal?.aborted || (error instanceof DOMException && error.name === "AbortError")) {
    return new AgentServerError("cancelled", "The request was cancelled.", {
      cause: error
    });
  }
  return new AgentServerError("network_error", fallbackMessage, { cause: error });
}
