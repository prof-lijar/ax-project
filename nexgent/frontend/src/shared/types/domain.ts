export type HealthStatus = "healthy" | "degraded";
export type ServiceStatus = "ready" | "mocked" | "degraded";
export type AgentAvailability = "available" | "busy" | "blocked" | "paused";
export type AgentHealth = "healthy" | "degraded" | "offline";

export interface SystemHealth {
  status: HealthStatus;
  backendVersion: string;
  database: ServiceStatus;
  eventStream: ServiceStatus;
  lastCheckedAt: string;
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

export interface CommandError {
  code: string;
  message: string;
  recoveryAction?: string | null;
  correlationId?: string;
}
