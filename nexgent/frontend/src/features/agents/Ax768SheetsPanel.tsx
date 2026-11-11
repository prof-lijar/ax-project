import { ArrowUpRight, FileSpreadsheet } from "lucide-react";
import { AX768_SHEETS } from "../../shared/api/ax768Sheets";
import { t, useLanguage } from "../../shared/i18n";
import styles from "./Ax768SheetsPanel.module.css";

export function Ax768SheetsPanel() {
  useLanguage(s => s.language);
  return <section className={styles.panel} aria-labelledby="ax-sheets-title">
    <header className={styles.header}>
      <div><h2 id="ax-sheets-title">{t("Sheet links")}</h2><p>{t("Open the spreadsheets used by 운영시트에이젠트.")}</p></div>
      <span>{t("{count} sheets", { count: AX768_SHEETS.length })}</span>
    </header>
    <ul className={styles.list}>{AX768_SHEETS.map(sheet => <li key={sheet.alias}>
      <a className={styles.sheet} href={`https://docs.google.com/spreadsheets/d/${sheet.spreadsheetId}/edit#gid=${sheet.gid}`} target="_blank" rel="noopener noreferrer"
        aria-label={t("Open {sheet} in Google Sheets (new tab)", { sheet: t(sheet.title) })}>
        <span className={styles.icon}><FileSpreadsheet size={22} aria-hidden /></span>
        <div className={styles.info}><h3>{t(sheet.title)}</h3><span>{sheet.alias}</span><p>{t("Cases: {cases}", { cases: sheet.cases.join(", ") })}</p></div>
        <span className={styles.open}>{t("Open sheet")}<ArrowUpRight size={17} aria-hidden /></span>
      </a>
    </li>)}</ul>
    <p className={styles.note}>{t("Links open in a new tab using your Google account’s sheet access.")}</p>
  </section>;
}
