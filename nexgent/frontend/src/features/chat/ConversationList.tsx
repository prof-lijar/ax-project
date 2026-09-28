import { t, useLanguage } from "../../shared/i18n";
import { Check, LoaderCircle, Pencil, Plus, Trash2, X } from "lucide-react";
import { useRef, useState } from "react";
import { useChatStore } from "../../shared/state/useChatStore";
import styles from "./ChatPage.module.css";
import { chatHistoryClient } from "../../shared/api/chatHistoryClient";
import { historyChanged } from "./persistentChatRunner";
import type { SavedChatHistory } from "./useSavedChatHistory";

export function ConversationList({
  history,
  onSelect,
  onNew,
  onDelete,
  onClose
}: {
  history: SavedChatHistory;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onClose: () => void;
}) {
  useLanguage((state) => state.language);
  const { conversations, activeId, activeRequest, renameChat } = useChatStore();
  const listRef = useRef<HTMLElement>(null);
  function finishEditing(id: string) {
    setEditing(null);
    requestAnimationFrame(() =>
      listRef.current
        ?.querySelector<HTMLElement>(`[data-chat-id="${id}"]`)
        ?.focus()
    );
  }
  const [editing, setEditing] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [deleting, setDeleting] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <>
      <div className={styles.listHeading}>
        <strong>{t("Chats")}</strong>
        <button
          className={styles.iconButton}
          onClick={onClose}
          aria-label={t("Close chat list")}
          title={t("Close chat list")}
        >
          <X size={17} />
        </button>
      </div>
      <button className={styles.newChatButton} onClick={onNew}>
        <Plus size={17} />
        {t("New chat")}
      </button>
      <nav
        ref={listRef}
        className={styles.conversations}
        aria-label={t("Conversations")}
      >
        {[...conversations]
          .sort((a, b) => b.updatedAt - a.updatedAt)
          .map((conversation) => (
            <div
              key={conversation.id}
              className={
                conversation.id === activeId
                  ? styles.conversationSelected
                  : styles.conversationRow
              }
            >
              {editing === conversation.id ? (
                <form
                  className={styles.renameForm}
                  onSubmit={async (event) => {
                    event.preventDefault();
                    setSaving(true); setError(null);
                    try {
                      if (conversation.serverId) await chatHistoryClient.rename(conversation.serverId, title.trim());
                      renameChat(conversation.id, title);
                      finishEditing(conversation.id); historyChanged();
                    } catch (failure) { setError((failure as Error).message); }
                    finally { setSaving(false); }
                  }}
                >
                  <input
                    aria-label={t("Conversation title")}
                    autoFocus
                    maxLength={120}
                    value={title}
                    onChange={(event) => setTitle(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Escape") {
                        event.stopPropagation();
                        finishEditing(conversation.id);
                      }
                    }}
                  />
                  <button
                    className={styles.iconButton}
                    disabled={saving || !title.trim()}
                    aria-label={t("Save title")}
                  >
                    <Check size={14} />
                  </button>
                  <button
                    className={styles.iconButton}
                    type="button"
                    onClick={() => finishEditing(conversation.id)}
                    aria-label={t("Cancel rename")}
                  >
                    <X size={14} />
                  </button>
                </form>
              ) : (
                <>
                  <button
                    data-chat-id={conversation.id}
                    className={styles.conversationLink}
                    onClick={() => onSelect(conversation.id)}
                    aria-current={
                      conversation.id === activeId ? "page" : undefined
                    }
                    title={conversationTitle(conversation)}
                  >
                    <span>{conversationTitle(conversation)}</span>
                    {(conversation.runId || activeRequest?.conversationId === conversation.id) && (
                      <LoaderCircle
                        size={14}
                        className={styles.spinner}
                        aria-label={t("Responding")}
                      />
                    )}
                  </button>
                  <div className={styles.rowActions}>
                    <button
                      className={styles.iconButton}
                      aria-label={t("Rename {0}", { 0: conversationTitle(conversation) })}
                      title={t("Rename chat")}
                      onClick={() => {
                        setEditing(conversation.id);
                        setTitle(conversation.title);
                        setDeleting(null);
                      }}
                    >
                      <Pencil size={13} />
                    </button>
                    <button
                      className={styles.iconButton}
                      aria-label={t("Delete {0}", { 0: conversationTitle(conversation) })}
                      title={t("Delete chat")}
                      disabled={conversation.submitting}
                      onClick={() => setDeleting(conversation.id)}
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </>
              )}
              {deleting === conversation.id && (
                <div className={styles.deleteConfirmation}>
                  <span>
                    {t(conversation.runId || activeRequest?.conversationId === conversation.id
                      ? "Delete this chat and stop its reply?" : "Delete this chat?")}
                  </span>
                  <button
                    onClick={() => {
                      onDelete(conversation.id);
                      setDeleting(null);
                    }}
                  >
                    {t("Delete")}
                  </button>
                  <button onClick={() => setDeleting(null)}>{t("Keep")}</button>
                </div>
              )}
            </div>
          ))}
      </nav>
      {(error || history.list.error) && <p role="alert">{error ?? history.list.error?.message} <button onClick={history.refresh}>{t("Retry")}</button></p>}
      {history.list.isPending && <p role="status">{t("Loading chats…")}</p>}
      {history.list.hasNextPage && <button disabled={history.list.isFetchingNextPage} onClick={() => void history.list.fetchNextPage()}>{t("Load more chats")}</button>}
      <p className={styles.sessionNote}>{t("AX chats are saved to your account. RAG chats last only this session.")}</p>
    </>
  );
}

// Translate only the untouched, automatic empty-chat title, never a user title.
function conversationTitle(conversation: { title: string; renamed: boolean; messages: unknown[]; serverId?: string }) {
  return !conversation.serverId && !conversation.renamed && !conversation.messages.length && conversation.title === "New chat"
    ? t("New chat") : conversation.title;
}
