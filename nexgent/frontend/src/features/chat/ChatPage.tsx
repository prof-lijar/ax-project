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
} from "lucide-react"; // FileText, Paperclip, X added for file clip
import {
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
  useEffect,
  useRef,
  useState
} from "react"; // ChangeEvent added for file clip

import {
  AgentServerError,
  agentServerClient
} from "../../shared/api/agentServerClient";
import {
  useAgentCatalog,
  useAgentServerHealth
} from "../../shared/api/queries";
import {
  type ChatRole,
  useChatStore
} from "../../shared/state/useChatStore";
import { useUiStore } from "../../shared/state/useUiStore";
import { ChatMarkdown } from "./ChatMarkdown";
import styles from "./ChatPage.module.css";

const WEEKLY_REPORTER_GRAPH_ID = "ansimk_weekly_reporter";
const REPORT_TIMEZONE = "Asia/Seoul";
const MOCK_EXECUTION_STAGES = [
  "Planning request",
  "Reading relevant data",
  "Processing information",
  "Generating response"
] as const;
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

interface MockExecutionProgress {
  agentId: string;
  agentName: string;
  assistantMessageId: string;
  activeStageIndex: number;
  startedAt: number;
  durationSeconds: number | null;
  status: "running" | "finished" | "stopped";
  mode: "live" | "mock";
}

export function ChatPage() {
  const messages = useChatStore((state) => state.messages);
  const appendMessage = useChatStore((state) => state.appendMessage);
  const updateMessage = useChatStore((state) => state.updateMessage);
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
  const [selectedFile, setSelectedFile] = useState<File | null>(null); // Added for file clip
  const [isSending, setIsSending] = useState(false);
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(
    null
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [mockExecution, setMockExecution] =
    useState<MockExecutionProgress | null>(null);
  const [slashMenuDismissed, setSlashMenuDismissed] = useState(false);
  const [highlightedSlashCommandIndex, setHighlightedSlashCommandIndex] =
    useState(0);
  const fileInputRef = useRef<HTMLInputElement | null>(null); // Added for file clip
  const composerInputRef = useRef<HTMLTextAreaElement | null>(null);
  const agentSelectorRef = useRef<HTMLDetailsElement | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const mockExecutionTimerRef = useRef<number | null>(null);
  const requestInFlightRef = useRef(false);
  const handledAgentRunRef = useRef<string | null>(null);
  const scrollAnchorRef = useRef<HTMLDivElement | null>(null);
  const latestMessageContent = messages[messages.length - 1]?.content;
  const mockExecutionHasResponse =
    mockExecution !== null &&
    messages.some(
      (message) => message.id === mockExecution.assistantMessageId
    );
  const slashQuery = getSlashQuery(draft);
  const filteredSlashCommands =
    slashQuery === null
      ? []
      : MOCK_SLASH_COMMANDS.filter(({ command }) =>
          command.slice(1).startsWith(slashQuery)
        );
  const slashMenuIsOpen = slashQuery !== null && !slashMenuDismissed;

  useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView({
      behavior: isSending ? "auto" : "smooth"
    });
  }, [
    messages.length,
    latestMessageContent,
    isSending,
    errorMessage,
    notice,
    mockExecution?.activeStageIndex,
    mockExecution?.status
  ]);

  useEffect(
    () => () => {
      abortControllerRef.current?.abort();
      clearMockExecutionTimer();
    },
    []
  );

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
    if (requestInFlightRef.current) {
      setNotice("A request is already running. Try Run in Chat again when it finishes.");
      return;
    }

    const weekStart = getMostRecentCompletedMonday();
    const assistantMessageId = createMessageId();
    const controller = new AbortController();
    requestInFlightRef.current = true;
    abortControllerRef.current = controller;
    setIsSending(true);
    setErrorMessage(null);
    setNotice(null);
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
        { week_start: weekStart, timezone: REPORT_TIMEZONE },
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
        setNotice("Weekly Reporter run cancelled. You can start it again from Agents.");
      } else {
        setErrorMessage(
          error instanceof Error
            ? error.message
            : "The Weekly Reporter could not complete the run."
        );
        void healthQuery.refetch();
      }
    } finally {
      finishMockExecution(requestCompleted);
      abortControllerRef.current = null;
      requestInFlightRef.current = false;
      setIsSending(false);
    }
  }

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
    const userMessage = createMessage("user", message);
    appendMessage(userMessage);

    const controller = new AbortController();
    abortControllerRef.current = controller;
    const assistantMessageId = createMessageId();

    if (selectedAgent) {
      startMockExecution(selectedAgent, assistantMessageId);
    } else {
      clearMockExecution();
    }

    let assistantMessageStarted = false;
    let requestCompleted = false;

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
      requestCompleted = true;
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
      finishMockExecution(requestCompleted);
      abortControllerRef.current = null;
      requestInFlightRef.current = false;
      setStreamingMessageId(null);
      setIsSending(false);
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

  function cancelRequest() {
    abortControllerRef.current?.abort();
  }

  function clearMockExecutionTimer() {
    if (mockExecutionTimerRef.current !== null) {
      window.clearInterval(mockExecutionTimerRef.current);
      mockExecutionTimerRef.current = null;
    }
  }

  function clearMockExecution() {
    clearMockExecutionTimer();
    setMockExecution(null);
  }

  function startMockExecution(
    agent: { id: string; name: string },
    assistantMessageId: string
  ) {
    clearMockExecutionTimer();
    setMockExecution({
      agentId: agent.id,
      agentName: agent.name,
      assistantMessageId,
      activeStageIndex: 0,
      startedAt: Date.now(),
      durationSeconds: null,
      status: "running",
      mode: "mock"
    });
    mockExecutionTimerRef.current = window.setInterval(() => {
      setMockExecution((current) => {
        if (!current || current.status !== "running") {
          return current;
        }
        const lastRunningStageIndex = MOCK_EXECUTION_STAGES.length - 1;
        if (current.activeStageIndex >= lastRunningStageIndex) {
          return current;
        }
        return {
          ...current,
          activeStageIndex: current.activeStageIndex + 1
        };
      });
    }, 700);
  }

  function startLiveExecution(
    agent: { id: string; name: string },
    assistantMessageId: string
  ) {
    clearMockExecutionTimer();
    setMockExecution({
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
    setMockExecution((current) =>
      current && current.mode === "live"
        ? {
            ...current,
            activeStageIndex: Math.max(current.activeStageIndex, stageIndex)
          }
        : current
    );
  }

  function finishMockExecution(completed: boolean) {
    clearMockExecutionTimer();
    setMockExecution((current) => {
      if (!current) {
        return current;
      }
      return completed
        ? {
            ...current,
            activeStageIndex: MOCK_EXECUTION_STAGES.length - 1,
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

  // Added for file clip
  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setSelectedFile(file);
  }

  // Added for file clip
  function removeSelectedFile() {
    setSelectedFile(null);

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
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
            messages.map((message) => {
              const messageExecution =
                message.role === "assistant" &&
                mockExecution?.assistantMessageId === message.id
                  ? mockExecution
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
                      <p className={styles.plainText}>{message.content}</p>
                    ) : (
                      <>
                        {messageExecution && (
                          <MockExecutionTrace progress={messageExecution} />
                        )}
                        <ChatMarkdown content={message.content} />
                        {streamingMessageId === message.id && (
                          <span className={styles.streamCursor} aria-hidden />
                        )}
                      </>
                    )}
                  </div>
                </article>
              );
            })
          )}

          {mockExecution && !mockExecutionHasResponse && (
            <article className={styles.assistantMessage} aria-live="polite">
              <span className={styles.avatar} aria-hidden>
                <Bot size={17} />
              </span>
              <div>
                <strong className={styles.speaker}>
                  {mockExecution.agentName}
                </strong>
                <MockExecutionTrace progress={mockExecution} />
              </div>
            </article>
          )}

          {isSending && !streamingMessageId && !mockExecution && (
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
        <form className={styles.composer} onSubmit={sendMessage}>
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
            onChange={handleFileChange}
          />

          {selectedFile && (
            <div className={styles.attachment}>
              <FileText size={16} />
              <span title={selectedFile.name}>{selectedFile.name}</span>
              <button
                type="button"
                onClick={removeSelectedFile}
                aria-label={`Remove ${selectedFile.name}`}
              >
                <X size={14} />
              </button>
            </div>
          )}

          <button
            className={styles.attachButton}
            type="button"
            onClick={() => fileInputRef.current?.click()}
            aria-label="Attach file"
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

function MockExecutionTrace({
  progress
}: {
  progress: MockExecutionProgress;
}) {
  const stages =
    progress.mode === "live" ? LIVE_REPORT_STAGES : MOCK_EXECUTION_STAGES;
  return (
    <section
      className={styles.mockExecution}
      aria-label={`${progress.mode === "live" ? "Live" : "Frontend-only mock"} execution for ${progress.agentName}`}
      aria-live="polite"
    >
      <header className={styles.mockExecutionHeader}>
        <small
          title={
            progress.mode === "live"
              ? "Live Agent Server events"
              : "Simulated frontend events"
          }
        >
          {progress.mode === "live" ? "Live run" : "Mock execution"}
        </small>
      </header>
      <ol className={styles.mockStageList}>
        {stages.map((stage, index) => {
          const stageState = getMockStageState(progress, index);
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
        {progress.status === "finished" && progress.durationSeconds !== null && (
          <li className={styles.mockExecutionComplete}>
            <Check size={15} aria-hidden />
            <span>Completed in {progress.durationSeconds.toFixed(1)} sec</span>
          </li>
        )}
      </ol>
      {progress.status === "stopped" && (
        <small className={styles.mockExecutionStopped}>
          {progress.mode === "live" ? "Run" : "Mock execution"} stopped before
          completion.
        </small>
      )}
    </section>
  );
}

function getMockStageState(
  progress: MockExecutionProgress,
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
