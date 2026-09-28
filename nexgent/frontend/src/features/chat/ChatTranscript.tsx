import { t, useLanguage } from "../../shared/i18n";
import { ArrowDown, FileText, RotateCcw } from "lucide-react";
import { useCallback, useLayoutEffect, useRef } from "react";
import {
  type ChatConversation,
  type ChatMessage,
  useChatStore
} from "../../shared/state/useChatStore";
import { ChatMarkdown } from "./ChatMarkdown";
import { useStreamingText } from "./useStreamingText";
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
  useLanguage((state) => state.language);
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
  const followReveal = useCallback(() => {
    const element = viewport.current;
    const current = useChatStore.getState().conversations.find(c => c.id === conversation.id);
    if (element && current?.following) element.scrollTop = element.scrollHeight;
  }, [conversation.id]);
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
        aria-label={t("Chat transcript")}
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
          }}>{loadingEarlier ? t("Loading…") : t("Load earlier messages")}</button>}
          {conversation.messages.map((message) => (
            <ChatTurn key={message.id} message={message} conversation={conversation}
              onReuse={onReuse} onReveal={followReveal} />
          ))}
        </div>
      </section>
      {!conversation.following && (
        <button className={styles.jumpButton} onClick={jump}>
          <ArrowDown size={16} />
          {t("Jump to latest")}
        </button>
      )}
    </div>
  );
}

function ChatTurn({ message: received, conversation, onReuse, onReveal }: {
  message: ChatMessage;
  conversation: ChatConversation;
  onReuse: (message: ChatMessage) => void;
  onReveal: () => void;
}) {
  useLanguage((state) => state.language);
  const display = useStreamingText(received.content, received.role === "assistant" ? received.status : undefined);
  const message = { ...received, content: display.content,
    status: display.revealing ? "streaming" as const : received.status };
  useLayoutEffect(onReveal, [display.content, onReveal]);
  return (
    <article
      className={
        message.role === "user" ? styles.userTurn : styles.assistantTurn
      }
      aria-label={
        message.role === "user"
          ? t("Your message")
          : message.status === "waiting"
            ? t("Waiting for {0}", { 0: message.speaker ?? "AX" })
            : t("{0} response", { 0: message.speaker ?? "AX" })
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
                aria-label={t("Message attachments")}
              >
                {message.attachments.map((file, index) => (
                  <li key={`${file.name}-${index}`}>
                    <FileText size={15} aria-hidden />
                    <span title={file.name}>{file.name}</span>
                    <small>{formatFileSize(file.size)}</small>
                    {file.id && <>
                      <a href={`/api/chat/attachments/${file.id}/download`} download={file.name}>{t("Download")}</a>
                      <button onClick={() => selectSavedFile(conversation, file)}>{t("Use again")}</button>
                    </>}
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : (
          <>
            {message.status === "waiting" ? (
              <span className={styles.waitingIndicator} aria-hidden />
            ) : (
              <>
                <strong className={styles.speaker}>
                  {message.speaker ?? "AX"}
                </strong>
                <ChatMarkdown content={message.content} />
              </>
            )}
            {message.status === "complete" && (
              <span className={styles.srOnly} role="status">
                {t("Reply complete.")}
              </span>
            )}
            {message.status === "streaming" && (
              <span className={styles.streamCursor} aria-hidden />
            )}
            {message.status === "stopped" && (
              <small className={styles.responseStatus} role="status">
                {t("Response stopped")}
              </small>
            )}
            {message.status === "failed" && (
              <small className={styles.responseStatus} role="status">
                {t("Reply interrupted. You can restore your prompt below.")}
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
              title={t("Reuse prompt")}
              aria-label={t("Reuse prompt")}
            >
              <RotateCcw size={15} />
            </button>
          )}
        </div>
      )}
    </article>
  );
}
