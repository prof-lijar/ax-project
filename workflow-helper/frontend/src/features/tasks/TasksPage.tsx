import { useTasks } from "../../shared/api/queries";
import { RiskBadge, StatusBadge } from "../../shared/components/Badge";
import { ProgressBar } from "../../shared/components/ProgressBar";
import { useUiStore } from "../../shared/state/useUiStore";
import { formatRelative } from "../../shared/time/format";
import styles from "../FeaturePages.module.css";

export function TasksPage() {
  const { data: tasks = [] } = useTasks();
  const search = useUiStore((state) => state.search).toLowerCase();
  const setInspectorTarget = useUiStore((state) => state.setInspectorTarget);
  const visibleTasks = tasks.filter((task) =>
    [task.title, task.goal, task.ownerName, task.status]
      .join(" ")
      .toLowerCase()
      .includes(search)
  );

  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1>Tasks</h1>
          <p>{visibleTasks.length} missions in scope</p>
        </div>
      </header>

      <div className={styles.table}>
        <div className={`${styles.tableHeader} ${styles.tableHeaderTasks}`}>
          <span>Priority</span>
          <span>Task</span>
          <span>Status</span>
          <span>Risk</span>
          <span>Owner</span>
          <span>Last activity</span>
        </div>
        {visibleTasks.map((task) => (
          <button
            className={styles.taskRow}
            key={task.id}
            onClick={() => setInspectorTarget({ type: "task", id: task.id })}
            type="button"
          >
            <span className={styles.priority}>{task.priority.toUpperCase()}</span>
            <span className={styles.primaryCell}>
              <strong>{task.title}</strong>
              <small>{task.nextAction}</small>
              <ProgressBar value={task.progress} />
            </span>
            <StatusBadge status={task.status} />
            <RiskBadge risk={task.riskLevel} />
            <span className={styles.muted}>{task.ownerName}</span>
            <span className={styles.muted}>{formatRelative(task.lastActivityAt)}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
