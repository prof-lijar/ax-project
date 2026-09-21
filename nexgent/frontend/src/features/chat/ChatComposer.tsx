import { ArrowUp, FileText, Paperclip, Square, X } from "lucide-react";
import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type RefObject
} from "react";
import { RAG_CHAT_GRAPH_ID } from "../../shared/api/agentCatalogClient";
import {
  type ChatConversation,
  useChatStore
} from "../../shared/state/useChatStore";
import {
  ATTACHMENT_ACCEPT,
  attachmentKey,
  deduplicateFiles,
  formatFileSize,
  validateSelectedFiles
} from "./chatAttachments";
import styles from "./ChatPage.module.css";
import { SavedFilePicker } from "./SavedFilePicker";

function FilePreview({ file }: { file: File }) {
  const [url, setUrl] = useState<string>();
  useEffect(() => {
    if (!file.type.startsWith("image/")) return;
    const preview = URL.createObjectURL(file);
    setUrl(preview);
    return () => URL.revokeObjectURL(preview);
  }, [file]);
  return url ? (
    <img src={url} alt="" className={styles.fileThumbnail} />
  ) : (
    <FileText size={20} aria-hidden />
  );
}
export function ChatComposer({
  disabled = false,
  conversation,
  inputRef,
  onSend,
  onStop,
  onOpenRunning
}: {
  disabled?: boolean;
  conversation: ChatConversation;
  inputRef: RefObject<HTMLTextAreaElement>;
  onSend: () => void;
  onStop: () => void;
  onOpenRunning: () => void;
}) {
  const activeRequest = useChatStore((state) => state.activeRequest);
  const { patchChat } = useChatStore.getState();
  const fileInput = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const dragDepth = useRef(0);
  const textOnly = conversation.agent?.graphId === RAG_CHAT_GRAPH_ID;
  const ownRequest = !!conversation.runId || activeRequest?.conversationId === conversation.id;
  const otherRequest = activeRequest && !ownRequest;
  useLayoutEffect(() => {
    const input = inputRef.current;
    if (!input) return;
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 200)}px`;
  }, [conversation.draft, conversation.id, inputRef]);
  useEffect(() => {
    dragDepth.current = 0;
    setDragging(false);
  }, [conversation.id]);
  function addFiles(incoming: File[]) {
    if (!incoming.length) return;
    if (textOnly) {
      patchChat(conversation.id, {
        notice: "RAG Agent supports text only. Choose AX Chat to attach files."
      });
      return;
    }
    const files = deduplicateFiles([...conversation.files, ...incoming]);
    const all = [...files, ...(conversation.selectedFiles ?? [])];
    const error = validateSelectedFiles(files) || (all.length > 5 || all.reduce((sum, f) => sum + f.size, 0) > 25 * 1024 * 1024
      ? "Select at most five files totaling 25 MiB." : null);
    patchChat(conversation.id, error ? { error } : { files, error: null });
  }
  return (
    <div className={styles.composerArea}>
      {otherRequest && (
        <div className={styles.busyNotice}>
          Another chat is responding.{" "}
          <button onClick={onOpenRunning}>View chat</button>
        </div>
      )}
      <form
        className={`${styles.composer} ${dragging ? styles.dragging : ""}`}
        onSubmit={(event) => {
          event.preventDefault();
          if (!disabled && !ownRequest && !conversation.submitting) onSend();
        }}
        onDragEnter={(event) => {
          if (Array.from(event.dataTransfer.types).includes("Files")) {
            event.preventDefault();
            dragDepth.current++;
            setDragging(true);
          }
        }}
        onDragOver={(event) => {
          if (Array.from(event.dataTransfer.types).includes("Files"))
            event.preventDefault();
        }}
        onDragLeave={(event) => {
          event.preventDefault();
          if (--dragDepth.current <= 0) setDragging(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          dragDepth.current = 0;
          setDragging(false);
          addFiles(Array.from(event.dataTransfer.files));
        }}
      >
        {dragging && (
          <div className={styles.dropHint}>
            {textOnly ? "RAG Agent supports text only" : "Drop files to attach"}
          </div>
        )}
        {!!conversation.selectedFiles?.length && <div className={styles.attachmentList} aria-label="Selected saved files">
          {conversation.selectedFiles.map(file => <div className={styles.attachment} key={file.id}>
            <FileText size={20} aria-hidden /><span>{file.name}<small>Saved file · {formatFileSize(file.size)}</small></span>
            <button type="button" aria-label={`Remove ${file.name}`} className={styles.iconButton}
              onClick={() => patchChat(conversation.id, { selectedFiles: conversation.selectedFiles?.filter(f => f.id !== file.id) })}><X size={14} /></button>
          </div>)}
        </div>}
        {conversation.files.length > 0 && (
          <div
            className={styles.attachmentList}
            aria-label="Selected attachments"
          >
            {conversation.files.map((file) => (
              <div className={styles.attachment} key={attachmentKey(file)}>
                <FilePreview file={file} />
                <span title={file.name}>
                  {file.name}
                  <small>{formatFileSize(file.size)}</small>
                </span>
                <button
                  type="button"
                  className={styles.iconButton}
                  aria-label={`Remove ${file.name}`}
                  onClick={() =>
                    patchChat(conversation.id, {
                      files: conversation.files.filter(
                        (f) => attachmentKey(f) !== attachmentKey(file)
                      )
                    })
                  }
                >
                  <X size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
        <textarea
          ref={inputRef}
          aria-label={`Message ${conversation.agent?.name ?? "AX"}`}
          aria-describedby="chat-composer-help"
          placeholder={`Message ${conversation.agent?.name ?? "AX"}`}
          rows={1}
          value={conversation.draft}
          onChange={(event) =>
            patchChat(conversation.id, { draft: event.target.value })
          }
          onKeyDown={(event) => {
            if (
              event.key === "Enter" &&
              !event.shiftKey &&
              !event.nativeEvent.isComposing &&
              event.keyCode !== 229
            ) {
              event.preventDefault();
              if (!activeRequest && !ownRequest && !conversation.submitting && !disabled) onSend();
            }
          }}
          onPaste={(event) => {
            const files = Array.from(event.clipboardData.items)
              .filter(
                (item) => item.kind === "file" && item.type.startsWith("image/")
              )
              .map((item) => item.getAsFile())
              .filter((file): file is File => file !== null);
            if (files.length) {
              event.preventDefault();
              addFiles(files);
            }
          }}
        />
        <div className={styles.composerTools}>
          <input
            ref={fileInput}
            type="file"
            hidden
            multiple
            accept={ATTACHMENT_ACCEPT}
            disabled={textOnly}
            onChange={(event) => {
              addFiles(Array.from(event.target.files ?? []));
              event.target.value = "";
            }}
          />
          <button
            type="button"
            className={styles.iconButton}
            disabled={textOnly}
            aria-label="Attach files"
            title={textOnly ? "RAG Agent supports text only" : "Attach files"}
            onClick={() => fileInput.current?.click()}
          >
            <Paperclip size={19} />
          </button>
          <span className={styles.attachmentHint}>
            {textOnly ? "Text only" : "Up to 5 files · 25 MB total"}
          </span>
          {ownRequest ? (
            <button
              className={styles.sendButton}
              type="button"
              onClick={onStop}
              aria-label="Stop response"
              title="Stop response"
            >
              <Square size={15} fill="currentColor" />
            </button>
          ) : (
            <button
              className={styles.sendButton}
              type="submit"
              disabled={disabled || !!conversation.submitting || Boolean(activeRequest) || !conversation.draft.trim()}
              aria-label="Send message"
              title={
                otherRequest ? "Another chat is responding" : "Send message"
              }
            >
              <ArrowUp size={20} />
            </button>
          )}
        </div>
      </form>
      {conversation.submitting && <p role="status">Saving your message…</p>}
      {conversation.serverId && !textOnly && <SavedFilePicker conversation={conversation} />}
      <p id="chat-composer-help" className={styles.composerHelp}>
        Enter to send · Shift+Enter for a new line
      </p>
      <p className={styles.contextNote}>
        {textOnly ? "RAG uses your latest question only. This chat is not saved." : "AX uses recent messages in this chat. Select saved files to include them again."}
      </p>
    </div>
  );
}
