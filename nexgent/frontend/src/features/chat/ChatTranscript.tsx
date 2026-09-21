import { ArrowDown, FileText, RotateCcw } from "lucide-react";
import { useLayoutEffect, useRef } from "react";
import {
  type ChatConversation,
  type ChatMessage,
  useChatStore
} from "../../shared/state/useChatStore";
import { ChatMarkdown } from "./ChatMarkdown";
import { CopyButton } from "./MessageActions";
import { formatFileSize } from "./chatAttachments";
import styles from "./ChatPage.module.css";
import { selectSavedFile } from "./SavedFilePicker";

export function isNearBottom(
  scrollTop: number,
  scrollHeight: number,
  clientHeight: number
) {
  return scrollHeight - clientHeight - scrollTop <= 80;
}
export function ChatTranscript({
  conversation,
  onReuse,
  hasEarlier = false,
  loadingEarlier = false,
  onLoadEarlier
}: {
  conversation: ChatConversation;
  onReuse: (message: ChatMessage) => void;
  hasEarlier?: boolean;
  loadingEarlier?: boolean;
  onLoadEarlier?: () => void;
}) {
  const viewport = useRef<HTMLDivElement>(null);
  const previousHeight = useRef<{ height: number; first?: string } | null>(null);
  useLayoutEffect(() => {
    if (previousHeight.current !== null && viewport.current && previousHeight.current.first !== conversation.messages[0]?.id) {
      viewport.current.scrollTop += viewport.current.scrollHeight - previousHeight.current.height;
      previousHeight.current = null;
    }
  }, [conversation.messages]);
  const last = conversation.messages[conversation.messages.length - 1];
  useLayoutEffect(() => {
    const element = viewport.current;
    if (element)
      element.scrollTop = conversation.following
        ? element.scrollHeight
        : conversation.scrollTop;
    // Restore only on conversation mount; incremental updates follow separately.
  }, [conversation.id]);
  useLayoutEffect(() => {
    const element = viewport.current;
    if (element && conversation.following)
      element.scrollTop = element.scrollHeight;
  }, [
    last?.content,
    last?.status,
    conversation.messages.length,
    conversation.following
  ]);
  function jump() {
    const element = viewport.current;
    if (element) element.scrollTop = element.scrollHeight;
    useChatStore.getState().patchChat(conversation.id, {
      following: true,
      scrollTop: element?.scrollTop ?? 0
    });
  }
  return (
    <div className={styles.transcriptWrap}>
      <section
        className={styles.transcript}
        ref={viewport}
        aria-label="Chat transcript"
        tabIndex={0}
        onScroll={(event) => {
          const element = event.currentTarget;
          useChatStore.getState().patchChat(conversation.id, {
            scrollTop: element.scrollTop,
            following: isNearBottom(
              element.scrollTop,
              element.scrollHeight,
              element.clientHeight
            )
          });
        }}
      >
        <div className={styles.messageColumn}>
          {hasEarlier && <button disabled={loadingEarlier} onClick={() => {
            previousHeight.current = viewport.current ? { height: viewport.current.scrollHeight, first: conversation.messages[0]?.id } : null;
            useChatStore.getState().patchChat(conversation.id, { following: false });
            onLoadEarlier?.();
          }}>{loadingEarlier ? "Loading…" : "Load earlier messages"}</button>}
          {conversation.messages.map((message) => (
            <article
              key={message.id}
              className={
                message.role === "user" ? styles.userTurn : styles.assistantTurn
              }
              aria-label={
                message.role === "user"
                  ? "Your message"
                  : `${message.speaker ?? "AX"} response`
              }
            >
              <div
                className={
                  message.role === "user"
                    ? styles.userMessage
                    : styles.assistantMessage
                }
              >
                {message.role === "user" ? (
                  <>
                    <p className={styles.plainText}>{message.content}</p>
                    {!!message.attachments?.length && (
                      <ul
                        className={styles.messageAttachments}
                        aria-label="Message attachments"
                      >
                        {message.attachments.map((file, index) => (
                          <li key={`${file.name}-${index}`}>
                            <FileText size={15} aria-hidden />
                            <span title={file.name}>{file.name}</span>
                            <small>{formatFileSize(file.size)}</small>
                            {file.id && <>
                              <a href={`/api/chat/attachments/${file.id}/download`} download={file.name}>Download</a>
                              <button onClick={() => selectSavedFile(conversation, file)}>Use again</button>
                            </>}
                          </li>
                        ))}
                      </ul>
                    )}
                  </>
                ) : (
                  <>
                    <strong className={styles.speaker}>
                      {message.speaker ?? "AX"}
                    </strong>
                    {message.status === "waiting" ? (
                      <p className={styles.thinking} role="status">
                        Thinking<span aria-hidden>…</span>
                      </p>
                    ) : (
                      <ChatMarkdown content={message.content} />
                    )}
                    {message.status === "complete" && (
                      <span className={styles.srOnly} role="status">
                        Reply complete.
                      </span>
                    )}
                    {message.status === "streaming" && (
                      <span className={styles.streamCursor} aria-hidden />
                    )}
                    {message.status === "stopped" && (
                      <small className={styles.responseStatus} role="status">
                        Response stopped
                      </small>
                    )}
                    {message.status === "failed" && (
                      <small className={styles.responseStatus} role="status">
                        Reply interrupted. You can restore your prompt below.
                      </small>
                    )}
                  </>
                )}
              </div>
              {message.content && message.status !== "streaming" && (
                <div className={styles.messageActions}>
                  <CopyButton text={message.content} />
                  {message.role === "user" && (
                    <button
                      className={styles.iconButton}
                      onClick={() => onReuse(message)}
                      title="Reuse prompt"
                      aria-label="Reuse prompt"
                    >
                      <RotateCcw size={15} />
                    </button>
                  )}
                </div>
              )}
            </article>
          ))}
        </div>
      </section>
      {!conversation.following && (
        <button className={styles.jumpButton} onClick={jump}>
          <ArrowDown size={16} />
          Jump to latest
        </button>
      )}
    </div>
  );
}
