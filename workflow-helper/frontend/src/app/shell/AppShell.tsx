import {
  Bell,
  CirclePlus,
  PauseCircle,
  Search,
  ShieldCheck,
  Wifi
} from "lucide-react";
import type { PropsWithChildren } from "react";

import { navItems } from "../routes";
import { useSystemHealth, useWorkspace } from "../../shared/api/queries";
import { StatusBadge } from "../../shared/components/Badge";
import { useUiStore } from "../../shared/state/useUiStore";
import styles from "./AppShell.module.css";

export function AppShell({ children }: PropsWithChildren) {
  const activeSection = useUiStore((state) => state.activeSection);
  const setActiveSection = useUiStore((state) => state.setActiveSection);
  const search = useUiStore((state) => state.search);
  const setSearch = useUiStore((state) => state.setSearch);
  const { data: workspace } = useWorkspace();
  const { data: health } = useSystemHealth();

  return (
    <div className={styles.shell}>
      <aside className={styles.rail}>
        <div className={styles.brand}>
          <span className={styles.brandMark}>WH</span>
          <span>
            <strong>Workflow Helper</strong>
            <small>{workspace?.name ?? "AX Project"}</small>
          </span>
        </div>

        <nav className={styles.nav} aria-label="Primary navigation">
          {navItems.map((item) => {
            const Icon = item.icon;
            const selected = activeSection === item.id;

            return (
              <button
                key={item.id}
                className={selected ? styles.navItemActive : styles.navItem}
                onClick={() => setActiveSection(item.id)}
                type="button"
              >
                <Icon size={18} strokeWidth={2.1} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        <div className={styles.railStatus}>
          <div>
            <span className={styles.statusIcon}>
              <Wifi size={15} />
            </span>
            <span>Local shell</span>
          </div>
          <StatusBadge status={health?.status ?? "healthy"} />
        </div>
      </aside>

      <main className={styles.main}>
        <header className={styles.commandStrip}>
          <label className={styles.searchBox}>
            <Search size={18} aria-hidden />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search work, co-workers, decisions"
              aria-label="Search"
            />
          </label>

          <div className={styles.actions}>
            <button className={styles.iconButton} type="button" title="Policy">
              <ShieldCheck size={18} />
            </button>
            <button
              className={styles.iconButton}
              type="button"
              title="Notifications"
            >
              <Bell size={18} />
            </button>
            <button className={styles.secondaryButton} type="button">
              <PauseCircle size={18} />
              <span>Pause</span>
            </button>
            <button className={styles.primaryButton} type="button">
              <CirclePlus size={18} />
              <span>Create task</span>
            </button>
          </div>
        </header>

        <section className={styles.content}>{children}</section>
      </main>
    </div>
  );
}
