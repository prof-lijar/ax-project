import { Check, LoaderCircle, Pencil, Plus, Trash2, X } from "lucide-react";
import { useRef, useState } from "react";
import { useChatStore } from "../../shared/state/useChatStore";
import styles from "./ChatPage.module.css";

export function ConversationList({
  onSelect,
  onNew,
  onDelete,
  onClose
}: {
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onClose: () => void;
}) {
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
  return (
    <>
      <div className={styles.listHeading}>
        <strong>Chats this session</strong>
        <button
          className={styles.iconButton}
          onClick={onClose}
          aria-label="Close chat list"
          title="Close chat list"
        >
          <X size={17} />
        </button>
      </div>
      <button className={styles.newChatButton} onClick={onNew}>
        <Plus size={17} />
        New chat
      </button>
      <nav
        ref={listRef}
        className={styles.conversations}
        aria-label="Session conversations"
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
                  onSubmit={(event) => {
                    event.preventDefault();
                    renameChat(conversation.id, title);
                    finishEditing(conversation.id);
                  }}
                >
                  <input
                    aria-label="Conversation title"
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
                    disabled={!title.trim()}
                    aria-label="Save title"
                  >
                    <Check size={14} />
                  </button>
                  <button
                    className={styles.iconButton}
                    type="button"
                    onClick={() => finishEditing(conversation.id)}
                    aria-label="Cancel rename"
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
                    title={conversation.title}
                  >
                    <span>{conversation.title}</span>
                    {activeRequest?.conversationId === conversation.id && (
                      <LoaderCircle
                        size={14}
                        className={styles.spinner}
                        aria-label="Responding"
                      />
                    )}
                  </button>
                  <div className={styles.rowActions}>
                    <button
                      className={styles.iconButton}
                      aria-label={`Rename ${conversation.title}`}
                      title="Rename chat"
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
                      aria-label={`Delete ${conversation.title}`}
                      title="Delete chat"
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
                    Delete this chat
                    {activeRequest?.conversationId === conversation.id
                      ? " and stop its reply"
                      : ""}
                    ?
                  </span>
                  <button
                    onClick={() => {
                      onDelete(conversation.id);
                      setDeleting(null);
                    }}
                  >
                    Delete
                  </button>
                  <button onClick={() => setDeleting(null)}>Keep</button>
                </div>
              )}
            </div>
          ))}
      </nav>
      <p className={styles.sessionNote}>Chats are cleared when you reload.</p>
    </>
  );
}
