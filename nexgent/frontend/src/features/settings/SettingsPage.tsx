import { CheckCircle2, LockKeyhole, ShieldCheck } from "lucide-react";

import { Badge } from "../../shared/components/Badge";
import styles from "../FeaturePages.module.css";

const settings = [
  {
    name: "Command boundary",
    detail: "Product commands only",
    status: "enabled",
    icon: ShieldCheck
  },
  {
    name: "Shell access",
    detail: "No shell plugin",
    status: "disabled",
    icon: LockKeyhole
  },
  {
    name: "Filesystem access",
    detail: "No filesystem plugin",
    status: "disabled",
    icon: LockKeyhole
  },
  {
    name: "Local data",
    detail: "SQLite command layer planned",
    status: "mocked",
    icon: CheckCircle2
  }
];

export function SettingsPage() {
  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1>Settings</h1>
          <p>Security posture</p>
        </div>
      </header>

      <div className={styles.table}>
        {settings.map((item) => {
          const Icon = item.icon;
          return (
            <div className={styles.settingRow} key={item.name}>
              <span className={styles.primaryCell}>
                <strong>
                  <Icon size={16} /> {item.name}
                </strong>
              </span>
              <span className={styles.muted}>{item.detail}</span>
              <Badge>{item.status}</Badge>
            </div>
          );
        })}
      </div>
    </section>
  );
}
