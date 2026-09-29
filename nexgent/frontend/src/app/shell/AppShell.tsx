import { LanguageSelect } from "../../shared/i18n/LanguageSelect";
import { t, useLanguage } from "../../shared/i18n";
import type { PropsWithChildren } from "react";
import { LockKeyhole } from "lucide-react";
import { useAccount } from "../../features/accounts/accountContext";

import { navItems } from "../routes";
import { useSystemHealth } from "../../shared/api/queries";
import { navigateToSection } from "../../shared/navigation/sections";
import { useUiStore } from "../../shared/state/useUiStore";
import styles from "./AppShell.module.css";

export function AppShell({ children }: PropsWithChildren) {
  useLanguage((state) => state.language);
  const account = useAccount();
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

        <nav data-primary-navigation className={styles.nav} aria-label={t("Primary navigation")}>
          {navItems.map((item) => {
            const Icon = item.icon;
            const selected = activeSection === item.id;

            if (item.id === "rag" && !account.is_admin) {
              return (
                <button key={item.id} type="button" disabled className={styles.navItemDisabled}
                  aria-label={`${t(item.label)} — ${t("Admin only")}`} title={t("Only administrators can access this page.")}>
                  <Icon size={18} strokeWidth={2.1} aria-hidden />
                  <span>{t(item.label)} <LockKeyhole size={12} aria-hidden /><small>{t("Admin only")}</small></span>
                </button>
              );
            }

            return (
              <a
                aria-label={t(item.label)}
                title={t(item.label)}
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
                <span>{t(item.label)}</span>
              </a>
            );
          })}
        </nav>

        <LanguageSelect />
        <div className={styles.railStatus}>
          <span>{t("Status:")}</span>
          <strong className={systemIsGood ? styles.statusGood : styles.statusBad}>
            {systemIsGood ? t("Good") : t("Bad")}
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
