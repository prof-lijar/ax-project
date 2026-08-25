import {
  Bot,
  Check,
  ChevronDown,
  FileText,
  LoaderCircle,
  Paperclip,
  RefreshCw,
  Send,
  Square,
  User,
  X
} from "lucide-react";
import {
  type ChangeEvent,
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
import { RAG_CHAT_GRAPH_ID } from "../../shared/api/agentCatalogClient";
import {
  useAgentCatalog,
  useAgentServerHealth
} from "../../shared/api/queries";
import {
  type ChatAttachmentSummary,
  type ChatRole,
  useChatStore
} from "../../shared/state/useChatStore";
import {
  getMockAgentRunStageState,
  MOCK_AGENT_RUN_STAGES,
  type MockAgentRun,
  useAgentRunStore
} from "../../shared/state/useAgentRunStore";
import { useUiStore } from "../../shared/state/useUiStore";
import { ChatMarkdown } from "./ChatMarkdown";
import styles from "./ChatPage.module.css";
import { RequestLanes } from "./requestLanes";

const WEEKLY_REPORTER_GRAPH_ID = "ansimk_weekly_reporter";
const REPORT_TIMEZONE = "Asia/Seoul";
const MAX_ATTACHMENT_COUNT = 5;
const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;
const MAX_TOTAL_ATTACHMENT_BYTES = 25 * 1024 * 1024;
const ACCEPTED_ATTACHMENT_EXTENSIONS = new Set([
  "csv",
  "docx",
  "jpeg",
  "jpg",
  "md",
  "pdf",
  "png",
  "txt",
  "webp"
]);
const ATTACHMENT_ACCEPT =
  ".pdf,.txt,.md,.csv,.docx,.png,.jpg,.jpeg,.webp," +
  "application/pdf,text/plain,text/markdown,text/csv," +
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document," +
  "image/png,image/jpeg,image/webp";
const LIVE_REPORT_STAGES = [
  "Starting report batch",
  "Reading ward risk data",
  "Generating ward reports",
  "Finalizing output"
] as const;

const MOCK_SLASH_COMMANDS = [
  { command: "/a", label: "Action A" },
  { command: "/b", label: "Action B" },
  { command: "/c", label: "Action C" }
] as const;

type MockSlashCommand = (typeof MOCK_SLASH_COMMANDS)[number];

interface LiveExecutionProgress {
  agentId: string;
  agentName: string;
  assistantMessageId: string;
  activeStageIndex: number;
  startedAt: number;
  durationSeconds: number | null;
  status: "running" | "finished" | "stopped";
  mode: "live";
}

type ExecutionProgress = LiveExecutionProgress | MockAgentRun;

export function ChatPage() {
  const messages = useChatStore((state) => state.messages);
  const appendMessage = useChatStore((state) => state.appendMessage);
  const updateMessage = useChatStore((state) => state.updateMessage);
  const errorMessage = useChatStore((state) => state.errorMessage);
  const setErrorMessage = useChatStore((state) => state.setErrorMessage);
  const mockRunsByAgentId = useAgentRunStore((state) => state.runsByAgentId);
  const startMockRun = useAgentRunStore((state) => state.startRun);
  const completeMockRun = useAgentRunStore((state) => state.completeRun);
  const failMockRun = useAgentRunStore((state) => state.failRun);
  const cancelMockRun = useAgentRunStore((state) => state.cancelRun);
  const selectedAgent = useUiStore((state) => state.selectedAgent);
  const selectAgent = useUiStore((state) => state.selectAgent);
  const clearSelectedAgent = useUiStore((state) => state.clearSelectedAgent);
  const pendingAgentRun = useUiStore((state) => state.pendingAgentRun);
  const clearPendingAgentRun = useUiStore(
    (state) => state.clearPendingAgentRun
  );
  const healthQuery = useAgentServerHealth();
  const catalogQuery = useAgentCatalog();
  const [draft, setDraft] = useState("");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isChatSending, setIsChatSending] = useState(false);
  const [isWeeklyReporterRunning, setIsWeeklyReporterRunning] = useState(false);
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(
    null
  );
  const [notice, setNotice] = useState<string | null>(null);
  const [weeklyReportError, setWeeklyReportError] = useState<string | null>(
    null
  );
  const [weeklyReportNotice, setWeeklyReportNotice] = useState<string | null>(
    null
  );
  const isRagAgentSelected = usesRagChat(selectedAgent?.graphId ?? null);
  const [liveExecution, setLiveExecution] =
    useState<LiveExecutionProgress | null>(null);
  const [slashMenuDismissed, setSlashMenuDismissed] = useState(false);
  const [highlightedSlashCommandIndex, setHighlightedSlashCommandIndex] =
    useState(0);
  const fileInputRef = useRef<HTMLInputElement | null>(null); // Added for file clip
  const composerRef = useRef<HTMLFormElement | null>(null);
  const composerInputRef = useRef<HTMLTextAreaElement | null>(null);
  const agentSelectorRef = useRef<HTMLDetailsElement | null>(null);
  const requestLanesRef = useRef(new RequestLanes());
  const activeMockRunRef = useRef<{ agentId: string; runId: string } | null>(
    null
  );
  const handledAgentRunRef = useRef<string | null>(null);
  const scrollAnchorRef = useRef<HTMLDivElement | null>(null);
  const latestMessageContent = messages[messages.length - 1]?.content;
  const isTranscriptBusy = isChatSending || isWeeklyReporterRunning;
  const mockRuns = Object.values(mockRunsByAgentId);
  const executions: ExecutionProgress[] = liveExecution
    ? [liveExecution, ...mockRuns]
    : mockRuns;
  const pendingExecution = executions
    .filter(
      (execution) =>
        !messages.some(
          (message) => message.id === execution.assistantMessageId
        )
    )
    .sort((left, right) => right.startedAt - left.startedAt)[0] ?? null;
  const executionUpdateKey = executions
    .map(
      (execution) =>
        `${execution.agentId}:${execution.activeStageIndex}:${execution.status}`
    )
    .join("|");
  const slashQuery = getSlashQuery(draft);
  const filteredSlashCommands =
    slashQuery === null
      ? []
      : MOCK_SLASH_COMMANDS.filter(({ command }) =>
          command.slice(1).startsWith(slashQuery)
        );
  const slashMenuIsOpen = slashQuery !== null && !slashMenuDismissed;

  useEffect(() => {
    if (!isRagAgentSelected || selectedFiles.length === 0) {
      return;
    }
    setSelectedFiles([]);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, [isRagAgentSelected, selectedFiles.length]);

  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({
      behavior: isTranscriptBusy ? "auto" : "smooth"
    });
  }, [
    messages.length,
    latestMessageContent,
    isTranscriptBusy,
    errorMessage,
    notice,
    weeklyReportError,
    weeklyReportNotice,
    executionUpdateKey
  ]);

  useEffect(
    () => () => {
      requestLanesRef.current.cancelAll();
    },
    []
  );

  useEffect(() => {
    function closeAgentSelectorOnOutsideClick(event: PointerEvent) {
      const selector = agentSelectorRef.current;
      if (
        !selector?.open ||
        !(event.target instanceof Node) ||
        selector.contains(event.target)
      ) {
        return;
      }
      selector.open = false;
    }

    function closeAgentSelectorOnEscape(event: globalThis.KeyboardEvent) {
      const selector = agentSelectorRef.current;
      if (!selector?.open || event.key !== "Escape") {
        return;
      }
      event.preventDefault();
      selector.open = false;
      selector.querySelector<HTMLElement>("summary")?.focus();
    }

    document.addEventListener("pointerdown", closeAgentSelectorOnOutsideClick);
    document.addEventListener("keydown", closeAgentSelectorOnEscape);
    return () => {
      document.removeEventListener(
        "pointerdown",
        closeAgentSelectorOnOutsideClick
      );
      document.removeEventListener("keydown", closeAgentSelectorOnEscape);
    };
  }, []);

  useEffect(() => {
    if (!slashMenuIsOpen) {
      return;
    }

    function closeSlashMenuOnOutsideClick(event: PointerEvent) {
      const composer = composerRef.current;
      if (
        !composer ||
        !(event.target instanceof Node) ||
        composer.contains(event.target)
      ) {
        return;
      }
      setSlashMenuDismissed(true);
    }

    document.addEventListener("pointerdown", closeSlashMenuOnOutsideClick);
    return () =>
      document.removeEventListener(
        "pointerdown",
        closeSlashMenuOnOutsideClick
      );
  }, [slashMenuIsOpen]);

  useEffect(() => {
    if (!pendingAgentRun || pendingAgentRun.agentId !== selectedAgent?.id) {
      return;
    }
    if (handledAgentRunRef.current === pendingAgentRun.requestId) {
      return;
    }

    handledAgentRunRef.current = pendingAgentRun.requestId;
    clearPendingAgentRun();
    if (selectedAgent.graphId === WEEKLY_REPORTER_GRAPH_ID) {
      void runWeeklyReporter(selectedAgent);
      return;
    }
    setErrorMessage(`${selectedAgent.name} does not have a live Chat runner yet.`);
  }, [clearPendingAgentRun, pendingAgentRun, selectedAgent]);

  async function runWeeklyReporter(agent: { id: string; name: string }) {
    const controller = requestLanesRef.current.start("weekly-report");
    if (!controller) {
      setWeeklyReportNotice("Weekly Reporter is already running.");
      return;
    }

    const weekStart = getMostRecentCompletedMonday();
    const assistantMessageId = createMessageId();
    setIsWeeklyReporterRunning(true);
    setWeeklyReportError(null);
    setWeeklyReportNotice(null);
    appendMessage(
      createMessage(
        "user",
        `Run Weekly Reporter for ${weekStart} (${REPORT_TIMEZONE}).`
      )
    );
    startLiveExecution(agent, assistantMessageId);

    let requestCompleted = false;
    try {
      const result = await agentServerClient.runWeeklyReport(
        { week_start: weekStart, timezone: REPORT_TIMEZONE, limit: 3 },
        {
          signal: controller.signal,
          onProgress: updateLiveExecution
        }
      );
      appendMessage({
        id: assistantMessageId,
        role: "assistant",
        content: formatWeeklyReportBatch(result)
      });
      requestCompleted = true;
    } catch (error) {
      if (error instanceof AgentServerError && error.code === "cancelled") {
        setWeeklyReportNotice(
          "Weekly Reporter run cancelled. You can start it again from Agents."
        );
      } else {
        setWeeklyReportError(
          error instanceof Error
            ? error.message
            : "The Weekly Reporter could not complete the run."
        );
        void healthQuery.refetch();
      }
    } finally {
      finishLiveExecution(requestCompleted);
      requestLanesRef.current.finish("weekly-report", controller);
      setIsWeeklyReporterRunning(false);
    }
  }

  async function sendMessage(event?: FormEvent) {
    event?.preventDefault();
    const message = draft.trim();
    if (!message) {
      return;
    }

    const controller = requestLanesRef.current.start("chat");
    if (!controller) {
      return;
    }
    setIsChatSending(true);
    setErrorMessage(null);
    setNotice(null);
    setDraft("");
    const files = isRagAgentSelected ? [] : selectedFiles;
    setSelectedFiles([]);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    const userMessage = createMessage(
      "user",
      message,
      files.map(toAttachmentSummary)
    );
    appendMessage(userMessage);

    const assistantMessageId = createMessageId();

    const mockRun =
      selectedAgent?.graphId !== WEEKLY_REPORTER_GRAPH_ID &&
      selectedAgent?.graphId !== RAG_CHAT_GRAPH_ID &&
      selectedAgent
        ? {
            agentId: selectedAgent.id,
            runId: startMockRun({
              agentId: selectedAgent.id,
              agentName: selectedAgent.name,
              assistantMessageId,
              prompt: message
            })
          }
        : null;
    activeMockRunRef.current = mockRun;

    let assistantMessageStarted = false;

    try {
      const streamOptions = {
        signal: controller.signal,
        onResponse: (partialResponse: string) => {
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
      };
      const response = isRagAgentSelected
        ? await agentServerClient.streamRagChat(message, streamOptions)
        : await agentServerClient.streamChat(message, {
            ...streamOptions,
            files
          });
      if (!assistantMessageStarted) {
        appendMessage({
          id: assistantMessageId,
          role: "assistant",
          content: response
        });
      }
      if (mockRun) {
        completeMockRun(mockRun.agentId, mockRun.runId);
      }
    } catch (error) {
      if (error instanceof AgentServerError && error.code === "cancelled") {
        if (mockRun) {
          cancelMockRun(mockRun.agentId, mockRun.runId);
        }
        setNotice("Response cancelled. You can send another message.");
      } else {
        if (mockRun) {
          failMockRun(mockRun.agentId, mockRun.runId);
        }
        setErrorMessage(
          error instanceof Error
            ? error.message
            : "The Agent Server could not complete the request."
        );
        void healthQuery.refetch();
      }
    } finally {
      if (
        mockRun &&
        activeMockRunRef.current?.runId === mockRun.runId
      ) {
        activeMockRunRef.current = null;
      }
      requestLanesRef.current.finish("chat", controller);
      setStreamingMessageId(null);
      setIsChatSending(false);
    }
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (slashMenuIsOpen && !event.nativeEvent.isComposing) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        if (filteredSlashCommands.length > 0) {
          const direction = event.key === "ArrowDown" ? 1 : -1;
          setHighlightedSlashCommandIndex((currentIndex) =>
            (currentIndex + direction + filteredSlashCommands.length) %
            filteredSlashCommands.length
          );
        }
        return;
      }

      if (event.key === "Escape") {
        event.preventDefault();
        setSlashMenuDismissed(true);
        return;
      }

      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        const highlightedCommand =
          filteredSlashCommands[highlightedSlashCommandIndex] ??
          filteredSlashCommands[0];
        if (highlightedCommand) {
          selectSlashCommand(highlightedCommand);
        }
        return;
      }
    }

    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault();
      void sendMessage();
    }
  }

  function handleDraftChange(value: string) {
    setDraft(value);
    setSlashMenuDismissed(false);
    setHighlightedSlashCommandIndex(0);
  }

  function selectSlashCommand(command: MockSlashCommand) {
    setDraft(`${command.command} `);
    setSlashMenuDismissed(true);
    setHighlightedSlashCommandIndex(0);
    window.requestAnimationFrame(() => composerInputRef.current?.focus());
  }

  function cancelChatRequest() {
    const activeMockRun = activeMockRunRef.current;
    if (activeMockRun) {
      cancelMockRun(activeMockRun.agentId, activeMockRun.runId);
    }
    requestLanesRef.current.cancel("chat");
  }

  function cancelWeeklyReport() {
    requestLanesRef.current.cancel("weekly-report");
  }

  function startLiveExecution(
    agent: { id: string; name: string },
    assistantMessageId: string
  ) {
    setLiveExecution({
      agentId: agent.id,
      agentName: agent.name,
      assistantMessageId,
      activeStageIndex: 0,
      startedAt: Date.now(),
      durationSeconds: null,
      status: "running",
      mode: "live"
    });
  }

  function updateLiveExecution(event: { event: string }) {
    const stageIndex =
      event.event === "risk_data_loaded"
        ? 1
        : event.event === "ward_report_ready" ||
            event.event === "ward_report_fallback"
          ? 2
          : event.event === "batch_completed"
            ? 3
            : 0;
    setLiveExecution((current) =>
      current && current.mode === "live"
        ? {
            ...current,
            activeStageIndex: Math.max(current.activeStageIndex, stageIndex)
          }
        : current
    );
  }

  function finishLiveExecution(completed: boolean) {
    setLiveExecution((current) => {
      if (!current) {
        return current;
      }
      return completed
        ? {
            ...current,
            activeStageIndex: LIVE_REPORT_STAGES.length - 1,
            durationSeconds: (Date.now() - current.startedAt) / 1000,
            status: "finished"
          }
        : { ...current, status: "stopped" };
    });
  }

  function chooseAgent(agent: { id: string; name: string } | null) {
    const catalogAgent = agent
      ? (catalogQuery.data ?? []).find((item) => item.id === agent.id)
      : null;
    if (catalogAgent) {
      selectAgent(catalogAgent);
    } else {
      clearSelectedAgent();
    }
    if (agentSelectorRef.current) {
      agentSelectorRef.current.open = false;
    }
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const incoming = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (incoming.length === 0) {
      return;
    }

    const files = deduplicateFiles([...selectedFiles, ...incoming]);
    const validationError = validateSelectedFiles(files);
    if (validationError) {
      setErrorMessage(validationError);
      return;
    }
    setSelectedFiles(files);
    setErrorMessage(null);
  }

  function removeSelectedFile(fileToRemove: File) {
    setSelectedFiles((files) =>
      files.filter((file) => attachmentKey(file) !== attachmentKey(fileToRemove))
    );
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
        aria-busy={isTranscriptBusy}
      >
        <div className={styles.messageColumn}>
          {messages.length === 0 && !isTranscriptBusy ? (
            <div className={styles.emptyState}>
              <Bot size={28} />
              <h2>How can AX help?</h2>
              <p>Your transcript stays in this app until the page is reloaded.</p>
            </div>
          ) : (
            messages.map((message) => {
              const messageExecution =
                message.role === "assistant"
                  ? executions.find(
                      (execution) =>
                        execution.assistantMessageId === message.id
                    ) ?? null
                  : null;

              return (
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
                      {message.role === "user"
                        ? "You"
                        : messageExecution?.agentName ?? "AX"}
                    </strong>
                    {message.role === "user" ? (
                      <>
                        <p className={styles.plainText}>{message.content}</p>
                        {message.attachments && message.attachments.length > 0 && (
                          <AttachmentSummaryList attachments={message.attachments} />
                        )}
                      </>
                    ) : (
                      <>
                        {messageExecution && (
                          <MockExecutionTrace progress={messageExecution} />
                        )}
                        <ChatMarkdown content={message.content} />
                        {streamingMessageId === message.id && (
                          <span className={styles.streamCursor} aria-hidden />
                        )}
                        {messageExecution && (
                          <ExecutionCompletion progress={messageExecution} />
                        )}
                      </>
                    )}
                  </div>
                </article>
              );
            })
          )}

          {pendingExecution && (
            <article className={styles.assistantMessage} aria-live="polite">
              <span className={styles.avatar} aria-hidden>
                <Bot size={17} />
              </span>
              <div>
                <strong className={styles.speaker}>
                  {pendingExecution.agentName}
                </strong>
                <MockExecutionTrace progress={pendingExecution} />
              </div>
            </article>
          )}

          {isChatSending && !streamingMessageId && (
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
              {errorMessage}
            </p>
          )}
          {notice && (
            <p className={styles.notice} role="status">
              {notice}
            </p>
          )}
          {weeklyReportError && (
            <p className={styles.error} role="alert">
              {weeklyReportError}
            </p>
          )}
          {weeklyReportNotice && (
            <p className={styles.notice} role="status">
              {weeklyReportNotice}
            </p>
          )}
          <div ref={scrollAnchorRef} />
        </div>
      </section>

      <footer className={styles.composerArea}>
        {isWeeklyReporterRunning && (
          <div className={styles.weeklyRunControl} role="status">
            <span>Weekly Reporter is running in the background.</span>
            <button type="button" onClick={cancelWeeklyReport}>
              Cancel report
            </button>
          </div>
        )}
        <div className={styles.composerMode}>
          <details className={styles.agentSelector} ref={agentSelectorRef}>
            <summary aria-label="Choose an agent for Chat">
              <Bot size={16} aria-hidden />
              <span>{selectedAgent?.name ?? "AX Chat"}</span>
              <ChevronDown size={14} aria-hidden />
            </summary>
            <div
              className={styles.agentSelectorMenu}
              role="listbox"
              aria-label="Available agents"
            >
              <button
                className={
                  selectedAgent
                    ? styles.agentSelectorOption
                    : styles.agentSelectorOptionSelected
                }
                type="button"
                role="option"
                aria-selected={!selectedAgent}
                onClick={() => chooseAgent(null)}
              >
                <span>
                  <strong>No agent</strong>
                  <small>Normal AX Chat</small>
                </span>
                {!selectedAgent && <Check size={15} aria-hidden />}
              </button>

              {catalogQuery.isLoading && (
                <small className={styles.agentSelectorMessage}>
                  Loading agents…
                </small>
              )}
              {catalogQuery.isError && (
                <small className={styles.agentSelectorMessage}>
                  Agent catalog unavailable.
                </small>
              )}
              {(catalogQuery.data ?? []).map((agent) => {
                const isSelected = selectedAgent?.id === agent.id;
                return (
                  <button
                    className={
                      isSelected
                        ? styles.agentSelectorOptionSelected
                        : styles.agentSelectorOption
                    }
                    type="button"
                    role="option"
                    aria-selected={isSelected}
                    key={agent.id}
                    onClick={() => chooseAgent(agent)}
                  >
                    <span>
                      <strong>{agent.name}</strong>
                      <small>{agent.role}</small>
                    </span>
                    {isSelected && <Check size={15} aria-hidden />}
                  </button>
                );
              })}
            </div>
          </details>
        </div>
        <form
          className={styles.composer}
          ref={composerRef}
          onSubmit={sendMessage}
        >
          {slashMenuIsOpen && (
            <div
              className={styles.slashCommandMenu}
              id="slash-command-menu"
              role="listbox"
              aria-label="Slash commands"
            >
              <small className={styles.slashCommandMenuLabel}>Commands</small>
              {filteredSlashCommands.length > 0 ? (
                <div className={styles.slashCommandList}>
                  {filteredSlashCommands.map((command, index) => {
                    const isHighlighted =
                      index === highlightedSlashCommandIndex;
                    return (
                      <button
                        className={
                          isHighlighted
                            ? styles.slashCommandOptionHighlighted
                            : styles.slashCommandOption
                        }
                        id={`slash-command-${command.command.slice(1)}`}
                        key={command.command}
                        type="button"
                        role="option"
                        aria-selected={isHighlighted}
                        onMouseEnter={() =>
                          setHighlightedSlashCommandIndex(index)
                        }
                        onClick={() => selectSlashCommand(command)}
                      >
                        <code>{command.command}</code>
                        <span>{command.label}</span>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <small className={styles.slashCommandEmpty}>
                  No commands found
                </small>
              )}
            </div>
          )}

          <input
            ref={fileInputRef}
            className={styles.fileInput}
            type="file"
            accept={ATTACHMENT_ACCEPT}
            multiple
            disabled={isRagAgentSelected}
            onChange={handleFileChange}
          />

          {selectedFiles.length > 0 && (
            <div className={styles.attachmentList} aria-label="Selected attachments">
              {selectedFiles.map((file) => (
                <div className={styles.attachment} key={attachmentKey(file)}>
                  <FileText size={16} />
                  <span title={file.name}>{file.name}</span>
                  <small>{formatFileSize(file.size)}</small>
                  <button
                    type="button"
                    onClick={() => removeSelectedFile(file)}
                    aria-label={`Remove ${file.name}`}
                  >
                    <X size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}

          <button
            className={styles.attachButton}
            type="button"
            onClick={() => fileInputRef.current?.click()}
            aria-label={
              isRagAgentSelected
                ? "Attachments are unavailable for RAG Agent"
                : "Attach file"
            }
            disabled={isRagAgentSelected}
          >
            <Paperclip size={18} />
          </button>

          <textarea
            ref={composerInputRef}
            aria-label="Message AX"
            aria-autocomplete="list"
            aria-controls={slashMenuIsOpen ? "slash-command-menu" : undefined}
            aria-expanded={slashMenuIsOpen}
            aria-activedescendant={
              slashMenuIsOpen && filteredSlashCommands.length > 0
                ? `slash-command-${
                    filteredSlashCommands[
                      highlightedSlashCommandIndex
                    ]?.command.slice(1) ?? filteredSlashCommands[0].command.slice(1)
                  }`
                : undefined
            }
            placeholder="Message AX"
            rows={1}
            value={draft}
            onChange={(event) => handleDraftChange(event.target.value)}
            onKeyDown={handleComposerKeyDown}
          />

          {isChatSending ? (
            <button
              className={styles.cancelButton}
              type="button"
              onClick={cancelChatRequest}
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
        <small>
          {isRagAgentSelected
            ? "Enter to send · Shift+Enter for a new line · RAG Agent is text-only"
            : "Enter to send · Shift+Enter for a new line · Up to 5 files / 25 MB"}
        </small>
      </footer>
    </div>
  );
}

export function usesRagChat(graphId: string | null): boolean {
  return graphId === RAG_CHAT_GRAPH_ID;
}

function MockExecutionTrace({
  progress
}: {
  progress: ExecutionProgress;
}) {
  const isLive = isLiveExecution(progress);
  const stages = isLive ? LIVE_REPORT_STAGES : MOCK_AGENT_RUN_STAGES;
  return (
    <section
      className={styles.mockExecution}
      aria-label={`${isLive ? "Live" : "Frontend-only mock"} execution for ${progress.agentName}`}
      aria-live="polite"
    >
      <header className={styles.mockExecutionHeader}>
        <small
          title={
            isLive
              ? "Live Agent Server events"
              : "Simulated frontend events"
          }
        >
          {isLive ? "Live run" : "Mock execution"}
        </small>
      </header>
      <ol className={styles.mockStageList}>
        {stages.map((stage, index) => {
          const stageState = isLive
            ? getLiveStageState(progress, index)
            : getMockAgentRunStageState(progress, index);
          if (stageState === "pending") {
            return null;
          }
          const StageIcon =
            stageState === "completed"
              ? Check
              : LoaderCircle;

          return (
            <li className={styles[`mockStage${stageState}`]} key={stage}>
              <StageIcon size={15} aria-hidden />
              <span>{stage}{stageState === "active" ? "…" : ""}</span>
            </li>
          );
        })}
      </ol>
      {isLive && progress.status === "stopped" && (
        <small className={styles.mockExecutionStopped}>
          Run stopped before completion.
        </small>
      )}
      {!isLive && progress.status === "cancelled" && (
        <small className={styles.mockExecutionStopped}>
          Mock execution stopped before completion.
        </small>
      )}
      {!isLive && progress.status === "failed" && (
        <small className={styles.mockExecutionStopped}>
          Mock execution failed before completion.
        </small>
      )}
    </section>
  );
}

function ExecutionCompletion({
  progress
}: {
  progress: ExecutionProgress;
}) {
  const completed = isLiveExecution(progress)
    ? progress.status === "finished"
    : progress.status === "completed";
  if (!completed || progress.durationSeconds === null) {
    return null;
  }

  return (
    <div className={styles.mockExecutionComplete} role="status">
      <Check size={15} aria-hidden />
      <span>Completed in {progress.durationSeconds.toFixed(1)} sec</span>
    </div>
  );
}

function getLiveStageState(
  progress: LiveExecutionProgress,
  stageIndex: number
): "pending" | "active" | "completed" {
  if (progress.status === "finished" || stageIndex < progress.activeStageIndex) {
    return "completed";
  }
  if (
    progress.status === "running" &&
    stageIndex === progress.activeStageIndex
  ) {
    return "active";
  }
  return "pending";
}

function isLiveExecution(
  progress: ExecutionProgress
): progress is LiveExecutionProgress {
  return "mode" in progress && progress.mode === "live";
}

function getSlashQuery(value: string): string | null {
  const match = value.match(/^\/([^\s]*)$/);
  return match ? match[1].toLocaleLowerCase() : null;
}

function getMostRecentCompletedMonday(now = new Date()) {
  const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const daysSinceMonday = (monday.getDay() + 6) % 7;
  monday.setDate(monday.getDate() - daysSinceMonday - 7);
  const year = monday.getFullYear();
  const month = String(monday.getMonth() + 1).padStart(2, "0");
  const day = String(monday.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatWeeklyReportBatch(result: {
  week_start: string;
  week_end: string;
  reports: Array<{ markdown: string }>;
  warnings: string[];
}) {
  const reports = result.reports
    .map((report) => report.markdown.trim())
    .join("\n\n---\n\n");
  const warnings = result.warnings.length
    ? `\n\n## Run warnings\n\n${result.warnings
        .map((warning) => `- ${warning}`)
        .join("\n")}`
    : "";
  return `Weekly Reporter completed ${result.reports.length} ward reports for ${result.week_start} through ${result.week_end}.\n\n${reports}${warnings}`;
}

let messageSequence = 0;

function AttachmentSummaryList({
  attachments
}: {
  attachments: ChatAttachmentSummary[];
}) {
  return (
    <ul className={styles.messageAttachments} aria-label="Message attachments">
      {attachments.map((attachment) => (
        <li key={`${attachment.name}:${attachment.size}`}>
          <FileText size={14} aria-hidden />
          <span title={attachment.name}>{attachment.name}</span>
          <small>{formatFileSize(attachment.size)}</small>
        </li>
      ))}
    </ul>
  );
}

function validateSelectedFiles(files: File[]) {
  if (files.length > MAX_ATTACHMENT_COUNT) {
    return `Attach no more than ${MAX_ATTACHMENT_COUNT} files.`;
  }
  for (const file of files) {
    const extension = file.name.split(".").pop()?.toLocaleLowerCase() ?? "";
    if (!ACCEPTED_ATTACHMENT_EXTENSIONS.has(extension)) {
      return `${file.name} is not a supported attachment type.`;
    }
    if (file.size === 0) {
      return `${file.name} is empty.`;
    }
    if (file.size > MAX_ATTACHMENT_BYTES) {
      return `${file.name} exceeds the 10 MB per-file limit.`;
    }
  }
  const totalBytes = files.reduce((total, file) => total + file.size, 0);
  if (totalBytes > MAX_TOTAL_ATTACHMENT_BYTES) {
    return "Attachments exceed the 25 MB total limit.";
  }
  return null;
}

function deduplicateFiles(files: File[]) {
  return Array.from(
    new Map(files.map((file) => [attachmentKey(file), file])).values()
  );
}

function attachmentKey(file: File) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function toAttachmentSummary(file: File): ChatAttachmentSummary {
  return { name: file.name, size: file.size, type: file.type };
}

function formatFileSize(bytes: number) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${Math.ceil(bytes / 1024)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function createMessage(
  role: ChatRole,
  content: string,
  attachments?: ChatAttachmentSummary[]
) {
  return {
    id: createMessageId(),
    role,
    content,
    ...(attachments && attachments.length > 0 ? { attachments } : {})
  };
}

function createMessageId() {
  messageSequence += 1;
  return `${Date.now()}-${messageSequence}`;
}
