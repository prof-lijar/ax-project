import {
  ArrowLeft,
  Bot,
  Check,
  Circle,
  LoaderCircle,
  MessageSquare,
  Square
} from "lucide-react";
import type { MouseEvent } from "react";

import { useAgentCatalog } from "../../shared/api/queries";
import { Badge } from "../../shared/components/Badge";
import { navigateToSection } from "../../shared/navigation/sections";
import {
  getMockAgentRunStageState,
  MOCK_AGENT_RUN_STAGES,
  type MockAgentRun,
  type MockAgentRunStatus,
  useAgentRunStore
} from "../../shared/state/useAgentRunStore";
import { useUiStore } from "../../shared/state/useUiStore";
import type { AgentDefinition } from "../../shared/types/agents";
import {
  getReadinessPresentation,
  prepareAgentChatSelection
} from "./AgentsPage";
import styles from "./AgentDetailPage.module.css";

interface AgentDetailPageProps {
  agentId: string;
}

interface AgentDetailPageViewProps {
  agent: AgentDefinition | null;
  run?: MockAgentRun | null;
  latestRun?: MockAgentRun | null;
  isLoading?: boolean;
  isError?: boolean;
  onBack?: (event: MouseEvent<HTMLAnchorElement>) => void;
  onRunInChat?: (agent: AgentDefinition) => void;
  onStopRun?: () => void;
}

export function AgentDetailPage({ agentId }: AgentDetailPageProps) {
  const catalogQuery = useAgentCatalog();
  const run = useAgentRunStore((state) => state.runsByAgentId[agentId] ?? null);
  const latestRun = useAgentRunStore(
    (state) => state.latestRunsByAgentId[agentId] ?? null
  );
  const cancelRun = useAgentRunStore((state) => state.cancelRun);
  const agent =
    (catalogQuery.data ?? []).find((item) => item.id === agentId) ?? null;

  function backToAgents(event: MouseEvent<HTMLAnchorElement>) {
    if (
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    ) {
      return;
    }
    event.preventDefault();
    navigateToSection("agents");
  }

  function openAgentInChat(selectedAgent: AgentDefinition) {
    prepareAgentChatSelection(selectedAgent);
    navigateToSection("chat");
  }

  return (
    <AgentDetailPageView
      agent={agent}
      run={run}
      latestRun={latestRun}
      isLoading={catalogQuery.isLoading}
      isError={catalogQuery.isError}
      onBack={backToAgents}
      onRunInChat={openAgentInChat}
      onStopRun={() => cancelRun(agentId)}
    />
  );
}

export function AgentDetailPageView({
  agent,
  run = null,
  latestRun = null,
  isLoading = false,
  isError = false,
  onBack,
  onRunInChat,
  onStopRun
}: AgentDetailPageViewProps) {
  return (
    <section className={styles.page}>
      <a className={styles.backLink} href="/agents" onClick={onBack}>
        <ArrowLeft size={16} aria-hidden />
        Back to Agents
      </a>

      {isLoading && (
        <DetailMessage title="Loading agent details…">
          The agent catalog is being prepared.
        </DetailMessage>
      )}

      {isError && (
        <DetailMessage title="Agent information is unavailable">
          Return to Agents and refresh the workspace to try again.
        </DetailMessage>
      )}

      {!isLoading && !isError && !agent && (
        <DetailMessage title="Agent not found">
          This agent is not available in the current catalog.
        </DetailMessage>
      )}

      {!isLoading && !isError && agent && (
        <AgentDetails
          agent={agent}
          run={run}
          latestRun={latestRun}
          onRunInChat={onRunInChat}
          onStopRun={onStopRun}
        />
      )}
    </section>
  );
}

function DetailMessage({
  title,
  children
}: {
  title: string;
  children: string;
}) {
  return (
    <div className={styles.detailMessage} role="status">
      <Bot size={24} aria-hidden />
      <strong>{title}</strong>
      <span>{children}</span>
    </div>
  );
}

function AgentDetails({
  agent,
  run,
  latestRun,
  onRunInChat,
  onStopRun
}: {
  agent: AgentDefinition;
  run: MockAgentRun | null;
  latestRun: MockAgentRun | null;
  onRunInChat?: (agent: AgentDefinition) => void;
  onStopRun?: () => void;
}) {
  const readiness = getReadinessPresentation(agent.readiness);
  const currentRun = run?.status === "running" ? run : null;

  return (
    <article className={styles.details} aria-label={`${agent.name} details`}>
      <header className={styles.detailsHeader}>
        <span className={styles.detailsIcon} aria-hidden>
          <Bot size={24} />
        </span>
        <div className={styles.detailsTitleRow}>
          <h1>{agent.name}</h1>
          <Badge tone={agent.observationMode === "live" ? "green" : "amber"}>
            {agent.observationMode === "live" ? "Live data" : "Preview data"}
          </Badge>
        </div>
        <div className={styles.headerStatus}>
          <Badge tone={readiness.tone}>{readiness.label}</Badge>
        </div>
        <p className={styles.detailsSubtitle}>{agent.role}</p>
        <p className={styles.description}>{agent.description}</p>
        <button
          className={styles.runInChatButton}
          type="button"
          onClick={() => onRunInChat?.(agent)}
        >
          <MessageSquare size={16} aria-hidden />
          Run in Chat
        </button>
      </header>

      <CurrentRun run={currentRun} onStopRun={onStopRun} />
      <LatestRun
        agent={agent}
        run={latestRun}
        onRunInChat={onRunInChat}
      />
    </article>
  );
}

function CurrentRun({
  run,
  onStopRun
}: {
  run: MockAgentRun | null;
  onStopRun?: () => void;
}) {
  const status = run ? getMockRunStatusPresentation(run.status) : null;

  return (
    <section className={styles.currentRun} aria-live="polite">
      <header className={styles.currentRunHeader}>
        <h2>Current run</h2>
        {status && <Badge tone={status.tone}>{status.label}</Badge>}
      </header>

      {!run ? (
        <p className={styles.noCurrentRun}>No active mock run.</p>
      ) : (
        <div className={styles.currentRunBody}>
          <p className={styles.runPrompt}>{run.prompt}</p>
          <ol className={styles.runStages}>
            {MOCK_AGENT_RUN_STAGES.map((stage, index) => {
              const stageState = getMockAgentRunStageState(run, index);
              const StageIcon =
                stageState === "completed"
                  ? Check
                  : stageState === "active"
                    ? LoaderCircle
                    : Circle;
              return (
                <li className={styles[`runStage${stageState}`]} key={stage}>
                  <StageIcon size={15} aria-hidden />
                  <span>{stage}{stageState === "active" ? "…" : ""}</span>
                </li>
              );
            })}
          </ol>
          <div className={styles.runFooter}>
            <small>{formatRunTiming(run)}</small>
            {run.status === "running" && (
              <button
                className={styles.stopRunButton}
                type="button"
                onClick={onStopRun}
              >
                <Square size={13} fill="currentColor" aria-hidden />
                Stop
              </button>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

function LatestRun({
  agent,
  run,
  onRunInChat
}: {
  agent: AgentDefinition;
  run: MockAgentRun | null;
  onRunInChat?: (agent: AgentDefinition) => void;
}) {
  const terminalRun = run && run.status !== "running" ? run : null;
  const status = terminalRun
    ? getMockRunStatusPresentation(terminalRun.status)
    : null;

  return (
    <section className={styles.latestRun}>
      <header className={styles.latestRunHeader}>
        <h2>Latest run</h2>
        {status && <Badge tone={status.tone}>{status.label}</Badge>}
      </header>

      {!terminalRun ? (
        <p className={styles.noLatestRun}>No previous mock run.</p>
      ) : (
        <div className={styles.latestRunBody}>
          <p className={styles.runPrompt}>{terminalRun.prompt}</p>
          <div className={styles.latestRunFooter}>
            <div className={styles.latestRunMetadata}>
              <span>{formatTerminalRunDuration(terminalRun)}</span>
              <time dateTime={formatFinishedDateTime(terminalRun)}>
                Finished {formatFinishedAt(terminalRun)}
              </time>
            </div>
            <button
              className={styles.latestRunAction}
              type="button"
              onClick={() => onRunInChat?.(agent)}
            >
              <MessageSquare size={14} aria-hidden />
              {terminalRun.status === "failed"
                ? "Retry in Chat"
                : "Run again in Chat"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function getMockRunStatusPresentation(status: MockAgentRunStatus) {
  const presentations = {
    running: { label: "Running", tone: "blue" },
    completed: { label: "Completed", tone: "green" },
    cancelled: { label: "Cancelled", tone: "neutral" },
    failed: { label: "Failed", tone: "red" }
  } as const;
  return presentations[status];
}

function formatRunTiming(run: MockAgentRun) {
  const durationSeconds =
    run.durationSeconds ?? Math.max(0, (Date.now() - run.startedAt) / 1000);
  return `Running for ${formatDuration(durationSeconds)}`;
}

function formatTerminalRunDuration(run: MockAgentRun) {
  const duration = formatDuration(run.durationSeconds ?? 0);
  return run.status === "completed"
    ? `Completed in ${duration}`
    : `Duration ${duration}`;
}

function formatDuration(durationSeconds: number) {
  const minutes = Math.floor(durationSeconds / 60);
  const seconds = Math.floor(durationSeconds % 60);
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function formatFinishedDateTime(run: MockAgentRun) {
  return new Date(run.completedAt ?? run.startedAt).toISOString();
}

function formatFinishedAt(run: MockAgentRun) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(run.completedAt ?? run.startedAt));
}
