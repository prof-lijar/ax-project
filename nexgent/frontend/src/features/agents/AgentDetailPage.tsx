import {
  ArrowLeft,
  Bot,
  Braces,
  CalendarClock,
  Clock3,
  MessageSquare,
  Workflow
} from "lucide-react";
import type { MouseEvent, ReactNode } from "react";

import { useAgentCatalog } from "../../shared/api/queries";
import { Badge } from "../../shared/components/Badge";
import { navigateToSection } from "../../shared/navigation/sections";
import { useUiStore } from "../../shared/state/useUiStore";
import type {
  AgentDefinition,
  AgentRunStatus
} from "../../shared/types/agents";
import { getReadinessPresentation } from "./AgentsPage";
import styles from "./AgentDetailPage.module.css";

interface AgentDetailPageProps {
  agentId: string;
}

interface AgentDetailPageViewProps {
  agent: AgentDefinition | null;
  isLoading?: boolean;
  isError?: boolean;
  onBack?: (event: MouseEvent<HTMLAnchorElement>) => void;
  onRunInChat?: (agent: AgentDefinition) => void;
}

export function AgentDetailPage({ agentId }: AgentDetailPageProps) {
  const catalogQuery = useAgentCatalog();
  const requestAgentRun = useUiStore((state) => state.requestAgentRun);
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
    requestAgentRun(selectedAgent);
    navigateToSection("chat");
  }

  return (
    <AgentDetailPageView
      agent={agent}
      isLoading={catalogQuery.isLoading}
      isError={catalogQuery.isError}
      onBack={backToAgents}
      onRunInChat={openAgentInChat}
    />
  );
}

export function AgentDetailPageView({
  agent,
  isLoading = false,
  isError = false,
  onBack,
  onRunInChat
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
        <AgentDetails agent={agent} onRunInChat={onRunInChat} />
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
  onRunInChat
}: {
  agent: AgentDefinition;
  onRunInChat?: (agent: AgentDefinition) => void;
}) {
  const readiness = getReadinessPresentation(agent.readiness);

  return (
    <article className={styles.details} aria-label={`${agent.name} details`}>
      <header className={styles.detailsHeader}>
        <span className={styles.detailsIcon} aria-hidden>
          <Bot size={24} />
        </span>
        <div className={styles.detailsTitle}>
          <div>
            <h1>{agent.name}</h1>
            <Badge tone={agent.observationMode === "live" ? "green" : "amber"}>
              {agent.observationMode === "live" ? "Live data" : "Preview data"}
            </Badge>
          </div>
          <p>{agent.role}</p>
        </div>
        <Badge tone={readiness.tone}>{readiness.label}</Badge>
      </header>

      <p className={styles.description}>{agent.description}</p>

      <div className={styles.detailsActions}>
        <button
          className={styles.runInChatButton}
          type="button"
          onClick={() => onRunInChat?.(agent)}
        >
          <MessageSquare size={16} aria-hidden />
          Run in Chat
        </button>
      </div>

      <dl className={styles.factGrid}>
        <div>
          <dt>
            <Workflow size={15} aria-hidden /> Graph ID
          </dt>
          <dd>
            <code>{agent.graphId}</code>
          </dd>
        </div>
        <div>
          <dt>
            <Braces size={15} aria-hidden /> Runtime
          </dt>
          <dd>{agent.runtimeLabel}</dd>
        </div>
        <div>
          <dt>
            <Clock3 size={15} aria-hidden /> Last observed
          </dt>
          <dd>{formatObservedAt(agent.lastObservedAt)}</dd>
        </div>
      </dl>

      <DetailSection title="Capabilities">
        <div className={styles.capabilities}>
          {agent.capabilities.map((capability) => (
            <Badge key={capability}>{capability}</Badge>
          ))}
        </div>
      </DetailSection>

      <DetailSection title="Contract">
        <div className={styles.contractList}>
          {agent.inputs.map((input) => (
            <div key={input.name}>
              <code>{input.name}</code>
              <span>{input.description}</span>
              <small>{input.required ? "Required" : "Optional"}</small>
            </div>
          ))}
          <div>
            <strong>Output</strong>
            <span>{agent.outputDescription}</span>
          </div>
        </div>
      </DetailSection>

      <DetailSection title="Configuration">
        <dl className={styles.configuration}>
          {agent.configuration.map((item) => (
            <div key={item.label}>
              <dt>{item.label}</dt>
              <dd>{item.value}</dd>
            </div>
          ))}
        </dl>
      </DetailSection>

      <DetailSection title="Current limitations">
        <ul className={styles.limitations}>
          {agent.limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
      </DetailSection>

      <DetailSection title="Recent runs" detail="Sample history">
        {agent.recentRuns.length === 0 ? (
          <p className={styles.noRuns}>No sample runs yet.</p>
        ) : (
          <div className={styles.runList}>
            {agent.recentRuns.map((run) => {
              const status = getRunStatusPresentation(run.status);
              return (
                <article className={styles.runItem} key={run.id}>
                  <div className={styles.runHeading}>
                    <span>
                      <CalendarClock size={16} aria-hidden />
                      <strong>{formatObservedAt(run.startedAt)}</strong>
                    </span>
                    <Badge tone={status.tone}>{status.label}</Badge>
                  </div>
                  <p>{run.resultSummary}</p>
                  <small>
                    {run.trigger} · {run.duration} · {run.warningCount} warnings
                  </small>
                </article>
              );
            })}
          </div>
        )}
      </DetailSection>
    </article>
  );
}

function DetailSection({
  title,
  detail,
  children
}: {
  title: string;
  detail?: string;
  children: ReactNode;
}) {
  return (
    <section className={styles.detailSection}>
      <header>
        <h2>{title}</h2>
        {detail && <span>{detail}</span>}
      </header>
      {children}
    </section>
  );
}

export function getRunStatusPresentation(status: AgentRunStatus) {
  const presentations = {
    queued: { label: "Queued", tone: "amber" },
    running: { label: "Running", tone: "blue" },
    completed: { label: "Completed", tone: "green" },
    failed: { label: "Failed", tone: "red" },
    cancelled: { label: "Cancelled", tone: "neutral" }
  } as const;
  return presentations[status];
}

function formatObservedAt(value: string | null) {
  if (!value) {
    return "Not observed";
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}
