import styles from "./Badge.module.css";

type BadgeTone = "neutral" | "blue" | "green" | "amber" | "red";

interface BadgeProps {
  children: string;
  tone?: BadgeTone;
}

export function Badge({ children, tone = "neutral" }: BadgeProps) {
  return <span className={`${styles.badge} ${styles[tone]}`}>{children}</span>;
}
