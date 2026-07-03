import { useActivity } from "../../shared/api/queries";
import { StatusBadge } from "../../shared/components/Badge";
import { useUiStore } from "../../shared/state/useUiStore";
import { formatClock } from "../../shared/time/format";
import styles from "../FeaturePages.module.css";

export function ActivityPage() {
  const { data: activity = [] } = useActivity();
  const search = useUiStore((state) => state.search).toLowerCase();
  const setInspectorTarget = useUiStore((state) => state.setInspectorTarget);
  const visibleActivity = activity.filter((event) =>
    [event.title, event.description, event.kind, event.severity]
      .join(" ")
      .toLowerCase()
      .includes(search)
  );

  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1>Activity</h1>
          <p>{visibleActivity.length} recent events</p>
        </div>
      </header>

      <div className={styles.table}>
        <div className={`${styles.tableHeader} ${styles.tableHeaderActivity}`}>
          <span>Time</span>
          <span>Event</span>
          <span>Severity</span>
          <span>Kind</span>
        </div>
        {visibleActivity.map((event) => (
          <button
            className={styles.activityRow}
            key={event.id}
            onClick={() => setInspectorTarget({ type: "event", id: event.id })}
            type="button"
          >
            <span className={styles.muted}>{formatClock(event.createdAt)}</span>
            <span className={styles.primaryCell}>
              <strong>{event.title}</strong>
              <small>{event.description}</small>
            </span>
            <StatusBadge status={event.severity} />
            <span className={styles.muted}>{event.kind}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
