import type {
  AgentSummary,
  SystemHealth
} from "../types/domain";

export const systemHealth: SystemHealth = {
  status: "healthy",
  backendVersion: "0.1.0",
  database: "mocked",
  eventStream: "ready",
  lastCheckedAt: "2026-07-03T09:30:00+09:00"
};

export const agents: AgentSummary[] = [
  {
    id: "agent-audit",
    name: "Audit",
    role: "Integration verifier",
    availability: "blocked",
    health: "degraded",
    currentMission: "Validate Nextcloud integration path",
    nextAction: "Await scoped connectivity approval",
    blockers: ["Human approval required"],
    queueDepth: 2,
    reliability: 91,
    lastHeartbeatAt: "2026-07-03T09:27:00+09:00",
    capabilities: ["API checks", "Evidence collection"],
    permissionProfile: ["Read-only network via backend"]
  },
  {
    id: "agent-planner",
    name: "Planner",
    role: "Mission planner",
    availability: "busy",
    health: "healthy",
    currentMission: "Draft mission control operating model",
    nextAction: "Rank open decisions by operator impact",
    blockers: [],
    queueDepth: 4,
    reliability: 96,
    lastHeartbeatAt: "2026-07-03T09:28:00+09:00",
    capabilities: ["Task planning", "Risk summary"],
    permissionProfile: ["No external actions"]
  },
  {
    id: "agent-guardian",
    name: "Guardian",
    role: "Policy and risk guard",
    availability: "busy",
    health: "healthy",
    currentMission: "Define stage-one approval policy",
    nextAction: "Suggest approval evidence thresholds",
    blockers: [],
    queueDepth: 1,
    reliability: 98,
    lastHeartbeatAt: "2026-07-03T09:29:00+09:00",
    capabilities: ["Policy checks", "Risk scoring"],
    permissionProfile: ["Policy advisory only"]
  },
  {
    id: "agent-docs",
    name: "Docs",
    role: "Documentation maintainer",
    availability: "available",
    health: "healthy",
    currentMission: null,
    nextAction: "Ready for documentation task",
    blockers: [],
    queueDepth: 0,
    reliability: 94,
    lastHeartbeatAt: "2026-07-03T09:25:00+09:00",
    capabilities: ["Runbooks", "Architecture notes"],
    permissionProfile: ["Documentation changes only"]
  }
];
