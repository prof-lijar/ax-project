import type {
  AgentDefinition,
  AgentReadiness,
  AgentRunStatus
} from "../types/agents";

export const WEEKLY_REPORTER_AGENT_ID = "1";
export const RAG_CHAT_AGENT_ID = "7";
export const RAG_CHAT_GRAPH_ID = "rag_chat";
export const SCOUT_AGENT_ID = "ansimk_scout_agent";

export interface AgentCatalogRecord extends Omit<AgentDefinition, "readiness" | "recentRuns"> {
  readiness: string | null;
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
  canRunInChat: true,
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
    { label: "Ward limit", value: "Operator-selected, 1–25" }
  ],
  limitations: [
    "Each run processes a bounded subset of up to 25 eligible wards",
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

const ragChatRecord: AgentCatalogRecord = {
  id: RAG_CHAT_AGENT_ID,
  name: "RAG Agent",
  role: "Grounded knowledge assistant",
  description:
    "Answers one-turn questions from the indexed RAG corpus using grounded retrieval and source provenance.",
  graphId: RAG_CHAT_GRAPH_ID,
  canRunInChat: true,
  readiness: null,
  currentWork: null,
  runtimeLabel: "LangGraph",
  lastObservedAt: null,
  observationMode: null,
  capabilities: [
    "Exact vector retrieval",
    "Context-grounded answer generation",
    "Deterministic source provenance",
    "Explicit insufficient-context responses"
  ],
  inputs: [
    {
      name: "question",
      description: "One text-only question to answer from the indexed RAG corpus",
      required: true
    }
  ],
  outputDescription:
    "A streamed grounded Markdown answer followed by retrieval-ordered sources.",
  configuration: [
    { label: "Retrieval", value: "Vector-only exact cosine" },
    { label: "Top-K", value: "5" },
    { label: "Conversation", value: "One turn" },
    { label: "Attachments", value: "Not supported in Phase 1" }
  ],
  limitations: [
    "Answer coverage depends on the content currently indexed in RAG",
    "Does not retain earlier Chat turns",
    "Does not accept attachments",
    "Hybrid retrieval is not enabled"
  ],
  recentRuns: []
};

const scoutAgentRecord: AgentCatalogRecord = {
  id: SCOUT_AGENT_ID,
  name: "AnsimK Scout Agent",
  role: "Web research collaborator",
  description:
    "웹 자료를 검색하고 핵심 내용을 조사·요약해 Markdown 보고서로 생성합니다.",
  graphId: SCOUT_AGENT_ID,
  canRunInChat: false,
  readiness: null,
  currentWork: null,
  runtimeLabel: "Google ADK",
  lastObservedAt: null,
  observationMode: null,
  capabilities: [
    "Public web search",
    "Bounded page extraction",
    "Evidence-grounded Markdown reports"
  ],
  inputs: [
    {
      name: "topic",
      description: "Research topic, from 3 to 500 characters",
      required: true
    },
    {
      name: "keywords",
      description: "Optional comma- or newline-separated research keywords",
      required: false
    },
    {
      name: "additional_instructions",
      description: "Optional per-run or scheduled research guidance",
      required: false
    }
  ],
  outputDescription:
    "A Markdown research report with fetched source URLs and run artifact references.",
  configuration: [
    { label: "Trigger", value: "Run Now · one-time schedule" },
    { label: "Runtime", value: "Standalone Scout + Scheduling APIs" }
  ],
  limitations: [
    "Runs synchronously and may take more than a minute",
    "Run Now history is not retained; scheduled audit history is shown",
    "Recurring/cron scheduling and Slack delivery are not implemented"
  ],
  recentRuns: []
};

export const agentCatalogClient = {
  async listAgents(): Promise<AgentDefinition[]> {
    return normalizeAgentCatalog([
      weeklyReporterRecord,
      ragChatRecord,
      scoutAgentRecord
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

function normalizeReadiness(value: string | null): AgentReadiness | null {
  if (value === null) {
    return null;
  }

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
