export type AgentReadiness = "ready" | "degraded" | "offline" | "draft";
export type AgentObservationMode = "preview" | "live";
export type AgentRunStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface AgentInputField {
  name: string;
  description: string;
  required: boolean;
}

export interface AgentConfigurationItem {
  label: string;
  value: string;
}

export interface AgentRunSummary {
  id: string;
  status: AgentRunStatus;
  trigger: string;
  startedAt: string;
  duration: string;
  resultSummary: string;
  warningCount: number;
}

export interface AgentDefinition {
  id: string;
  name: string;
  role: string;
  description: string;
  graphId: string;
  readiness: AgentReadiness;
  currentWork: string;
  runtimeLabel: string;
  lastObservedAt: string | null;
  observationMode: AgentObservationMode;
  capabilities: string[];
  inputs: AgentInputField[];
  outputDescription: string;
  configuration: AgentConfigurationItem[];
  limitations: string[];
  recentRuns: AgentRunSummary[];
}
