export interface WeeklyReportRequest {
  week_start: string;
  timezone: string;
}

export interface WardRiskSnapshot {
  danger_days: number;
}

export interface WardRiskDelta {
  danger_days: number;
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
  markdown: string;
  generation_mode: "llm" | "template_fallback";
}

export interface WeeklyReportBatchResult {
  status: "completed";
  week_start: string;
  week_end: string;
  timezone: string;
  reports: WardWeeklyReport[];
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
