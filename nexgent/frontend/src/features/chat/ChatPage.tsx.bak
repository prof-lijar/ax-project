import { Bot, RefreshCw, Send, Square, User } from "lucide-react";
import {
  type FormEvent,
  type KeyboardEvent,
  useEffect,
  useRef,
  useState
} from "react";

import {
  AgentServerError,
  agentServerClient
} from "../../shared/api/agentServerClient";
import { useAgentServerHealth } from "../../shared/api/queries";
import {
  type ChatRole,
  useChatStore
} from "../../shared/state/useChatStore";
import { ChatMarkdown } from "./ChatMarkdown";
import styles from "./ChatPage.module.css";

export function ChatPage() {
  const messages = useChatStore((state) => state.messages);
  const appendMessage = useChatStore((state) => state.appendMessage);
  const updateMessage = useChatStore((state) => state.updateMessage);
  const healthQuery = useAgentServerHealth();
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(
    null
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const requestInFlightRef = useRef(false);
  const scrollAnchorRef = useRef<HTMLDivElement | null>(null);
  const latestMessageContent = messages[messages.length - 1]?.content;

  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({
      behavior: isSending ? "auto" : "smooth"
    });
  }, [messages.length, latestMessageContent, isSending, errorMessage, notice]);

  useEffect(
    () => () => {
      abortControllerRef.current?.abort();
    },
    []
  );

  async function sendMessage(event?: FormEvent) {
    event?.preventDefault();
    const message = draft.trim();
    if (!message || requestInFlightRef.current) {
      return;
    }

    requestInFlightRef.current = true;
    setIsSending(true);
    setErrorMessage(null);
    setNotice(null);
    setDraft("");
    appendMessage(createMessage("user", message));

    const controller = new AbortController();
    abortControllerRef.current = controller;
    const assistantMessageId = createMessageId();
    let assistantMessageStarted = false;

    try {
      const response = await agentServerClient.streamChat(message, {
        signal: controller.signal,
        onResponse: (partialResponse) => {
          if (!assistantMessageStarted) {
            if (!partialResponse) {
              return;
            }
            assistantMessageStarted = true;
            appendMessage({
              id: assistantMessageId,
              role: "assistant",
              content: partialResponse
            });
            setStreamingMessageId(assistantMessageId);
            return;
          }
          updateMessage(assistantMessageId, partialResponse);
        }
      });
      if (!assistantMessageStarted) {
        appendMessage({
          id: assistantMessageId,
          role: "assistant",
          content: response
        });
      }
    } catch (error) {
      if (error instanceof AgentServerError && error.code === "cancelled") {
        setNotice("Response cancelled. You can send another message.");
      } else {
        setErrorMessage(
          error instanceof Error
            ? error.message
            : "The Agent Server could not complete the request."
        );
        void healthQuery.refetch();
      }
    } finally {
      abortControllerRef.current = null;
      requestInFlightRef.current = false;
      setStreamingMessageId(null);
      setIsSending(false);
    }
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault();
      void sendMessage();
    }
  }

  function cancelRequest() {
    abortControllerRef.current?.abort();
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1>AX Chat</h1>
          <p>Ask one question at a time.</p>
        </div>
        <div className={styles.health} aria-live="polite">
          <span
            className={
              healthQuery.isPending
                ? styles.statusChecking
                : healthQuery.isError
                  ? styles.statusOffline
                  : styles.statusOnline
            }
            aria-hidden
          />
          <span>
            {healthQuery.isPending
              ? "Checking server"
              : healthQuery.isError
                ? "Server unavailable"
                : "Server available"}
          </span>
          {healthQuery.isError && (
            <button
              type="button"
              onClick={() => void healthQuery.refetch()}
              disabled={healthQuery.isFetching}
            >
              <RefreshCw size={14} />
              Retry
            </button>
          )}
        </div>
      </header>

      <section
        className={styles.transcript}
        aria-label="Chat transcript"
        aria-busy={isSending}
      >
        <div className={styles.messageColumn}>
          {messages.length === 0 && !isSending ? (
            <div className={styles.emptyState}>
              <Bot size={28} />
              <h2>How can AX help?</h2>
              <p>Your transcript stays in this app until the page is reloaded.</p>
            </div>
          ) : (
            messages.map((message) => (
              <article
                className={
                  message.role === "user"
                    ? styles.userMessage
                    : styles.assistantMessage
                }
                key={message.id}
              >
                <span className={styles.avatar} aria-hidden>
                  {message.role === "user" ? <User size={17} /> : <Bot size={17} />}
                </span>
                <div>
                  <strong className={styles.speaker}>
                    {message.role === "user" ? "You" : "AX"}
                  </strong>
                  {message.role === "user" ? (
                    <p className={styles.plainText}>{message.content}</p>
                  ) : (
                    <>
                      <ChatMarkdown content={message.content} />
                      {streamingMessageId === message.id && (
                        <span className={styles.streamCursor} aria-hidden />
                      )}
                    </>
                  )}
                </div>
              </article>
            ))
          )}

          {isSending && !streamingMessageId && (
            <article className={styles.assistantMessage} aria-live="polite">
              <span className={styles.avatar} aria-hidden>
                <Bot size={17} />
              </span>
              <div>
                <strong className={styles.speaker}>AX</strong>
                <p className={styles.thinking}>Thinking…</p>
              </div>
            </article>
          )}

          {errorMessage && (
            <p className={styles.error} role="alert">
              {errorMessage} Check the server and try sending the message again.
            </p>
          )}
          {notice && (
            <p className={styles.notice} role="status">
              {notice}
            </p>
          )}
          <div ref={scrollAnchorRef} />
        </div>
      </section>

      <footer className={styles.composerArea}>
        <form className={styles.composer} onSubmit={sendMessage}>
          <textarea
            aria-label="Message AX"
            placeholder="Message AX"
            rows={2}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleComposerKeyDown}
          />
          {isSending ? (
            <button
              className={styles.cancelButton}
              type="button"
              onClick={cancelRequest}
              aria-label="Cancel response"
            >
              <Square size={16} fill="currentColor" />
            </button>
          ) : (
            <button
              className={styles.sendButton}
              type="submit"
              disabled={!draft.trim()}
              aria-label="Send message"
            >
              <Send size={17} />
            </button>
          )}
        </form>
        <small>Enter to send · Shift+Enter for a new line</small>
      </footer>
    </div>
  );
}

let messageSequence = 0;

function createMessage(role: ChatRole, content: string) {
  return {
    id: createMessageId(),
    role,
    content
  };
}

function createMessageId() {
  messageSequence += 1;
  return `${Date.now()}-${messageSequence}`;
}
