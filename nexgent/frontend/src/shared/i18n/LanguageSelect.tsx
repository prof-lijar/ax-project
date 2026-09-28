import { Languages } from "lucide-react";
import { t, useLanguage, type Language } from ".";
import styles from "./LanguageSelect.module.css";

export function LanguageSelect() {
  const { language, setLanguage } = useLanguage();
  return (
    <label className={styles.control}>
      <Languages size={16} aria-hidden />
      <span className={styles.label}>{t("Language")}</span>
      <select aria-label={t("Language")} value={language}
        onChange={(event) => setLanguage(event.target.value as Language)}>
        <option value="en" lang="en">English</option>
        <option value="ko" lang="ko">한국어</option>
      </select>
    </label>
  );
}
