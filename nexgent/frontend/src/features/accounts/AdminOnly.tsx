import { LockKeyhole } from "lucide-react";
import type { PropsWithChildren } from "react";
import { t, useLanguage } from "../../shared/i18n";
import { navigateToSection } from "../../shared/navigation/sections";
import { useAccount } from "./accountContext";
import styles from "./AccountApp.module.css";

export function AdminOnly({ children }: PropsWithChildren) {
  useLanguage((state) => state.language);
  const account = useAccount();
  if (account.is_admin) return <>{children}</>;
  return (
    <section className={styles.accessDenied} aria-labelledby="access-denied-title" role="status">
      <LockKeyhole size={24} aria-hidden />
      <h1 id="access-denied-title">{t("Access restricted")}</h1>
      <p>{t("Only administrators can access this page.")}</p>
      <button type="button" onClick={() => navigateToSection("chat")}>{t("Go to Chat")}</button>
    </section>
  );
}
