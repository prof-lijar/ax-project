import styles from "./ProgressBar.module.css";

export function ProgressBar({ value }: { value: number }) {
  const width = Math.min(100, Math.max(0, value));
  const bucket = Math.round(width / 5) * 5;

  return (
    <div
      className={styles.track}
      aria-label={`Progress ${width}%`}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={width}
    >
      <span className={`${styles.fill} ${styles[`w${bucket}`]}`} />
    </div>
  );
}
