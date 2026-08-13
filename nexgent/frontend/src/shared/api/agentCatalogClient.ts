import type {
  AgentDefinition,
  AgentReadiness,
  AgentRunStatus
} from "../types/agents";

export interface AgentCatalogRecord extends Omit<AgentDefinition, "readiness" | "recentRuns"> {
  readiness: string;
  recentRuns: Array<Omit<AgentDefinition["recentRuns"][number], "status"> & {
    status: string;
  }>;
}

const weeklyReporterRecord: AgentCatalogRecord = {
  id: "ansimk-weekly-reporter",
  name: "Weekly Reporter",
  role: "Work insight collaborator",
  description:
    "Compares each person's current and previous work week, then prepares a grounded Korean Markdown report.",
  graphId: "ansimk_weekly_reporter",
  readiness: "ready",
  currentWork: "Ready for a manual weekly report request",
  runtimeLabel: "LangGraph",
  lastObservedAt: "2026-08-12T18:07:00+09:00",
  observationMode: "preview",
  capabilities: [
    "Weekly activity comparison",
    "Per-person report generation",
    "Korean Markdown output",
    "Deterministic fallback reporting"
  ],
  inputs: [
    {
      name: "week_start",
      description: "Monday in YYYY-MM-DD format",
      required: true
    },
    {
      name: "timezone",
      description: "Report timezone; defaults to Asia/Seoul",
      required: false
    }
  ],
  outputDescription:
    "One Korean Markdown report per person, plus any batch-level warnings.",
  configuration: [
    { label: "Trigger", value: "Manual" },
    { label: "Default timezone", value: "Asia/Seoul" },
    { label: "Reporting window", value: "Monday to Monday" },
    { label: "Maximum concurrency", value: "4 reports" }
  ],
  limitations: [
    "Uses a deterministic mock activity source",
    "Scheduling and delivery are not connected",
    "Run history is not persisted",
    "Authentication is not configured"
  ],
  recentRuns: [
    {
      id: "preview-run-2026-08-03",
      status: "completed",
      trigger: "Manual preview",
      startedAt: "2026-08-12T18:05:00+09:00",
      duration: "12 sec",
      resultSummary: "Prepared 3 personal reports",
      warningCount: 0
    },
    {
      id: "preview-run-2026-07-27",
      status: "completed",
      trigger: "Manual preview",
      startedAt: "2026-08-12T17:42:00+09:00",
      duration: "9 sec",
      resultSummary: "Prepared 3 reports using fallback narratives",
      warningCount: 1
    }
  ]
};

export const agentCatalogClient = {
  async listAgents(): Promise<AgentDefinition[]> {
    return normalizeAgentCatalog([weeklyReporterRecord]);
  }
};

export function normalizeAgentCatalog(
  records: AgentCatalogRecord[]
): AgentDefinition[] {
  return records.map((record) => ({
    ...record,
    readiness: normalizeReadiness(record.readiness),
    capabilities: [...record.capabilities],
    inputs: record.inputs.map((input) => ({ ...input })),
    configuration: record.configuration.map((item) => ({ ...item })),
    limitations: [...record.limitations],
    recentRuns: record.recentRuns.map((run) => ({
      ...run,
      status: normalizeRunStatus(run.status)
    }))
  }));
}

function normalizeReadiness(value: string): AgentReadiness {
  if (
    value === "ready" ||
    value === "degraded" ||
    value === "offline" ||
    value === "draft"
  ) {
    return value;
  }
  return "draft";
}

function normalizeRunStatus(value: string): AgentRunStatus {
  if (
    value === "queued" ||
    value === "running" ||
    value === "completed" ||
    value === "failed" ||
    value === "cancelled"
  ) {
    return value;
  }
  return "failed";
}
