import type { PropsWithChildren } from "react";

import { navItems } from "../routes";
import { useSystemHealth } from "../../shared/api/queries";
import { navigateToSection } from "../../shared/navigation/sections";
import { useUiStore } from "../../shared/state/useUiStore";
import styles from "./AppShell.module.css";

export function AppShell({ children }: PropsWithChildren) {
  const activeSection = useUiStore((state) => state.activeSection);
  const healthQuery = useSystemHealth();
  const chatIsActive = activeSection === "chat";
  const systemIsGood =
    !healthQuery.isError &&
    (healthQuery.data?.status ?? "healthy") === "healthy";

  return (
    <div className={styles.shell}>
      <aside className={styles.rail}>
        <div className={styles.brand}>
          <span className={styles.brandMark} aria-hidden>N</span>
          <span>
            <strong>Nexgent</strong>
            <small>AX Project</small>
          </span>
        </div>

        <nav className={styles.nav} aria-label="Primary navigation">
          {navItems.map((item) => {
            const Icon = item.icon;
            const selected = activeSection === item.id;

            return (
              <a
                aria-current={selected ? "page" : undefined}
                key={item.id}
                className={selected ? styles.navItemActive : styles.navItem}
                href={item.path}
                onClick={(event) => {
                  if (
                    event.button !== 0 ||
                    event.metaKey ||
                    event.ctrlKey ||
                    event.shiftKey ||
                    event.altKey
                  ) {
                    return;
                  }
                  event.preventDefault();
                  navigateToSection(item.id);
                }}
              >
                <Icon size={18} strokeWidth={2.1} />
                <span>{item.label}</span>
              </a>
            );
          })}
        </nav>

        <div className={styles.railStatus}>
          <span>Status:</span>
          <strong className={systemIsGood ? styles.statusGood : styles.statusBad}>
            {systemIsGood ? "Good" : "Bad"}
          </strong>
        </div>
      </aside>

      <main className={styles.main}>
        <section className={chatIsActive ? styles.chatContent : styles.content}>
          {children}
        </section>
      </main>
    </div>
  );
}
