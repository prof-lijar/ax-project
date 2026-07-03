import {
  AlertCircle,
  ArrowRight,
  Bot,
  CheckCircle2,
  Clock3,
  ShieldCheck
} from "lucide-react";
import type { ReactNode } from "react";

import {
  useActivity,
  useAgents,
  useApprovals,
  useTasks
} from "../../shared/api/queries";
import { RiskBadge, StatusBadge } from "../../shared/components/Badge";
import { ProgressBar } from "../../shared/components/ProgressBar";
import { useUiStore } from "../../shared/state/useUiStore";
import { formatClock, formatRelative } from "../../shared/time/format";
import type {
  ActivityEvent,
  AgentSummary,
  ApprovalRequest,
  TaskSummary
} from "../../shared/types/domain";
import styles from "./MissionControl.module.css";

export function MissionControl() {
  const search = useUiStore((state) => state.search);
  const setActiveSection = useUiStore((state) => state.setActiveSection);
  const { data: tasks = [] } = useTasks();
  const { data: approvals = [] } = useApprovals();
  const { data: agents = [] } = useAgents();
  const { data: activity = [] } = useActivity();

  const query = search.trim().toLowerCase();
  const visibleTasks = filterTasks(tasks, query);
  const visibleApprovals = filterApprovals(approvals, query);
  const visibleAgents = filterAgents(agents, query);
  const visibleActivity = filterActivity(activity, query);
  const primaryDecision = visibleApprovals[0] ?? null;
  const currentWork = visibleTasks
    .filter((task) => task.status !== "complete")
    .slice(0, 3);
  const recentActivity = visibleActivity.slice(0, 4);

  return (
    <div className={styles.page}>
      <header className={styles.hero}>
        <div>
          <span className={styles.eyebrow}>Today</span>
          <h1>Keep the work moving.</h1>
          <p>
            Review the next decision, see what the team is focused on, and step
            in only where it matters.
          </p>
        </div>
        <div className={styles.quickStatus}>
          <StatusPill icon={<ShieldCheck size={16} />} value={visibleApprovals.length} label="decisions" />
          <StatusPill icon={<Bot size={16} />} value={visibleAgents.length} label="co-workers" />
          <StatusPill icon={<Clock3 size={16} />} value={currentWork.length} label="active" />
        </div>
      </header>

      <section className={styles.workspace}>
        <div className={styles.leftColumn}>
          <DecisionPanel
            approval={primaryDecision}
            agent={agents.find((agent) => agent.id === primaryDecision?.agentId)}
          />

          <section className={styles.section}>
            <SectionHeader
              title="Current work"
              actionLabel="View tasks"
              onAction={() => setActiveSection("tasks")}
            />
            <div className={styles.workList}>
              {currentWork.map((task) => (
                <WorkItem
                  key={task.id}
                  task={task}
                />
              ))}
            </div>
          </section>
        </div>

        <div className={styles.rightColumn}>
          <section className={styles.section}>
            <SectionHeader
              title="Co-workers"
              actionLabel="View team"
              onAction={() => setActiveSection("agents")}
            />
            <div className={styles.coworkerRoom}>
              {visibleAgents.map((agent) => (
                <CoworkerCard
                  key={agent.id}
                  agent={agent}
                />
              ))}
            </div>
          </section>

          <section className={styles.section}>
            <SectionHeader
              title="Recent"
              actionLabel="View activity"
              onAction={() => setActiveSection("activity")}
            />
            <div className={styles.activityFeed}>
              {recentActivity.map((event) => (
                <ActivityNote
                  event={event}
                  key={event.id}
                />
              ))}
            </div>
          </section>
        </div>
      </section>
    </div>
  );
}

function StatusPill({
  icon,
  value,
  label
}: {
  icon: ReactNode;
  value: number;
  label: string;
}) {
  return (
    <span className={styles.statusPill}>
      {icon}
      <strong>{value}</strong>
      <span>{label}</span>
    </span>
  );
}

function SectionHeader({
  title,
  actionLabel,
  onAction
}: {
  title: string;
  actionLabel: string;
  onAction: () => void;
}) {
  return (
    <header className={styles.sectionHeader}>
      <h2>{title}</h2>
      <button type="button" onClick={onAction}>
        {actionLabel}
        <ArrowRight size={15} />
      </button>
    </header>
  );
}

function DecisionPanel({
  approval,
  agent
}: {
  approval: ApprovalRequest | null;
  agent?: AgentSummary;
}) {
  if (!approval) {
    return (
      <section className={styles.decisionEmpty}>
        <CheckCircle2 size={22} />
        <div>
          <h2>No decision needed</h2>
          <p>The team can keep working without your input right now.</p>
        </div>
      </section>
    );
  }

  return (
    <section className={styles.decisionPanel}>
      <span className={styles.decisionTopline}>
        <span>
          <AlertCircle size={18} />
          Decision needed
        </span>
        <RiskBadge risk={approval.riskLevel} />
      </span>
      <strong>{approval.requestedAction}</strong>
      <p>{approval.scope}</p>
      <span className={styles.decisionMeta}>
        <span>{agent?.name ?? approval.agentId}</span>
        <span>{formatRelative(approval.createdAt)}</span>
      </span>
    </section>
  );
}

function WorkItem({ task }: { task: TaskSummary }) {
  return (
    <article className={styles.workItem}>
      <span className={styles.workMain}>
        <strong>{task.title}</strong>
        <small>{task.nextAction}</small>
      </span>
      <span className={styles.workMeta}>
        <StatusBadge status={task.status} />
        <span>{task.ownerName}</span>
      </span>
      <ProgressBar value={task.progress} />
    </article>
  );
}

function CoworkerCard({ agent }: { agent: AgentSummary }) {
  return (
    <article className={styles.coworkerCard}>
      <span className={styles.avatar} aria-hidden>
        {initials(agent.name)}
      </span>
      <span className={styles.coworkerCopy}>
        <strong>{agent.name}</strong>
        <small>{agent.role}</small>
      </span>
      <span className={`${styles.presence} ${styles[agent.availability]}`}>
        {agent.availability}
      </span>
      <span className={styles.focus}>
        {agent.currentMission ?? agent.nextAction}
      </span>
    </article>
  );
}

function ActivityNote({ event }: { event: ActivityEvent }) {
  return (
    <article className={styles.activityNote}>
      <span>{formatClock(event.createdAt)}</span>
      <strong>{event.title}</strong>
      <small>{event.description}</small>
    </article>
  );
}

function initials(name: string) {
  return name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

function filterTasks(tasks: TaskSummary[], query: string) {
  if (!query) {
    return tasks;
  }

  return tasks.filter((task) =>
    [task.title, task.goal, task.ownerName, task.nextAction]
      .join(" ")
      .toLowerCase()
      .includes(query)
  );
}

function filterApprovals(approvals: ApprovalRequest[], query: string) {
  if (!query) {
    return approvals;
  }

  return approvals.filter((approval) =>
    [approval.requestedAction, approval.scope, approval.riskLevel]
      .join(" ")
      .toLowerCase()
      .includes(query)
  );
}

function filterAgents(agents: AgentSummary[], query: string) {
  if (!query) {
    return agents;
  }

  return agents.filter((agent) =>
    [agent.name, agent.role, agent.currentMission, agent.nextAction]
      .join(" ")
      .toLowerCase()
      .includes(query)
  );
}

function filterActivity(events: ActivityEvent[], query: string) {
  if (!query) {
    return events;
  }

  return events.filter((event) =>
    [event.title, event.description, event.kind]
      .join(" ")
      .toLowerCase()
      .includes(query)
  );
}
