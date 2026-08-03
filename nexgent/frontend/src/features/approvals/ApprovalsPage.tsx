import { useAgents, useApprovals, useTasks } from "../../shared/api/queries";
import { RiskBadge } from "../../shared/components/Badge";
import { useUiStore } from "../../shared/state/useUiStore";
import { formatClock, formatRelative } from "../../shared/time/format";
import styles from "../FeaturePages.module.css";

export function ApprovalsPage() {
  const { data: approvals = [] } = useApprovals();
  const { data: agents = [] } = useAgents();
  const { data: tasks = [] } = useTasks();
  const search = useUiStore((state) => state.search).toLowerCase();
  const visibleApprovals = approvals.filter((approval) =>
    [approval.requestedAction, approval.scope, approval.riskLevel]
      .join(" ")
      .toLowerCase()
      .includes(search)
  );

  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1>Approvals</h1>
          <p>{visibleApprovals.length} pending decisions</p>
        </div>
      </header>

      <div className={styles.table}>
        <div className={`${styles.tableHeader} ${styles.tableHeaderApprovals}`}>
          <span>Risk</span>
          <span>Requested action</span>
          <span>Requested by</span>
          <span>Age</span>
          <span>Expires</span>
        </div>
        {visibleApprovals.map((approval) => {
          const agent = agents.find((item) => item.id === approval.agentId);
          const task = tasks.find((item) => item.id === approval.taskId);

          return (
            <div
              className={styles.approvalRow}
              key={approval.id}
            >
              <RiskBadge risk={approval.riskLevel} />
              <span className={styles.primaryCell}>
                <strong>{approval.requestedAction}</strong>
                <small>{task?.title ?? approval.scope}</small>
              </span>
              <span className={styles.muted}>{agent?.name ?? approval.agentId}</span>
              <span className={styles.muted}>{formatRelative(approval.createdAt)}</span>
              <span className={styles.muted}>{formatClock(approval.expiresAt)}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
