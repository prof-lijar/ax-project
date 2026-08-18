import type {
  AgentDefinition,
  AgentReadiness,
  AgentRunStatus
} from "../types/agents";

export const WEEKLY_REPORTER_AGENT_ID = "1";

export interface AgentCatalogRecord extends Omit<AgentDefinition, "readiness" | "recentRuns"> {
  readiness: string;
  recentRuns: Array<Omit<AgentDefinition["recentRuns"][number], "status"> & {
    status: string;
  }>;
}

const weeklyReporterRecord: AgentCatalogRecord = {
  id: WEEKLY_REPORTER_AGENT_ID,
  name: "Weekly Reporter",
  role: "Ward risk reporting collaborator",
  description:
    "Compares current and previous danger-day totals for a bounded ward subset, then prepares grounded Korean Markdown reports.",
  graphId: "ansimk_weekly_reporter",
  readiness: "ready",
  currentWork: "Ready to query ward risk data through the database MCP",
  runtimeLabel: "LangGraph",
  lastObservedAt: "2026-08-12T18:07:00+09:00",
  observationMode: "live",
  capabilities: [
    "Ward danger-day comparison",
    "Database MCP integration",
    "Per-ward report generation",
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
    "One Korean Markdown risk report per ward, plus any batch-level warnings.",
  configuration: [
    { label: "Trigger", value: "Manual" },
    { label: "Default timezone", value: "Asia/Seoul" },
    { label: "Reporting window", value: "Monday to Monday" },
    { label: "Data source", value: "ansimk.analysis_warddangerdaily via db MCP" },
    { label: "Ward limit", value: "First 3 complete wards" }
  ],
  limitations: [
    "Prototype processes a bounded subset of three wards",
    "Danger-day semantics require domain validation",
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
      resultSummary: "Prepared 3 ward danger-day reports",
      warningCount: 0
    },
    {
      id: "preview-run-2026-07-27",
      status: "completed",
      trigger: "Manual preview",
      startedAt: "2026-08-12T17:42:00+09:00",
      duration: "9 sec",
      resultSummary: "Prepared 3 ward reports using fallback narratives",
      warningCount: 1
    }
  ]
};

const dataAnalystRecord: AgentCatalogRecord = {
  id: "2",
  name: "Data Analyst",
  role: "Business data collaborator",
  description:
    "Explores preview business datasets, identifies meaningful trends, and prepares concise findings for internal decisions.",
  graphId: "preview_data_analyst",
  readiness: "ready",
  currentWork: "Reviewing mock customer-retention trends for the preview workspace",
  runtimeLabel: "LangGraph Preview",
  lastObservedAt: "2026-08-14T10:18:00+09:00",
  observationMode: "preview",
  capabilities: [
    "Exploratory data analysis",
    "Trend and anomaly detection",
    "Metric definition review",
    "Decision-ready summary generation"
  ],
  inputs: [
    {
      name: "dataset_reference",
      description: "Mock dataset identifier available in the preview workspace",
      required: true
    },
    {
      name: "analysis_question",
      description: "Business question to investigate",
      required: true
    },
    {
      name: "comparison_period",
      description: "Optional preview period used for trend comparison",
      required: false
    }
  ],
  outputDescription:
    "A preview analysis summary with key metrics, notable trends, and suggested follow-up questions.",
  configuration: [
    { label: "Data source", value: "Mock analytics warehouse" },
    { label: "Trigger", value: "Manual preview" },
    { label: "Default lookback", value: "90 days" },
    { label: "Output format", value: "Markdown brief" }
  ],
  limitations: [
    "Uses generated preview datasets only",
    "Does not access production analytics systems",
    "Findings are not suitable for external reporting"
  ],
  recentRuns: [
    {
      id: "preview-data-run-2026-08-14",
      status: "completed",
      trigger: "Manual preview",
      startedAt: "2026-08-14T10:12:00+09:00",
      duration: "42 sec",
      resultSummary: "Summarized 4 retention trends from mock data",
      warningCount: 0
    },
    {
      id: "preview-data-run-2026-08-13",
      status: "completed",
      trigger: "Catalog preview",
      startedAt: "2026-08-13T16:30:00+09:00",
      duration: "35 sec",
      resultSummary: "Compared mock monthly conversion metrics",
      warningCount: 1
    }
  ]
};

const reportQaRecord: AgentCatalogRecord = {
  id: "3",
  name: "Report QA",
  role: "Report quality reviewer",
  description:
    "Reviews mock internal reports for unsupported claims, inconsistent metrics, and missing context before preview delivery.",
  graphId: "preview_report_qa",
  readiness: "degraded",
  currentWork: "Checking a mock quarterly report while citation validation is limited",
  runtimeLabel: "LangGraph Preview",
  lastObservedAt: "2026-08-14T09:46:00+09:00",
  observationMode: "preview",
  capabilities: [
    "Claim and evidence review",
    "Metric consistency checks",
    "Tone and terminology review",
    "Quality issue prioritization"
  ],
  inputs: [
    {
      name: "report_draft",
      description: "Mock report content to review",
      required: true
    },
    {
      name: "source_bundle",
      description: "Optional preview references supporting the report",
      required: false
    },
    {
      name: "review_profile",
      description: "Internal review checklist to apply",
      required: false
    }
  ],
  outputDescription:
    "A preview QA checklist with severity-ranked findings and suggested report corrections.",
  configuration: [
    { label: "Review mode", value: "Mock internal report" },
    { label: "Severity threshold", value: "Medium" },
    { label: "Citation check", value: "Limited preview" },
    { label: "Trigger", value: "On demand" }
  ],
  limitations: [
    "Citation validation is intentionally degraded in preview",
    "Does not approve reports for publication",
    "Only checks supplied mock reference material"
  ],
  recentRuns: [
    {
      id: "preview-qa-run-2026-08-14",
      status: "completed",
      trigger: "Manual preview",
      startedAt: "2026-08-14T09:38:00+09:00",
      duration: "1 min 08 sec",
      resultSummary: "Flagged 3 mock claims for follow-up",
      warningCount: 2
    },
    {
      id: "preview-qa-run-2026-08-12",
      status: "failed",
      trigger: "Preview workflow",
      startedAt: "2026-08-12T15:20:00+09:00",
      duration: "18 sec",
      resultSummary: "Mock source bundle was incomplete",
      warningCount: 1
    }
  ]
};

const documentAssistantRecord: AgentCatalogRecord = {
  id: "4",
  name: "Document Assistant",
  role: "Internal documentation collaborator",
  description:
    "Drafts and organizes preview internal documents from structured notes, templates, and supplied team context.",
  graphId: "preview_document_assistant",
  readiness: "draft",
  currentWork: "Drafting a mock onboarding guide for catalog layout review",
  runtimeLabel: "Prototype Preview",
  lastObservedAt: "2026-08-13T14:05:00+09:00",
  observationMode: "preview",
  capabilities: [
    "Structured document drafting",
    "Template-based organization",
    "Plain-language rewriting",
    "Action item extraction"
  ],
  inputs: [
    {
      name: "document_goal",
      description: "Purpose of the mock document",
      required: true
    },
    {
      name: "source_notes",
      description: "Preview notes to organize into a draft",
      required: true
    },
    {
      name: "template_name",
      description: "Optional mock template identifier",
      required: false
    }
  ],
  outputDescription:
    "A preview Markdown document with a proposed structure, draft copy, and unresolved questions.",
  configuration: [
    { label: "Lifecycle", value: "Draft prototype" },
    { label: "Default language", value: "English" },
    { label: "Output format", value: "Markdown" },
    { label: "Delivery", value: "Preview only" }
  ],
  limitations: [
    "Draft workflow is not connected to a document repository",
    "Templates are static mock fixtures",
    "Requires human review before reuse"
  ],
  recentRuns: [
    {
      id: "preview-document-run-2026-08-13",
      status: "cancelled",
      trigger: "Prototype test",
      startedAt: "2026-08-13T13:58:00+09:00",
      duration: "24 sec",
      resultSummary: "Stopped after generating a mock outline",
      warningCount: 0
    },
    {
      id: "preview-document-run-2026-08-11",
      status: "completed",
      trigger: "Manual preview",
      startedAt: "2026-08-11T11:10:00+09:00",
      duration: "31 sec",
      resultSummary: "Created a sample onboarding outline",
      warningCount: 1
    }
  ]
};

const databaseAssistantRecord: AgentCatalogRecord = {
  id: "5",
  name: "Database Assistant",
  role: "Data operations collaborator",
  description:
    "Translates internal questions into safe read-only query plans and explains mock database results for preview workflows.",
  graphId: "preview_database_assistant",
  readiness: "offline",
  currentWork: "Offline while the mock database connection is intentionally disabled",
  runtimeLabel: "SQL Agent Preview",
  lastObservedAt: "2026-08-12T17:25:00+09:00",
  observationMode: "preview",
  capabilities: [
    "Read-only query planning",
    "Schema-aware question translation",
    "Query result explanation",
    "Potential data issue identification"
  ],
  inputs: [
    {
      name: "data_question",
      description: "Internal question to answer from preview data",
      required: true
    },
    {
      name: "schema_snapshot",
      description: "Mock schema definition used to plan a query",
      required: true
    },
    {
      name: "row_limit",
      description: "Optional maximum number of preview rows",
      required: false
    }
  ],
  outputDescription:
    "A read-only preview query plan, sample SQL, and plain-language explanation of mock results.",
  configuration: [
    { label: "Access mode", value: "Read-only mock" },
    { label: "Connection", value: "Disabled" },
    { label: "Default row limit", value: "100" },
    { label: "Dialect", value: "PostgreSQL preview" }
  ],
  limitations: [
    "No database connection is active",
    "Never executes write or schema-changing statements",
    "Schema and query results are mock preview data"
  ],
  recentRuns: [
    {
      id: "preview-database-run-2026-08-12",
      status: "failed",
      trigger: "Connection preview",
      startedAt: "2026-08-12T17:24:00+09:00",
      duration: "5 sec",
      resultSummary: "Mock database connection is disabled",
      warningCount: 1
    },
    {
      id: "preview-database-run-2026-08-10",
      status: "completed",
      trigger: "Schema-only preview",
      startedAt: "2026-08-10T10:45:00+09:00",
      duration: "16 sec",
      resultSummary: "Generated SQL from a sample schema without execution",
      warningCount: 0
    }
  ]
};

const riskMonitoringRecord: AgentCatalogRecord = {
  id: "6",
  name: "Risk Monitoring Agent",
  role: "Operational risk collaborator",
  description:
    "Reviews generated preview signals for operational risk patterns and prepares a prioritized internal watchlist.",
  graphId: "preview_risk_monitoring_agent",
  readiness: "degraded",
  currentWork: "Monitoring mock vendor and service signals with delayed preview updates",
  runtimeLabel: "Event Monitor Preview",
  lastObservedAt: "2026-08-14T10:02:00+09:00",
  observationMode: "preview",
  capabilities: [
    "Risk signal classification",
    "Severity and impact assessment",
    "Watchlist prioritization",
    "Escalation summary drafting"
  ],
  inputs: [
    {
      name: "signal_batch",
      description: "Generated preview events to assess",
      required: true
    },
    {
      name: "risk_profile",
      description: "Mock thresholds and categories for classification",
      required: true
    },
    {
      name: "monitoring_window",
      description: "Optional period represented by the signal batch",
      required: false
    }
  ],
  outputDescription:
    "A preview risk watchlist with severity, rationale, and suggested internal follow-up actions.",
  configuration: [
    { label: "Signal source", value: "Generated preview feed" },
    { label: "Refresh interval", value: "15 minutes" },
    { label: "Escalation threshold", value: "High" },
    { label: "Delivery", value: "Catalog preview only" }
  ],
  limitations: [
    "Preview signals are generated and may be delayed",
    "Does not send real alerts or notifications",
    "Risk classifications require human confirmation"
  ],
  recentRuns: [
    {
      id: "preview-risk-run-2026-08-14",
      status: "running",
      trigger: "Scheduled preview",
      startedAt: "2026-08-14T10:00:00+09:00",
      duration: "2 min",
      resultSummary: "Reviewing 12 generated operational signals",
      warningCount: 1
    },
    {
      id: "preview-risk-run-2026-08-13",
      status: "completed",
      trigger: "Scheduled preview",
      startedAt: "2026-08-13T17:00:00+09:00",
      duration: "48 sec",
      resultSummary: "Added 2 mock items to the preview watchlist",
      warningCount: 0
    }
  ]
};

export const agentCatalogClient = {
  async listAgents(): Promise<AgentDefinition[]> {
    return normalizeAgentCatalog([
      weeklyReporterRecord,
      dataAnalystRecord,
      reportQaRecord,
      documentAssistantRecord,
      databaseAssistantRecord,
      riskMonitoringRecord
    ]);
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
