export type HealthStatus = "healthy" | "degraded";
export type ServiceStatus = "ready" | "mocked" | "degraded";
export type TaskStatus = "running" | "blocked" | "waiting" | "complete";
export type Priority = "p0" | "p1" | "p2" | "p3";
export type RiskLevel = "low" | "medium" | "high" | "critical";
export type AgentAvailability = "available" | "busy" | "blocked" | "paused";
export type AgentHealth = "healthy" | "degraded" | "offline";
export type ActivitySeverity = "info" | "success" | "warning" | "critical";
export type ActivityKind =
  | "taskCreated"
  | "taskUpdated"
  | "agentHeartbeat"
  | "approvalRequested"
  | "approvalDecided"
  | "systemWarning";

export interface SystemHealth {
  status: HealthStatus;
  backendVersion: string;
  database: ServiceStatus;
  eventStream: ServiceStatus;
  lastCheckedAt: string;
}

export interface TaskSummary {
  id: string;
  title: string;
  goal: string;
  status: TaskStatus;
  priority: Priority;
  ownerAgentId: string | null;
  ownerName: string;
  riskLevel: RiskLevel;
  lastActivityAt: string;
  nextAction: string;
  progress: number;
}

export interface ApprovalRequest {
  id: string;
  taskId: string;
  agentId: string;
  requestedAction: string;
  scope: string;
  riskLevel: RiskLevel;
  evidence: string[];
  alternatives: string[];
  expiresAt: string;
  createdAt: string;
}

export interface AgentSummary {
  id: string;
  name: string;
  role: string;
  availability: AgentAvailability;
  health: AgentHealth;
  currentMission: string | null;
  nextAction: string;
  blockers: string[];
  queueDepth: number;
  reliability: number;
  lastHeartbeatAt: string;
  capabilities: string[];
  permissionProfile: string[];
}

export interface ActivityEvent {
  id: string;
  kind: ActivityKind;
  title: string;
  description: string;
  severity: ActivitySeverity;
  taskId: string | null;
  agentId: string | null;
  createdAt: string;
}

export interface CommandError {
  code: string;
  message: string;
  recoveryAction?: string | null;
  correlationId?: string;
}
