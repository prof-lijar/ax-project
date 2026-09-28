import { t, useLanguage } from "../../shared/i18n";
import { Check, ChevronDown, Menu, Plus, RefreshCw, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { RAG_CHAT_GRAPH_ID } from "../../shared/api/agentCatalogClient";
import {
  useAgentCatalog,
  useAgentServerHealth
} from "../../shared/api/queries";
import {
  type ChatMessage,
  useChatStore
} from "../../shared/state/useChatStore";
import { useUiStore } from "../../shared/state/useUiStore";
import type { AgentDefinition } from "../../shared/types/agents";
import { ChatComposer } from "./ChatComposer";
import { ChatTranscript } from "./ChatTranscript";
import { ConversationList } from "./ConversationList";
import type { ChatRunner } from "./chatRunner";
import { navigateChat, type SavedChatHistory } from "./useSavedChatHistory";
import { chatHistoryClient } from "../../shared/api/chatHistoryClient";
import { historyChanged } from "./persistentChatRunner";
import styles from "./ChatPage.module.css";

export function usesRagChat(graphId: string | null) {
  return graphId === RAG_CHAT_GRAPH_ID;
}
export function getChatCapableAgents(agents: AgentDefinition[]) {
  return agents.filter((agent) => agent.canRunInChat);
}
const starters = [
  { label: "Draft a message", prompt: "Help me draft a message about " },
  {
    label: "Summarize text",
    prompt: "Summarize the key points of this text:\n\n"
  },
  { label: "Plan next steps", prompt: "Help me plan the next steps for " }
];
export function ChatPage({ runner, history }: { runner: ChatRunner; history: SavedChatHistory }) {
  useLanguage((state) => state.language);
  const { conversations, activeId, activeRequest, patchChat, chooseAgent } =
    useChatStore();
  const conversation = conversations.find((c) => c.id === activeId)!;
  const selectedAgent = useUiStore((state) => state.selectedAgent);
  const health = useAgentServerHealth();
  const catalog = useAgentCatalog();
  const [wide, setWide] = useState(
    () =>
      typeof window !== "undefined" &&
      window.matchMedia("(min-width: 1120px)").matches
  );
  const [sidebarOpen, setSidebarOpen] = useState(wide);
  const [replaceAction, setReplaceAction] = useState<null | {
    draft: string;
    files: File[];
    notice: string | null;
    recovery: boolean;
  }>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const sidebarRef = useRef<HTMLElement>(null);
  const mainRef = useRef<HTMLDivElement>(null);
  const selectorRef = useRef<HTMLDetailsElement>(null);

  useEffect(() => {
    const query = window.matchMedia("(min-width: 1120px)");
    const changed = () => {
      setWide(query.matches);
      setSidebarOpen(query.matches);
    };
    query.addEventListener("change", changed);
    return () => query.removeEventListener("change", changed);
  }, []);
  useEffect(() => {
    // The existing Agents entry point hands its selection to Chat via useUiStore.
    const state = useChatStore.getState();
    const current = state.conversations.find(c => c.id === state.activeId)!;
    if (current.agent?.id !== selectedAgent?.id) {
      if (current.messages.length || current.serverId) {
        state.newChat(selectedAgent);
        navigateChat();
      } else state.chooseAgent(state.activeId, selectedAgent);
    }
    const pending = useUiStore.getState().pendingAgentRun;
    if (pending) {
      useUiStore.getState().clearPendingAgentRun();
      state.patchChat(state.activeId, {
        notice: "Choose a co-worker available in Chat to send a message."
      });
    }
  }, [selectedAgent]);
  useEffect(() => {
    setReplaceAction(null);
  }, [activeId]);
  useEffect(() => {
    if (!sidebarOpen || wide) return;
    const previous = document.activeElement as HTMLElement | null;
    const background = [
      mainRef.current,
      document
        .querySelector('nav[data-primary-navigation]')
        ?.closest("aside")
    ].filter(
      (element): element is HTMLElement => element instanceof HTMLElement
    );
    const newlyInert = background.filter(
      (element) => !element.hasAttribute("inert")
    );
    newlyInert.forEach((element) => element.setAttribute("inert", ""));
    sidebarRef.current?.querySelector<HTMLElement>("button")?.focus();
    function trap(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setSidebarOpen(false);
      }
      if (event.key !== "Tab") return;
      const elements = sidebarRef.current?.querySelectorAll<HTMLElement>(
        'button:not(:disabled), input, [tabindex="0"]'
      );
      if (!elements?.length) return;
      const first = elements[0],
        last = elements[elements.length - 1];
      if (!sidebarRef.current?.contains(document.activeElement)) {
        event.preventDefault();
        first.focus();
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", trap);
    return () => {
      document.removeEventListener("keydown", trap);
      newlyInert.forEach((element) => element.removeAttribute("inert"));
      previous?.focus();
    };
  }, [sidebarOpen, wide]);
  useEffect(() => {
    function outside(event: PointerEvent) {
      if (
        selectorRef.current?.open &&
        event.target instanceof Node &&
        !selectorRef.current.contains(event.target)
      )
        selectorRef.current.open = false;
    }
    function escape(event: KeyboardEvent) {
      if (event.key === "Escape" && selectorRef.current?.open) {
        selectorRef.current.open = false;
        selectorRef.current.querySelector("summary")?.focus();
      }
    }
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, []);
  function syncSelection() {
    const state = useChatStore.getState();
    useUiStore.setState({
      selectedAgent:
        state.conversations.find((c) => c.id === state.activeId)?.agent ?? null
    });
  }
  function focusComposer() {
    requestAnimationFrame(() => inputRef.current?.focus());
  }
  function selectChat(id: string) {
    useChatStore.getState().selectChat(id);
    navigateChat(useChatStore.getState().conversations.find(c => c.id === id)?.serverId);
    syncSelection();
    if (!wide) setSidebarOpen(false);
  }
  function newChat() {
    useChatStore.getState().newChat(conversation.agent);
    navigateChat();
    syncSelection();
    if (!wide) setSidebarOpen(false);
    focusComposer();
  }
  async function deleteChat(id: string) {
    const chat = useChatStore.getState().conversations.find(c => c.id === id);
    if (chat?.submitting) return;
    try {
      if (chat?.serverId) await chatHistoryClient.remove(chat.serverId);
      else if (activeRequest?.conversationId === id) runner.stop(id);
    } catch (error) { patchChat(id, { error: (error as Error).message }); return; }
    useChatStore.getState().deleteChat(id);
    const state = useChatStore.getState();
    navigateChat(state.conversations.find(c => c.id === state.activeId)?.serverId);
    historyChanged();
    syncSelection();
    requestAnimationFrame(() =>
      sidebarRef.current
        ?.querySelector<HTMLElement>('[aria-current="page"]')
        ?.focus()
    );
  }
  function selectAgent(agent: AgentDefinition | null) {
    if (conversation.agent?.id !== agent?.id && (conversation.messages.length || conversation.serverId)) {
      useChatStore.getState().newChat(agent);
      navigateChat();
    } else chooseAgent(activeId, agent);
    useUiStore.setState({ selectedAgent: agent });
    if (selectorRef.current) selectorRef.current.open = false;
    focusComposer();
  }
  function applyDraft(action: NonNullable<typeof replaceAction>) {
    const textOnly = usesRagChat(conversation.agent?.graphId ?? null);
    patchChat(activeId, {
      draft: action.draft,
      files: textOnly ? [] : action.files,
      notice:
        textOnly && action.files.length
          ? t("Prompt restored. RAG Agent supports text only; files were not restored.")
          : action.notice,
      ...(action.recovery ? { error: null, recovery: null } : {})
    });
    setReplaceAction(null);
    focusComposer();
  }
  function requestDraft(action: NonNullable<typeof replaceAction>) {
    if (conversation.draft || conversation.files.length)
      setReplaceAction(action);
    else applyDraft(action);
  }
  function reuse(message: ChatMessage) {
    requestDraft({
      draft: message.content,
      files: [],
      notice: message.attachments?.length
        ? t("Prompt reused. Reattach any files you need.")
        : null,
      recovery: false
    });
  }
  return (
    <div className={styles.page}>
      {sidebarOpen && (
        <>
          {!wide && (
            <button
              className={styles.drawerBackdrop}
              aria-label={t("Close chat list")}
              tabIndex={-1}
              onClick={() => setSidebarOpen(false)}
            />
          )}
          <aside
            ref={sidebarRef}
            id="chat-conversations"
            className={`${styles.sidebar} ${!wide ? styles.sidebarDrawer : ""}`}
            role={!wide ? "dialog" : undefined}
            aria-modal={!wide ? true : undefined}
            aria-label={t("Chat conversations")}
          >
            <ConversationList
              history={history}
              onSelect={selectChat}
              onNew={newChat}
              onDelete={deleteChat}
              onClose={() => {
                setSidebarOpen(false);
                toggleRef.current?.focus();
              }}
            />
          </aside>
        </>
      )}
      <div className={styles.chatMain} ref={mainRef}>
        <header className={styles.header}>
          <button
            ref={toggleRef}
            className={styles.iconButton}
            aria-label={t("Toggle chat list")}
            title={t("Toggle chat list")}
            aria-expanded={sidebarOpen}
            aria-controls="chat-conversations"
            onClick={() => setSidebarOpen((open) => !open)}
          >
            <Menu size={19} />
          </button>
          <details className={styles.agentSelector} ref={selectorRef}>
            <summary aria-label={t("Choose a co-worker for Chat")}>
              <span>{t(conversation.agent?.name ?? "AX Chat")}</span>
              <ChevronDown size={15} />
            </summary>
            <div className={styles.agentSelectorMenu}>
              <small>{t("Chat with")}</small>
              <button
                onClick={() => selectAgent(null)}
                aria-pressed={!conversation.agent}
              >
                <span>
                  {t("AX Chat")}<small>{t("General questions and files")}</small>
                </span>
                {!conversation.agent && <Check size={15} />}
              </button>
              {getChatCapableAgents(catalog.data ?? []).map((agent) => (
                <button
                  key={agent.id}
                  aria-pressed={conversation.agent?.id === agent.id}
                  onClick={() => selectAgent(agent)}
                >
                  <span>
                    {t(agent.name)}
                    <small>{t(agent.role)}</small>
                  </span>
                  {conversation.agent?.id === agent.id && <Check size={15} />}
                </button>
              ))}
              {catalog.isPending && <p>{t("Loading co-workers…")}</p>}
              {catalog.isError && (
                <p>
                  {t("Couldn't load co-workers.")}{" "}
                  <button onClick={() => void catalog.refetch()}>{t("Retry")}</button>
                </p>
              )}
            </div>
          </details>
          <span className={styles.headerSpacer} />
          {health.isError && (
            <div className={styles.healthWarning}>
              <span>{t("Connection unavailable")}</span>
              <button
                className={styles.iconButton}
                aria-label={t("Retry connection")}
                title={t("Retry connection")}
                disabled={health.isFetching}
                onClick={() => void health.refetch()}
              >
                <RefreshCw size={15} />
              </button>
            </div>
          )}
          <button
            className={styles.iconButton}
            aria-label={t("New chat")}
            title={t("New chat")}
            onClick={newChat}
          >
            <Plus size={20} />
          </button>
        </header>
        <div
          className={`${styles.conversationBody} ${!conversation.messages.length ? styles.emptyBody : ""}`}
        >
          {history.loading ? <p role="status">{t("Loading conversation…")}</p> : history.error && conversation.serverId ? (
            <div role="alert"><p>{history.error.message}</p><button onClick={history.refresh}>{t("Retry")}</button></div>
          ) : conversation.messages.length ? (
            <ChatTranscript
              key={activeId}
              conversation={conversation}
              onReuse={reuse}
              onLoadEarlier={() => void history.messages.fetchNextPage()}
              hasEarlier={!!history.messages.hasNextPage}
              loadingEarlier={history.messages.isFetchingNextPage}
            />
          ) : (
            <div className={styles.welcome}>
              <h1>{t("How can I help?")}</h1>
              <div className={styles.starters}>
                {starters.map((starter) => (
                  <button
                    key={starter.label}
                    onClick={() =>
                      requestDraft({
                        draft: t(starter.prompt),
                        files: [],
                        notice: null,
                        recovery: false
                      })
                    }
                  >
                    {t(starter.label)}
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className={styles.composerDock}>
            {conversation.error && (
              <div className={styles.error} role="alert">
                <span>{t(conversation.error)}</span>
                {conversation.recovery && (
                  <button
                    onClick={() =>
                      requestDraft({
                        draft: conversation.recovery!.prompt,
                        files: conversation.recovery!.files,
                        notice: "Prompt restored. Review it before sending.",
                        recovery: true
                      })
                    }
                  >
                    {t("Restore prompt")}
                  </button>
                )}
                <button
                  className={styles.iconButton}
                  aria-label={t("Dismiss error")}
                  onClick={() => patchChat(activeId, { error: null })}
                >
                  <X size={14} />
                </button>
              </div>
            )}
            {conversation.notice && (
              <div className={styles.notice} role="status">
                <span>{t(conversation.notice)}</span>
                <button
                  className={styles.iconButton}
                  aria-label={t("Dismiss notice")}
                  onClick={() => patchChat(activeId, { notice: null })}
                >
                  <X size={14} />
                </button>
              </div>
            )}
            {replaceAction && (
              <div className={styles.notice}>
                <span>{t("Replace your current draft and attachments?")}</span>
                <button onClick={() => applyDraft(replaceAction)}>
                  {t("Replace")}
                </button>
                <button onClick={() => setReplaceAction(null)}>
                  {t("Keep draft")}
                </button>
              </div>
            )}
            <ChatComposer
              disabled={history.loading || !!(history.error && conversation.serverId)}
              conversation={conversation}
              inputRef={inputRef}
              onSend={() => {
                if (conversation.agent && !conversation.agent.canRunInChat) {
                  patchChat(activeId, {
                    error:
                      t("This co-worker isn't available in Chat. Choose AX Chat or RAG Agent.")
                  });
                  return;
                }
                void runner.send(activeId);
                focusComposer();
              }}
              onStop={() => runner.stop(activeId)}
              onOpenRunning={() => {
                if (activeRequest) selectChat(activeRequest.conversationId);
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
