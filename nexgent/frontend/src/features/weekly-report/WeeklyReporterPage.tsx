import { t, useLanguage } from "../../shared/i18n";
import { ArrowLeft, Bot } from "lucide-react";
import type { MouseEvent } from "react";

import { navigateToSection } from "../../shared/navigation/sections";
import { BulkWeeklyReportPanel } from "./BulkWeeklyReportPanel";
import { WeeklyReportSchedulePanel } from "./WeeklyReportSchedulePanel";
import styles from "./WeeklyReporterPage.module.css";

export function WeeklyReporterPage() {
  useLanguage((state) => state.language);
  function backToAgents(event: MouseEvent<HTMLAnchorElement>) {
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
    navigateToSection("agents");
  }

  return (
    <section className={styles.page}>
      <div className={styles.pageHeading}>
        <a className={styles.backLink} href="/agents" onClick={backToAgents}>
          <ArrowLeft size={16} aria-hidden />
          {t("Back to Agents")}
        </a>
        <header className={styles.pageHeader}>
          <span className={styles.titleIcon} aria-hidden>
            <Bot size={22} />
          </span>
          <div>
            <h1>{t("Weekly Reporter")}</h1>
            <p>
              {t("Start a durable concurrent run, watch live throughput, and download the verified export.")}
            </p>
          </div>
        </header>
      </div>

      <WeeklyReportSchedulePanel />
      <BulkWeeklyReportPanel />
    </section>
  );
}
