import { authenticatedFetch } from "./authenticatedFetch";
export const SCOUT_SCHEDULE_TIMEZONE = "Asia/Seoul" as const;

export const SCOUT_SCHEDULE_RECURRENCES = [
  "once",
  "daily",
  "weekly",
  "monthly"
] as const;

export type ScoutScheduleRecurrence =
  (typeof SCOUT_SCHEDULE_RECURRENCES)[number];

export const SCOUT_SCHEDULE_DAYS = [
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday"
] as const;

export type ScoutScheduleDayOfWeek =
  (typeof SCOUT_SCHEDULE_DAYS)[number];

export const SCOUT_SCHEDULE_STATUSES = [
  "pending",
  "running",
  "succeeded",
  "failed",
  "cancelled",
  "missed"
] as const;

export type ScoutScheduleStatus =
  (typeof SCOUT_SCHEDULE_STATUSES)[number];

export interface ScoutScheduleCreateRequest {
  topic: string;
  keywords: string[];
  additional_instructions?: string;
  recurrence: ScoutScheduleRecurrence;
  run_at?: string;
  schedule_time?: string;
  day_of_week?: ScoutScheduleDayOfWeek;
  day_of_month?: number;
  timezone: typeof SCOUT_SCHEDULE_TIMEZONE;
}

export interface ScheduledScoutRunSuccess {
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

export interface ScheduledScoutRunFailure {
  run_id: string;
  status: "failed";
  started_at: string;
  completed_at: string;
  duration_seconds: number;
  source_count: 0;
  log_artifact: string;
}

export type ScheduledScoutRun =
  | ScheduledScoutRunSuccess
  | ScheduledScoutRunFailure;

export interface ScoutScheduleRecord {
  schedule_id: string;
  topic: string;
  keywords: string[];
  additional_instructions: string | null;
  recurrence: ScoutScheduleRecurrence;
  run_at: string;
  schedule_time: string | null;
  day_of_week: ScoutScheduleDayOfWeek | null;
  day_of_month: number | null;
  timezone: typeof SCOUT_SCHEDULE_TIMEZONE;
  trigger_at: string;
  status: ScoutScheduleStatus;
  created_at: string;
  updated_at: string;
  dispatch_started_at: string | null;
  terminal_at: string | null;
  error_code: string | null;
  error_message: string | null;
  scout_run: ScheduledScoutRun | null;
}

export interface ScoutScheduleListResponse {
  schedules: ScoutScheduleRecord[];
}

interface RequestOptions {
  signal?: AbortSignal;
}

export class ScoutScheduleClientError extends Error {
  readonly status: number | null;

  constructor(message: string, status: number | null = null) {
    super(message);
    this.name = "ScoutScheduleClientError";
    this.status = status;
  }
}

export const SCOUT_SCHEDULER_SERVER_BASE_URL = "/scout-scheduler-api";

export const scoutScheduleClient = {
  async create(
    input: ScoutScheduleCreateRequest,
    { signal }: RequestOptions = {}
  ): Promise<ScoutScheduleRecord> {
    validateCreateRequest(input);
    const additionalInstructions = input.additional_instructions?.trim();
    const response = await request(
      scoutSchedulerUrl("/v1/scout/schedules"),
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          topic: input.topic.trim(),
          keywords: input.keywords.map((keyword) => keyword.trim()),
          ...(additionalInstructions
            ? { additional_instructions: additionalInstructions }
            : {}),
          recurrence: input.recurrence,
          run_at: input.run_at,
          schedule_time: input.schedule_time,
          day_of_week: input.day_of_week,
          day_of_month: input.day_of_month,
          timezone: SCOUT_SCHEDULE_TIMEZONE
        }),
        signal
      }
    );
    return parseScheduleRecord(await readJson(response));
  },

  async list(
    { signal }: RequestOptions = {}
  ): Promise<ScoutScheduleListResponse> {
    const response = await request(
      scoutSchedulerUrl("/v1/scout/schedules"),
      { method: "GET", headers: { Accept: "application/json" }, signal }
    );
    const payload = await readJson(response);
    if (!isRecord(payload) || !Array.isArray(payload.schedules)) {
      throw unexpectedResponseError();
    }
    return {
      schedules: payload.schedules.map(parseScheduleRecord)
    };
  },

  async cancel(
    scheduleId: string,
    { signal }: RequestOptions = {}
  ): Promise<ScoutScheduleRecord> {
    if (!isUuid(scheduleId)) {
      throw new ScoutScheduleClientError("Invalid Scout schedule ID.");
    }
    const response = await request(
      scoutSchedulerUrl(
        `/v1/scout/schedules/${encodeURIComponent(scheduleId)}`
      ),
      { method: "DELETE", headers: { Accept: "application/json" }, signal }
    );
    return parseScheduleRecord(await readJson(response));
  }
};

export function resolveScoutSchedulerServerBaseUrl(_configured?: string) {
  return "/scout-scheduler-api";
}

function scoutSchedulerUrl(path: string) {
  return `${SCOUT_SCHEDULER_SERVER_BASE_URL}${path}`;
}

async function request(url: string, init: RequestInit) {
  try {
    const response = await authenticatedFetch(url, init);
    if (!response.ok) {
      const payload = await readJsonSafely(response);
      const detail =
        isRecord(payload) && typeof payload.detail === "string"
          ? payload.detail
          : `Scout scheduling request failed with HTTP ${response.status}.`;
      throw new ScoutScheduleClientError(detail, response.status);
    }
    return response;
  } catch (error) {
    if (error instanceof ScoutScheduleClientError) {
      throw error;
    }
    throw new ScoutScheduleClientError(
      "Could not reach the Scout scheduling service. Confirm that it is running and try again."
    );
  }
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    throw unexpectedResponseError();
  }
}

async function readJsonSafely(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function validateCreateRequest(input: ScoutScheduleCreateRequest) {
  const topic = input.topic.trim();
  if (topic.length < 3 || topic.length > 500) {
    throw new ScoutScheduleClientError(
      "Enter a topic containing 3 to 500 characters."
    );
  }
  if (
    input.keywords.length > 10 ||
    input.keywords.some(
      (keyword) =>
        !keyword.trim() || keyword.trim().length > 100
    )
  ) {
    throw new ScoutScheduleClientError("Invalid Scout keywords.");
  }
  if (
    input.additional_instructions !== undefined &&
    input.additional_instructions.trim().length > 2_000
  ) {
    throw new ScoutScheduleClientError(
      "Additional research instructions must contain no more than 2,000 characters."
    );
  }
  if (input.timezone !== SCOUT_SCHEDULE_TIMEZONE) {
    throw new ScoutScheduleClientError("Scout schedules use Asia/Seoul.");
  }
  if (!isScheduleRecurrence(input.recurrence)) {
    throw new ScoutScheduleClientError("Choose a valid recurrence.");
  }
  if (input.recurrence === "once") {
    if (
      !isLocalDateTime(input.run_at) ||
      input.schedule_time !== undefined ||
      input.day_of_week !== undefined ||
      input.day_of_month !== undefined
    ) {
      throw new ScoutScheduleClientError(
        "Enter a valid one-time Scout schedule."
      );
    }
    return;
  }
  if (input.run_at !== undefined || !isLocalTime(input.schedule_time)) {
    throw new ScoutScheduleClientError("Enter a valid recurring schedule time.");
  }
  if (
    input.recurrence === "daily" &&
    (input.day_of_week !== undefined || input.day_of_month !== undefined)
  ) {
    throw new ScoutScheduleClientError("Enter a valid daily schedule.");
  }
  if (
    input.recurrence === "weekly" &&
    (!isScheduleDay(input.day_of_week) || input.day_of_month !== undefined)
  ) {
    throw new ScoutScheduleClientError("Choose a valid weekly schedule day.");
  }
  if (
    input.recurrence === "monthly" &&
    (input.day_of_week !== undefined ||
      !Number.isInteger(input.day_of_month) ||
      Number(input.day_of_month) < 1 ||
      Number(input.day_of_month) > 31)
  ) {
    throw new ScoutScheduleClientError("Choose a day of month from 1 to 31.");
  }
}

function parseScheduleRecord(value: unknown): ScoutScheduleRecord {
  const recurrence =
    isRecord(value) && value.recurrence === undefined
      ? "once"
      : isRecord(value) && isScheduleRecurrence(value.recurrence)
        ? value.recurrence
        : null;
  if (
    !isRecord(value) ||
    !isUuid(value.schedule_id) ||
    !isNonEmptyString(value.topic) ||
    !isStringArray(value.keywords) ||
    !isOptionalString(value.additional_instructions) ||
    recurrence === null ||
    !isLocalDateTime(value.run_at) ||
    !isValidPersistedRule(
      recurrence,
      value.schedule_time,
      value.day_of_week,
      value.day_of_month
    ) ||
    value.timezone !== SCOUT_SCHEDULE_TIMEZONE ||
    !isAwareTimestamp(value.trigger_at) ||
    !isScheduleStatus(value.status) ||
    !isAwareTimestamp(value.created_at) ||
    !isAwareTimestamp(value.updated_at) ||
    !isOptionalAwareTimestamp(value.dispatch_started_at) ||
    !isOptionalAwareTimestamp(value.terminal_at) ||
    !isOptionalString(value.error_code) ||
    !isOptionalString(value.error_message)
  ) {
    throw unexpectedResponseError();
  }

  const scoutRun =
    value.scout_run === null || value.scout_run === undefined
      ? null
      : parseScheduledScoutRun(value.scout_run);
  if (!isConsistentTerminalState(value.status, recurrence, scoutRun)) {
    throw unexpectedResponseError();
  }

  return {
    schedule_id: value.schedule_id,
    topic: value.topic,
    keywords: value.keywords,
    additional_instructions:
      typeof value.additional_instructions === "string"
        ? value.additional_instructions
        : null,
    recurrence,
    run_at: value.run_at,
    schedule_time:
      typeof value.schedule_time === "string" ? value.schedule_time : null,
    day_of_week: isScheduleDay(value.day_of_week) ? value.day_of_week : null,
    day_of_month:
      typeof value.day_of_month === "number" ? value.day_of_month : null,
    timezone: value.timezone,
    trigger_at: value.trigger_at,
    status: value.status,
    created_at: value.created_at,
    updated_at: value.updated_at,
    dispatch_started_at: value.dispatch_started_at ?? null,
    terminal_at: value.terminal_at ?? null,
    error_code: value.error_code ?? null,
    error_message: value.error_message ?? null,
    scout_run: scoutRun
  };
}

function parseScheduledScoutRun(value: unknown): ScheduledScoutRun {
  if (
    !isRecord(value) ||
    !isNonEmptyString(value.run_id) ||
    !isAwareTimestamp(value.started_at) ||
    !isAwareTimestamp(value.completed_at) ||
    new Date(value.completed_at).getTime() < new Date(value.started_at).getTime() ||
    !isNonNegativeNumber(value.duration_seconds) ||
    typeof value.source_count !== "number" ||
    !Number.isInteger(value.source_count) ||
    value.source_count < 0 ||
    !isNonEmptyString(value.log_artifact)
  ) {
    throw unexpectedResponseError();
  }

  if (value.status === "success") {
    if (
      !isNonEmptyString(value.report) ||
      !isStringArray(value.sources) ||
      value.sources.some((source) => !isPublicWebUrl(source)) ||
      value.source_count !== value.sources.length ||
      value.source_count < 1 ||
      !isNonEmptyString(value.report_artifact)
    ) {
      throw unexpectedResponseError();
    }
    return {
      run_id: value.run_id,
      status: "success",
      started_at: value.started_at,
      completed_at: value.completed_at,
      duration_seconds: value.duration_seconds,
      source_count: value.source_count,
      report: value.report,
      sources: value.sources,
      report_artifact: value.report_artifact,
      log_artifact: value.log_artifact
    };
  }

  if (
    value.status === "failed" &&
    value.source_count === 0 &&
    (value.sources === undefined ||
      (isStringArray(value.sources) &&
        value.source_count === value.sources.length))
  ) {
    return {
      run_id: value.run_id,
      status: "failed",
      started_at: value.started_at,
      completed_at: value.completed_at,
      duration_seconds: value.duration_seconds,
      source_count: 0,
      log_artifact: value.log_artifact
    };
  }
  throw unexpectedResponseError();
}

function isConsistentTerminalState(
  status: ScoutScheduleStatus,
  recurrence: ScoutScheduleRecurrence,
  scoutRun: ScheduledScoutRun | null
) {
  if (status === "succeeded") {
    return scoutRun?.status === "success";
  }
  if (status === "failed") {
    return scoutRun === null || scoutRun.status === "failed";
  }
  return recurrence === "once" ? scoutRun === null : true;
}

function isValidPersistedRule(
  recurrence: ScoutScheduleRecurrence,
  scheduleTime: unknown,
  dayOfWeek: unknown,
  dayOfMonth: unknown
) {
  if (recurrence === "once") {
    return (
      (scheduleTime === null || scheduleTime === undefined) &&
      (dayOfWeek === null || dayOfWeek === undefined) &&
      (dayOfMonth === null || dayOfMonth === undefined)
    );
  }
  if (!isLocalTime(scheduleTime)) return false;
  if (recurrence === "daily") {
    return (
      (dayOfWeek === null || dayOfWeek === undefined) &&
      (dayOfMonth === null || dayOfMonth === undefined)
    );
  }
  if (recurrence === "weekly") {
    return (
      isScheduleDay(dayOfWeek) &&
      (dayOfMonth === null || dayOfMonth === undefined)
    );
  }
  return (
    (dayOfWeek === null || dayOfWeek === undefined) &&
    typeof dayOfMonth === "number" &&
    Number.isInteger(dayOfMonth) &&
    dayOfMonth >= 1 &&
    dayOfMonth <= 31
  );
}

function isScheduleStatus(value: unknown): value is ScoutScheduleStatus {
  return SCOUT_SCHEDULE_STATUSES.some((status) => status === value);
}

function isScheduleRecurrence(value: unknown): value is ScoutScheduleRecurrence {
  return SCOUT_SCHEDULE_RECURRENCES.some((recurrence) => recurrence === value);
}

function isScheduleDay(value: unknown): value is ScoutScheduleDayOfWeek {
  return SCOUT_SCHEDULE_DAYS.some((day) => day === value);
}

function isLocalTime(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{2}:\d{2}:\d{2}$/.test(value)) {
    return false;
  }
  const [hour, minute, second] = value.split(":").map(Number);
  return hour <= 23 && minute <= 59 && second <= 59;
}

function isLocalDateTime(value: unknown): value is string {
  if (
    typeof value !== "string" ||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?$/.test(value)
  ) {
    return false;
  }
  const [datePart, timePart] = value.split("T");
  const [year, month, day] = datePart.split("-").map(Number);
  const [hour, minute, second] = timePart.split(":").map(Number);
  const calendar = new Date(Date.UTC(year, month - 1, day, hour, minute, second));
  return (
    calendar.getUTCFullYear() === year &&
    calendar.getUTCMonth() === month - 1 &&
    calendar.getUTCDate() === day &&
    calendar.getUTCHours() === hour &&
    calendar.getUTCMinutes() === minute &&
    calendar.getUTCSeconds() === Math.floor(second)
  );
}

function isAwareTimestamp(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) &&
    Number.isFinite(Date.parse(value))
  );
}

function isOptionalAwareTimestamp(value: unknown) {
  return value === null || value === undefined || isAwareTimestamp(value);
}

function isOptionalString(value: unknown) {
  return value === null || value === undefined || typeof value === "string";
}

function isNonNegativeNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isPublicWebUrl(value: string) {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

function isUuid(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
      value
    )
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function unexpectedResponseError() {
  return new ScoutScheduleClientError(
    "The Scout scheduling service returned an unexpected response."
  );
}
