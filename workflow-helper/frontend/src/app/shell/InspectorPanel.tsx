import { AlertTriangle, Bot, CheckSquare, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";

import {
  useActivity,
  useAgents,
  useApprovals,
  useSystemHealth,
  useTasks,
  useWorkspace
} from "../../shared/api/queries";
import { RiskBadge, StatusBadge } from "../../shared/components/Badge";
import { ProgressBar } from "../../shared/components/ProgressBar";
import { useUiStore } from "../../shared/state/useUiStore";
import { formatClock } from "../../shared/time/format";
import styles from "./InspectorPanel.module.css";

export function InspectorPanel() {
  const target = useUiStore((state) => state.inspectorTarget);
  const { data: workspace } = useWorkspace();
  const { data: health } = useSystemHealth();
  const { data: tasks = [] } = useTasks();
  const { data: approvals = [] } = useApprovals();
  const { data: agents = [] } = useAgents();
  const { data: activity = [] } = useActivity();

  if (target?.type === "approval") {
    const approval = approvals.find((item) => item.id === target.id);
    const agent = agents.find((item) => item.id === approval?.agentId);
    const task = tasks.find((item) => item.id === approval?.taskId);

    if (approval) {
      return (
        <section className={styles.panel}>
          <Header icon={<ShieldCheck size={18} />} title="Approval" />
          <div className={styles.stack}>
            <RiskBadge risk={approval.riskLevel} />
            <h2>{approval.requestedAction}</h2>
            <p>{approval.scope}</p>
            <Meta label="Requested by" value={agent?.name ?? approval.agentId} />
            <Meta label="Task" value={task?.title ?? approval.taskId} />
            <Meta label="Expires" value={formatClock(approval.expiresAt)} />
          </div>
          <InspectorList title="Evidence" items={approval.evidence} />
          <InspectorList title="Alternatives" items={approval.alternatives} />
          <div className={styles.decisionRow}>
            <button className={styles.approveButton} type="button">
              Approve once
            </button>
            <button className={styles.rejectButton} type="button">
              Reject
            </button>
          </div>
        </section>
      );
    }
  }

  if (target?.type === "task") {
    const task = tasks.find((item) => item.id === target.id);

    if (task) {
      return (
        <section className={styles.panel}>
          <Header icon={<CheckSquare size={18} />} title="Task" />
          <div className={styles.stack}>
            <div className={styles.badgeRow}>
              <StatusBadge status={task.status} />
              <RiskBadge risk={task.riskLevel} />
            </div>
            <h2>{task.title}</h2>
            <p>{task.goal}</p>
            <ProgressBar value={task.progress} />
            <Meta label="Owner" value={task.ownerName} />
            <Meta label="Priority" value={task.priority.toUpperCase()} />
            <Meta label="Next action" value={task.nextAction} />
          </div>
        </section>
      );
    }
  }

  if (target?.type === "agent") {
    const agent = agents.find((item) => item.id === target.id);

    if (agent) {
      return (
        <section className={styles.panel}>
          <Header icon={<Bot size={18} />} title="Co-worker" />
          <div className={styles.stack}>
            <div className={styles.badgeRow}>
              <StatusBadge status={agent.availability} />
              <StatusBadge status={agent.health} />
            </div>
            <h2>{agent.name}</h2>
            <p>{agent.role}</p>
            <Meta label="Focus" value={agent.currentMission ?? "Idle"} />
            <Meta label="Next action" value={agent.nextAction} />
            <Meta label="Reliability" value={`${agent.reliability}%`} />
          </div>
          <InspectorList title="Capabilities" items={agent.capabilities} />
          <InspectorList title="Permissions" items={agent.permissionProfile} />
        </section>
      );
    }
  }

  if (target?.type === "event") {
    const event = activity.find((item) => item.id === target.id);

    if (event) {
      return (
        <section className={styles.panel}>
          <Header icon={<AlertTriangle size={18} />} title="Event" />
          <div className={styles.stack}>
            <StatusBadge status={event.severity} />
            <h2>{event.title}</h2>
            <p>{event.description}</p>
            <Meta label="Kind" value={event.kind} />
            <Meta label="Time" value={formatClock(event.createdAt)} />
          </div>
        </section>
      );
    }
  }

  return (
    <section className={styles.panel}>
      <Header icon={<ShieldCheck size={18} />} title="System" />
      <div className={styles.stack}>
        <h2>{workspace?.name ?? "AX Project"}</h2>
        <div className={styles.badgeRow}>
          <StatusBadge status={health?.status ?? "healthy"} />
          <span className={styles.mode}>{workspace?.policyMode ?? "guarded"}</span>
        </div>
        <Meta label="Active missions" value={`${workspace?.activeMissions ?? 0}`} />
        <Meta
          label="Pending approvals"
          value={`${workspace?.pendingApprovals ?? 0}`}
        />
        <Meta
          label="Degraded agents"
          value={`${workspace?.degradedAgents ?? 0}`}
        />
        <Meta label="Database" value={health?.database ?? "mocked"} />
        <Meta label="Event stream" value={health?.eventStream ?? "ready"} />
      </div>
    </section>
  );
}

function Header({ icon, title }: { icon: ReactNode; title: string }) {
  return (
    <header className={styles.header}>
      <span>{icon}</span>
      <strong>{title}</strong>
    </header>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.meta}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function InspectorList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) {
    return null;
  }

  return (
    <section className={styles.listBlock}>
      <h3>{title}</h3>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}
