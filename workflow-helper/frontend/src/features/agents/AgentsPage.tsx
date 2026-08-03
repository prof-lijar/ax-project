import { useAgents } from "../../shared/api/queries";
import { StatusBadge } from "../../shared/components/Badge";
import { useUiStore } from "../../shared/state/useUiStore";
import { formatRelative } from "../../shared/time/format";
import styles from "../FeaturePages.module.css";

export function AgentsPage() {
  const { data: agents = [] } = useAgents();
  const search = useUiStore((state) => state.search).toLowerCase();
  const visibleAgents = agents.filter((agent) =>
    [agent.name, agent.role, agent.currentMission, agent.nextAction]
      .join(" ")
      .toLowerCase()
      .includes(search)
  );

  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1>Co-workers</h1>
          <p>{visibleAgents.length} co-workers available for local work</p>
        </div>
      </header>

      <div className={styles.teamGrid}>
        {visibleAgents.map((agent) => (
          <article
            className={styles.teamCard}
            key={agent.id}
          >
            <span className={styles.teamAvatar}>{initials(agent.name)}</span>
            <span className={styles.primaryCell}>
              <strong>{agent.name}</strong>
              <small>{agent.role}</small>
            </span>
            <span className={styles.badgeGroup}>
              <StatusBadge status={agent.availability} />
              <StatusBadge status={agent.health} />
            </span>
            <span className={styles.teamFocus}>
              {agent.currentMission ?? agent.nextAction}
            </span>
            <span className={styles.muted}>
              Last signal {formatRelative(agent.lastHeartbeatAt)}
            </span>
          </article>
        ))}
      </div>
    </section>
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
