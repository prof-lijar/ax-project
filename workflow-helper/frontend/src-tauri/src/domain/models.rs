#![allow(dead_code)]

use serde::Serialize;

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct WorkspaceOverview {
    pub name: String,
    pub operator: String,
    pub policy_mode: PolicyMode,
    pub emergency_pause: bool,
    pub active_missions: u8,
    pub pending_approvals: u8,
    pub degraded_agents: u8,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub enum PolicyMode {
    Guarded,
    Strict,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SystemHealth {
    pub status: HealthStatus,
    pub backend_version: String,
    pub database: ServiceStatus,
    pub event_stream: ServiceStatus,
    pub last_checked_at: String,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub enum HealthStatus {
    Healthy,
    Degraded,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub enum ServiceStatus {
    Ready,
    Mocked,
    Degraded,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TaskSummary {
    pub id: String,
    pub title: String,
    pub goal: String,
    pub status: TaskStatus,
    pub priority: Priority,
    pub owner_agent_id: Option<String>,
    pub owner_name: String,
    pub risk_level: RiskLevel,
    pub last_activity_at: String,
    pub next_action: String,
    pub progress: u8,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub enum TaskStatus {
    Running,
    Blocked,
    Waiting,
    Complete,
}

#[derive(Clone, Serialize)]
pub enum Priority {
    #[serde(rename = "p0")]
    P0,
    #[serde(rename = "p1")]
    P1,
    #[serde(rename = "p2")]
    P2,
    #[serde(rename = "p3")]
    P3,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub enum RiskLevel {
    Low,
    Medium,
    High,
    Critical,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ApprovalRequest {
    pub id: String,
    pub task_id: String,
    pub agent_id: String,
    pub requested_action: String,
    pub scope: String,
    pub risk_level: RiskLevel,
    pub evidence: Vec<String>,
    pub alternatives: Vec<String>,
    pub expires_at: String,
    pub created_at: String,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AgentSummary {
    pub id: String,
    pub name: String,
    pub role: String,
    pub availability: AgentAvailability,
    pub health: AgentHealth,
    pub current_mission: Option<String>,
    pub next_action: String,
    pub blockers: Vec<String>,
    pub queue_depth: u8,
    pub reliability: u8,
    pub last_heartbeat_at: String,
    pub capabilities: Vec<String>,
    pub permission_profile: Vec<String>,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub enum AgentAvailability {
    Available,
    Busy,
    Blocked,
    Paused,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub enum AgentHealth {
    Healthy,
    Degraded,
    Offline,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ActivityEvent {
    pub id: String,
    pub kind: ActivityKind,
    pub title: String,
    pub description: String,
    pub severity: ActivitySeverity,
    pub task_id: Option<String>,
    pub agent_id: Option<String>,
    pub created_at: String,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub enum ActivityKind {
    TaskCreated,
    TaskUpdated,
    AgentHeartbeat,
    ApprovalRequested,
    ApprovalDecided,
    SystemWarning,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub enum ActivitySeverity {
    Info,
    Success,
    Warning,
    Critical,
}
