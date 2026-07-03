import type {
  ActivitySeverity,
  AgentAvailability,
  AgentHealth,
  RiskLevel,
  TaskStatus
} from "../types/domain";
import styles from "./Badge.module.css";

type BadgeTone = "neutral" | "blue" | "green" | "amber" | "red";

interface BadgeProps {
  children: string;
  tone?: BadgeTone;
}

export function Badge({ children, tone = "neutral" }: BadgeProps) {
  return <span className={`${styles.badge} ${styles[tone]}`}>{children}</span>;
}

export function RiskBadge({ risk }: { risk: RiskLevel }) {
  const tone: BadgeTone =
    risk === "critical" || risk === "high"
      ? "red"
      : risk === "medium"
        ? "amber"
        : "green";

  return <Badge tone={tone}>{risk}</Badge>;
}

export function StatusBadge({
  status
}: {
  status: TaskStatus | AgentAvailability | AgentHealth | ActivitySeverity;
}) {
  const tone: BadgeTone =
    status === "complete" ||
    status === "available" ||
    status === "healthy" ||
    status === "success"
      ? "green"
      : status === "running" ||
          status === "busy" ||
          status === "info"
        ? "blue"
        : status === "blocked" ||
            status === "degraded" ||
            status === "critical" ||
            status === "offline"
          ? "red"
          : "amber";

  return <Badge tone={tone}>{status}</Badge>;
}
