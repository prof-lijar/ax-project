use super::models::{
    ActivityEvent, ActivityKind, ActivitySeverity, AgentAvailability, AgentHealth, AgentSummary,
    ApprovalRequest, HealthStatus, PolicyMode, Priority, RiskLevel, ServiceStatus, SystemHealth,
    TaskStatus, TaskSummary, WorkspaceOverview,
};

pub fn workspace() -> WorkspaceOverview {
    WorkspaceOverview {
        name: "AX Project".into(),
        operator: "Local operator".into(),
        policy_mode: PolicyMode::Guarded,
        emergency_pause: false,
        active_missions: 4,
        pending_approvals: 3,
        degraded_agents: 1,
    }
}

pub fn system_health() -> SystemHealth {
    SystemHealth {
        status: HealthStatus::Healthy,
        backend_version: env!("CARGO_PKG_VERSION").into(),
        database: ServiceStatus::Mocked,
        event_stream: ServiceStatus::Ready,
        last_checked_at: "2026-07-03T09:30:00+09:00".into(),
    }
}

pub fn tasks() -> Vec<TaskSummary> {
    vec![
        TaskSummary {
            id: "task-nextcloud-001".into(),
            title: "Validate Nextcloud integration path".into(),
            goal: "Confirm local API connectivity, credentials flow, and certificate handling before file actions are enabled.".into(),
            status: TaskStatus::Blocked,
            priority: Priority::P0,
            owner_agent_id: Some("agent-audit".into()),
            owner_name: "Audit".into(),
            risk_level: RiskLevel::High,
            last_activity_at: "2026-07-03T09:21:00+09:00".into(),
            next_action: "Waiting for approval to run scoped connectivity check".into(),
            progress: 42,
        },
        TaskSummary {
            id: "task-ui-002".into(),
            title: "Draft mission control operating model".into(),
            goal: "Turn product requirements into the first operator workflow with approvals, agent health, and activity trace.".into(),
            status: TaskStatus::Running,
            priority: Priority::P1,
            owner_agent_id: Some("agent-planner".into()),
            owner_name: "Planner".into(),
            risk_level: RiskLevel::Medium,
            last_activity_at: "2026-07-03T09:18:00+09:00".into(),
            next_action: "Summarize open decisions for operator review".into(),
            progress: 64,
        },
        TaskSummary {
            id: "task-policy-003".into(),
            title: "Define stage-one approval policy".into(),
            goal: "Ensure destructive or external actions require auditable human approval during the local build phase.".into(),
            status: TaskStatus::Waiting,
            priority: Priority::P1,
            owner_agent_id: Some("agent-guardian".into()),
            owner_name: "Guardian".into(),
            risk_level: RiskLevel::High,
            last_activity_at: "2026-07-03T08:57:00+09:00".into(),
            next_action: "Collect evidence threshold examples".into(),
            progress: 51,
        },
        TaskSummary {
            id: "task-docs-004".into(),
            title: "Prepare implementation handoff".into(),
            goal: "Keep the architecture, runbook, and setup docs aligned with the Tauri desktop app.".into(),
            status: TaskStatus::Complete,
            priority: Priority::P2,
            owner_agent_id: Some("agent-docs".into()),
            owner_name: "Docs".into(),
            risk_level: RiskLevel::Low,
            last_activity_at: "2026-07-03T08:45:00+09:00".into(),
            next_action: "No action required".into(),
            progress: 100,
        },
    ]
}

pub fn approvals() -> Vec<ApprovalRequest> {
    vec![
        ApprovalRequest {
            id: "approval-nc-health".into(),
            task_id: "task-nextcloud-001".into(),
            agent_id: "agent-audit".into(),
            requested_action: "Call local backend health endpoint for Nextcloud connection".into(),
            scope: "Read-only request to 127.0.0.1 backend, no file changes".into(),
            risk_level: RiskLevel::High,
            evidence: vec![
                "Backend exposes local-only FastAPI routes for Nextcloud checks.".into(),
                "No shell, process, or filesystem Tauri plugins are enabled.".into(),
                "Credentials remain outside frontend state.".into(),
            ],
            alternatives: vec![
                "Ask operator to run curl manually and paste result.".into(),
                "Defer integration validation until credential storage is implemented.".into(),
            ],
            expires_at: "2026-07-03T10:00:00+09:00".into(),
            created_at: "2026-07-03T09:04:00+09:00".into(),
        },
        ApprovalRequest {
            id: "approval-policy-bundle".into(),
            task_id: "task-policy-003".into(),
            agent_id: "agent-guardian".into(),
            requested_action: "Bundle repeated low-risk evidence requests for this task".into(),
            scope: "Policy suggestion only, valid for current task for 30 minutes".into(),
            risk_level: RiskLevel::Medium,
            evidence: vec![
                "Three similar approval requests were generated by the same agent.".into(),
                "All requests are read-only and target product documentation.".into(),
            ],
            alternatives: vec![
                "Approve each request separately.".into(),
                "Ask agent to reduce the plan scope.".into(),
            ],
            expires_at: "2026-07-03T09:50:00+09:00".into(),
            created_at: "2026-07-03T09:12:00+09:00".into(),
        },
        ApprovalRequest {
            id: "approval-doc-update".into(),
            task_id: "task-docs-004".into(),
            agent_id: "agent-docs".into(),
            requested_action: "Update frontend runbook with desktop setup notes".into(),
            scope: "Write documentation under docs/ only".into(),
            risk_level: RiskLevel::Low,
            evidence: vec![
                "The requested change is documentation-only.".into(),
                "The runbook currently lacks desktop setup commands.".into(),
            ],
            alternatives: vec!["Leave setup notes in frontend README only.".into()],
            expires_at: "2026-07-03T11:00:00+09:00".into(),
            created_at: "2026-07-03T08:38:00+09:00".into(),
        },
    ]
}

pub fn agents() -> Vec<AgentSummary> {
    vec![
        AgentSummary {
            id: "agent-audit".into(),
            name: "Audit".into(),
            role: "Integration verifier".into(),
            availability: AgentAvailability::Blocked,
            health: AgentHealth::Degraded,
            current_mission: Some("Validate Nextcloud integration path".into()),
            next_action: "Await scoped connectivity approval".into(),
            blockers: vec!["Human approval required".into()],
            queue_depth: 2,
            reliability: 91,
            last_heartbeat_at: "2026-07-03T09:27:00+09:00".into(),
            capabilities: vec!["API checks".into(), "Evidence collection".into()],
            permission_profile: vec!["Read-only network via backend".into()],
        },
        AgentSummary {
            id: "agent-planner".into(),
            name: "Planner".into(),
            role: "Mission planner".into(),
            availability: AgentAvailability::Busy,
            health: AgentHealth::Healthy,
            current_mission: Some("Draft mission control operating model".into()),
            next_action: "Rank open decisions by operator impact".into(),
            blockers: vec![],
            queue_depth: 4,
            reliability: 96,
            last_heartbeat_at: "2026-07-03T09:28:00+09:00".into(),
            capabilities: vec!["Task planning".into(), "Risk summary".into()],
            permission_profile: vec!["No external actions".into()],
        },
        AgentSummary {
            id: "agent-guardian".into(),
            name: "Guardian".into(),
            role: "Policy and risk guard".into(),
            availability: AgentAvailability::Busy,
            health: AgentHealth::Healthy,
            current_mission: Some("Define stage-one approval policy".into()),
            next_action: "Suggest approval evidence thresholds".into(),
            blockers: vec![],
            queue_depth: 1,
            reliability: 98,
            last_heartbeat_at: "2026-07-03T09:29:00+09:00".into(),
            capabilities: vec!["Policy checks".into(), "Risk scoring".into()],
            permission_profile: vec!["Policy advisory only".into()],
        },
        AgentSummary {
            id: "agent-docs".into(),
            name: "Docs".into(),
            role: "Documentation maintainer".into(),
            availability: AgentAvailability::Available,
            health: AgentHealth::Healthy,
            current_mission: None,
            next_action: "Ready for documentation task".into(),
            blockers: vec![],
            queue_depth: 0,
            reliability: 94,
            last_heartbeat_at: "2026-07-03T09:25:00+09:00".into(),
            capabilities: vec!["Runbooks".into(), "Architecture notes".into()],
            permission_profile: vec!["Documentation changes only".into()],
        },
    ]
}

pub fn activity() -> Vec<ActivityEvent> {
    vec![
        ActivityEvent {
            id: "evt-approval-001".into(),
            kind: ActivityKind::ApprovalRequested,
            title: "Approval requested".into(),
            description: "Audit requested a scoped local connectivity check.".into(),
            severity: ActivitySeverity::Warning,
            task_id: Some("task-nextcloud-001".into()),
            agent_id: Some("agent-audit".into()),
            created_at: "2026-07-03T09:21:00+09:00".into(),
        },
        ActivityEvent {
            id: "evt-heartbeat-002".into(),
            kind: ActivityKind::AgentHeartbeat,
            title: "Co-worker checked in".into(),
            description: "Guardian reported healthy status.".into(),
            severity: ActivitySeverity::Info,
            task_id: Some("task-policy-003".into()),
            agent_id: Some("agent-guardian".into()),
            created_at: "2026-07-03T09:19:00+09:00".into(),
        },
        ActivityEvent {
            id: "evt-task-003".into(),
            kind: ActivityKind::TaskUpdated,
            title: "Mission progressed".into(),
            description: "Planner completed the initial screen hierarchy.".into(),
            severity: ActivitySeverity::Success,
            task_id: Some("task-ui-002".into()),
            agent_id: Some("agent-planner".into()),
            created_at: "2026-07-03T09:18:00+09:00".into(),
        },
        ActivityEvent {
            id: "evt-warning-004".into(),
            kind: ActivityKind::SystemWarning,
            title: "Persistence not configured".into(),
            description: "SQLite is planned but this build is using command-backed sample data.".into(),
            severity: ActivitySeverity::Warning,
            task_id: None,
            agent_id: None,
            created_at: "2026-07-03T09:00:00+09:00".into(),
        },
    ]
}
