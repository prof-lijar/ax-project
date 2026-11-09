import { t, useLanguage } from "../../shared/i18n";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, type PropsWithChildren } from "react";
import { accountClient } from "../../shared/api/accountClient";
import { AUTH_EXPIRED_EVENT, setCsrfToken } from "../../shared/api/authenticatedFetch";
import { createConversation, useChatStore } from "../../shared/state/useChatStore";
import { useAx768Store } from "../../shared/state/useAx768Store";
import { useAgentRunStore } from "../../shared/state/useAgentRunStore";
import { useUiStore } from "../../shared/state/useUiStore";
import { AccountContext } from "./accountContext";
import { SignIn } from "./AccountApp";
import styles from "./AccountApp.module.css";

function resetFeatureState() {
  useAx768Store.getState().reset();
  const conversation = createConversation();
  useChatStore.setState({ conversations: [conversation], activeId: conversation.id, activeRequest: null });
  useAgentRunStore.getState().resetRuns();
  useUiStore.setState({ selectedAgent: null, pendingAgentRun: null, search: "" });
}
export function AuthGate({ children }: PropsWithChildren) {
  useLanguage((state) => state.language);
  if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
    return <main className={styles.login}><div><h1>{t("Open Nexgent in your browser")}</h1>
      <p>{t("Use your company’s Nexgent web address to sign in.")}</p></div></main>;
  }
  return <BrowserAuthGate>{children}</BrowserAuthGate>;
}
function BrowserAuthGate({ children }: PropsWithChildren) {
  useLanguage((state) => state.language);
  const client = useQueryClient();
  const previousUser = useRef<string | null>(null);
  const returnTo = useRef(typeof window !== "undefined" && window.location.pathname !== "/login"
    ? window.location.pathname + window.location.search : "/chat");
  const clearFeatures = async () => {
    await client.cancelQueries({ predicate: query => query.queryKey[0] !== "account" });
    client.removeQueries({ predicate: query => query.queryKey[0] !== "account" });
    resetFeatureState();
  };
  const query = useQuery({ queryKey: ["account"], retry: false, staleTime: 0,
    refetchInterval: 30_000, refetchOnWindowFocus: true,
    queryFn: async ({ signal }) => {
      const account = await accountClient.me(signal);
      if ((account?.id ?? null) !== previousUser.current) {
        await clearFeatures();
        previousUser.current = account?.id ?? null;
      }
      // Restore the URL before App mounts and synchronizes its section routing.
      if (account && window.location.pathname === "/login") {
        const target = returnTo.current.startsWith("/") && !returnTo.current.startsWith("//") ? returnTo.current : "/chat";
        window.history.replaceState(null, "", target);
      }
      return account;
    }
  });
  useEffect(() => {
    if (!query.data?.is_admin) {
      client.removeQueries({ queryKey: ["access"] });
      useAx768Store.getState().reset();
    }
  }, [client, query.data?.is_admin]);
  useEffect(() => {
    const expire = () => {
      setCsrfToken(null);
      previousUser.current = null;
      void client.cancelQueries({ queryKey: ["account"] });
      client.setQueryData(["account"], null);
      void clearFeatures();
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, expire);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, expire);
  }, [client]);
  useEffect(() => {
    if (query.isPending || query.isError) return;
    if (!query.data) {
      setCsrfToken(null);
      if (window.location.pathname !== "/login") {
        returnTo.current = window.location.pathname + window.location.search;
        window.history.replaceState(null, "", "/login");
      }
      void clearFeatures();
    } else if (window.location.pathname === "/login") {
      const target = returnTo.current.startsWith("/") && !returnTo.current.startsWith("//") ? returnTo.current : "/chat";
      window.history.replaceState(null, "", target);
      window.dispatchEvent(new PopStateEvent("popstate"));
    }
  }, [query.data?.id, query.isPending, query.isError]);
  if (query.isPending) return <main className={styles.login}><p role="status">{t("Opening Nexgent…")}</p></main>;
  if (query.isError) return <main className={styles.login}><div><p role="alert">{t("Account service unavailable.")}</p>
    <button onClick={() => void query.refetch()}>{t("Try again")}</button></div></main>;
  if (!query.data) return <SignIn onSignedIn={() => query.refetch()} />;
  return <AccountContext.Provider value={query.data}><div key={query.data.id}>{children}</div></AccountContext.Provider>;
}
