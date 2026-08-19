export interface WeeklyReportRequest {
  week_start: string;
  timezone: string;
  limit: number;
}

export interface WardRiskSnapshot {
  covered_days: number;
  daily_summary_count: number;
  device_count: number;
  temperature_avg: number | null;
  temperature_min: number | null;
  temperature_max: number | null;
  temperature_count: number;
  humidity_avg: number | null;
  humidity_min: number | null;
  humidity_max: number | null;
  humidity_count: number;
  light_avg: number | null;
  light_min: number | null;
  light_max: number | null;
  light_count: number;
  light_on_time_minutes_avg: number | null;
  movement_count_avg: number | null;
  remote_control_count_avg: number | null;
  wake_up_time_avg: string | null;
  sleep_time_avg: string | null;
  night_awake_count_avg: number | null;
  risk_detected_count: number;
  risk_resolved_count: number;
  risk_score_avg: number | null;
  danger_days: number;
  dispatch_request_count: number;
  unresolved_dispatch_count: number;
}

export interface WardRiskDelta {
  covered_days: number;
  temperature_avg: number | null;
  humidity_avg: number | null;
  light_avg: number | null;
  light_on_time_minutes_avg: number | null;
  movement_count_avg: number | null;
  remote_control_count_avg: number | null;
  wake_up_time_minutes: number | null;
  sleep_time_minutes: number | null;
  night_awake_count_avg: number | null;
  risk_detected_count: number;
  risk_resolved_count: number;
  risk_score_avg: number | null;
  danger_days: number;
  dispatch_request_count: number;
  unresolved_dispatch_count: number;
}

export interface WeeklyNarrative {
  headline: string;
  analysis_text: string;
  observations: string[];
  suggestions: string[];
}

export interface NarrativeGenerationMetadata {
  prompt_version: string;
  model: string | null;
  validation_status: "passed" | "fallback";
  fallback_reason: string | null;
}

export interface WardWeeklyReport {
  ward_id: number;
  display_name: string;
  metrics: {
    ward_id: number;
    display_name: string;
    week_start: string;
    week_end: string;
    current: WardRiskSnapshot;
    previous: WardRiskSnapshot;
    delta: WardRiskDelta;
  };
  narrative: WeeklyNarrative;
  markdown: string;
  generation_mode: "llm" | "template_fallback";
  generation: NarrativeGenerationMetadata;
}

export interface SkippedWard {
  ward_id: number;
  reason: "not_found" | "source_error";
}

export interface WeeklyReportBatchResult {
  status: "completed";
  week_start: string;
  week_end: string;
  timezone: string;
  reports: WardWeeklyReport[];
  skipped: SkippedWard[];
  next_cursor: string | null;
  warnings: string[];
}

export type WeeklyReportProgressEvent =
  | { event: "batch_started"; week_start: string }
  | {
      event: "risk_data_loaded";
      ward_count: number;
      selection_truncated: boolean;
    }
  | { event: "ward_report_fallback" }
  | {
      event: "ward_report_ready";
      generation_mode: "llm" | "template_fallback";
    }
  | {
      event: "batch_completed";
      report_count: number;
      fallback_count: number;
    };
