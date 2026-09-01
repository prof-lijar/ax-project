export const SCOUT_SERVER_BASE_URL = resolveScoutServerBaseUrl(
  import.meta.env.VITE_SCOUT_API_BASE_URL
);

export interface ScoutRunRequest {
  topic: string;
  keywords: string[];
  additional_instructions?: string;
}

export interface ScoutRunResponse {
  run_id: string;
  status: "success";
  started_at: string;
  completed_at: string;
  duration_seconds: number;
  source_count: number;
  report: string;
  sources: string[];
  report_artifact: string;
  log_artifact: string;
}

export interface ScoutRunFailure {
  run_id: string;
  status: "failed";
  started_at: string;
  completed_at: string;
  duration_seconds: number;
  source_count: 0;
  log_artifact: string;
}

interface ScoutRequestOptions {
  signal?: AbortSignal;
}

export class ScoutClientError extends Error {
  status: number | null;
  run: ScoutRunFailure | null;

  constructor(
    message: string,
    status: number | null = null,
    run: ScoutRunFailure | null = null
  ) {
    super(message);
    this.name = "ScoutClientError";
    this.status = status;
    this.run = run;
  }
}

export const scoutClient = {
  async run(
    input: ScoutRunRequest,
    options: ScoutRequestOptions = {}
  ): Promise<ScoutRunResponse> {
    const request = normalizeRequest(input);
    let response: Response;

    try {
      response = await fetch(scoutServerUrl("/v1/scout/runs"), {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify(request),
        signal: options.signal
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new ScoutClientError("The Scout request was cancelled.");
      }
      throw new ScoutClientError(
        "Could not reach the Scout service. Confirm that it is running and try again."
      );
    }

    const payload = await readJson(response);
    if (!response.ok) {
      throw new ScoutClientError(
        readErrorDetail(payload) ?? fallbackHttpMessage(response.status),
        response.status,
        readFailureRun(payload)
      );
    }
    if (!isScoutRunResponse(payload)) {
      throw new ScoutClientError(
        "The Scout service returned an unexpected response.",
        response.status
      );
    }
    return payload;
  }
};

export function resolveScoutServerBaseUrl(configuredUrl?: string) {
  const value = configuredUrl?.trim() || defaultScoutServerBaseUrl();
  return value.replace(/\/+$/, "");
}

function scoutServerUrl(path: string) {
  return `${SCOUT_SERVER_BASE_URL}${path}`;
}

function defaultScoutServerBaseUrl() {
  if (typeof window === "undefined") {
    return "http://127.0.0.1:8091";
  }
  return `${window.location.protocol}//${window.location.hostname}:8091`;
}

function normalizeRequest(input: ScoutRunRequest): ScoutRunRequest {
  const topic = input.topic.trim();
  if (topic.length < 3 || topic.length > 500) {
    throw new ScoutClientError("Topic must contain 3 to 500 characters.");
  }
  if (input.keywords.length > 10) {
    throw new ScoutClientError("Enter no more than 10 keywords.");
  }

  const keywords: string[] = [];
  const seen = new Set<string>();
  for (const rawKeyword of input.keywords) {
    const keyword = rawKeyword.trim();
    if (!keyword || keyword.length > 100) {
      throw new ScoutClientError(
        "Each keyword must contain 1 to 100 characters."
      );
    }
    const key = keyword.toLocaleLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      keywords.push(keyword);
    }
  }
  const additionalInstructions = input.additional_instructions?.trim();
  if (additionalInstructions && additionalInstructions.length > 2_000) {
    throw new ScoutClientError(
      "Additional research instructions must contain no more than 2,000 characters."
    );
  }
  return {
    topic,
    keywords,
    ...(additionalInstructions
      ? { additional_instructions: additionalInstructions }
      : {})
  };
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    if (response.ok) {
      throw new ScoutClientError(
        "The Scout service returned an unreadable response.",
        response.status
      );
    }
    return null;
  }
}

function readErrorDetail(payload: unknown): string | null {
  if (!isRecord(payload)) {
    return null;
  }
  if (typeof payload.detail === "string") {
    return sanitizeMessage(payload.detail);
  }
  if (Array.isArray(payload.detail)) {
    const messages = payload.detail
      .map((item) =>
        isRecord(item) && typeof item.msg === "string"
          ? sanitizeMessage(item.msg)
          : null
      )
      .filter((item): item is string => Boolean(item));
    return messages.length > 0 ? messages.join(" ") : null;
  }
  return null;
}

function sanitizeMessage(value: string) {
  return value.replace(/\s+/g, " ").trim().slice(0, 400) || null;
}

function readFailureRun(payload: unknown): ScoutRunFailure | null {
  if (!isRecord(payload) || !isScoutRunFailure(payload.run)) {
    return null;
  }
  return payload.run;
}

function fallbackHttpMessage(status: number) {
  if (status === 503) {
    return "The Scout service is not ready. Confirm its model configuration and try again.";
  }
  return `The Scout request failed (HTTP ${status}).`;
}

function isScoutRunResponse(value: unknown): value is ScoutRunResponse {
  if (!isRecord(value)) {
    return false;
  }
  return (
    isNonEmptyString(value.run_id) &&
    value.status === "success" &&
    hasValidTerminalTiming(value) &&
    isNonEmptyString(value.report) &&
    Array.isArray(value.sources) &&
    value.sources.length > 0 &&
    value.sources.every(isPublicSourceUrl) &&
    value.source_count === value.sources.length &&
    isNonEmptyString(value.report_artifact) &&
    isNonEmptyString(value.log_artifact)
  );
}

function isScoutRunFailure(value: unknown): value is ScoutRunFailure {
  if (!isRecord(value)) {
    return false;
  }
  return (
    isNonEmptyString(value.run_id) &&
    value.status === "failed" &&
    hasValidTerminalTiming(value) &&
    value.source_count === 0 &&
    isNonEmptyString(value.log_artifact)
  );
}

function hasValidTerminalTiming(value: Record<string, unknown>) {
  if (
    !isTimestamp(value.started_at) ||
    !isTimestamp(value.completed_at) ||
    typeof value.duration_seconds !== "number" ||
    !Number.isFinite(value.duration_seconds) ||
    value.duration_seconds < 0 ||
    typeof value.source_count !== "number" ||
    !Number.isInteger(value.source_count) ||
    value.source_count < 0
  ) {
    return false;
  }
  return Date.parse(value.completed_at) >= Date.parse(value.started_at);
}

function isTimestamp(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) &&
    Number.isFinite(Date.parse(value))
  );
}

function isPublicSourceUrl(value: unknown): value is string {
  if (typeof value !== "string") {
    return false;
  }
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
