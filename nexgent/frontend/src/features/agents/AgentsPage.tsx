import { Bot, CircleAlert, MessageSquare } from "lucide-react";
import type { MouseEvent } from "react";

import { useAgentCatalog } from "../../shared/api/queries";
import { Badge } from "../../shared/components/Badge";
import {
  navigateToAgentDetail,
  navigateToSection
} from "../../shared/navigation/sections";
import { useUiStore } from "../../shared/state/useUiStore";
import type { AgentDefinition, AgentReadiness } from "../../shared/types/agents";
import styles from "./AgentsPage.module.css";

interface AgentsPageViewProps {
  agents: AgentDefinition[];
  search: string;
  isLoading?: boolean;
  isError?: boolean;
}

export function AgentsPage() {
  const catalogQuery = useAgentCatalog();
  const search = useUiStore((state) => state.search);

  return (
    <AgentsPageView
      agents={catalogQuery.data ?? []}
      search={search}
      isLoading={catalogQuery.isLoading}
      isError={catalogQuery.isError}
    />
  );
}

export function AgentsPageView({
  agents,
  search,
  isLoading = false,
  isError = false
}: AgentsPageViewProps) {
  const selectedAgent = useUiStore((state) => state.selectedAgent);
  const visibleAgents = filterAgents(agents, search);
  const hasPreviewAgents = agents.some(
    (agent) => agent.observationMode === "preview"
  );

  function openAgentDetail(
    event: MouseEvent<HTMLElement>,
    agent: AgentDefinition
  ) {
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
    navigateToAgentDetail(agent.id);
  }

  function openAgentInChat(
    event: MouseEvent<HTMLButtonElement>,
    agent: AgentDefinition
  ) {
    event.stopPropagation();
    prepareAgentChatSelection(agent);
    navigateToSection("chat");
  }

  return (
    <section className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <h1>Agents</h1>
          <p>Open and monitor the agents that work alongside your team.</p>
        </div>
        {hasPreviewAgents && <Badge tone="amber">Preview data</Badge>}
      </header>

      {hasPreviewAgents && (
        <div className={styles.previewNotice} role="note">
          <CircleAlert size={17} aria-hidden />
          <span>
            Status and run history are samples. Live Agent Server monitoring
            will be connected with the first agent integration.
          </span>
        </div>
      )}

      <section className={styles.catalog} aria-labelledby="agent-catalog-title">
        <header className={styles.catalogHeader}>
          <div>
            <h2 id="agent-catalog-title">Your agents</h2>
            <p>{visibleAgents.length} available to inspect</p>
          </div>
        </header>

        {isLoading && <CatalogMessage>Loading agent catalog…</CatalogMessage>}
        {isError && (
          <CatalogMessage>
            Agent information is unavailable. Refresh the workspace to try
            again.
          </CatalogMessage>
        )}
        {!isLoading && !isError && visibleAgents.length === 0 && (
          <CatalogMessage>
            {agents.length === 0
              ? "No agents are connected yet."
              : "No agents match your workspace search."}
          </CatalogMessage>
        )}

        {visibleAgents.length > 0 && (
          <div className={styles.agentList} role="list" aria-label="Agents">
            {visibleAgents.map((agent) => {
              const readiness = agent.readiness
                ? getReadinessPresentation(agent.readiness)
                : null;
              const isSelectedForChat = agent.id === selectedAgent?.id;

              return (
                <article
                  className={
                    isSelectedForChat
                      ? styles.agentCardSelected
                      : styles.agentCard
                  }
                  key={agent.id}
                  role="listitem"
                  onClick={(event) => openAgentDetail(event, agent)}
                >
                  <a
                    className={styles.agentCardBody}
                    href={`/agents/${encodeURIComponent(agent.id)}`}
                  >
                    <span className={styles.agentCardHeader}>
                      <span className={styles.agentIdentity}>
                        <span className={styles.agentAvatar} aria-hidden>
                          <Bot size={22} />
                        </span>
                        <span>
                          <strong>{agent.name}</strong>
                          <small>{agent.role}</small>
                        </span>
                      </span>
                      {readiness && (
                        <Badge tone={readiness.tone}>{readiness.label}</Badge>
                      )}
                    </span>
                    <span className={styles.cardDescription}>
                      {agent.description}
                    </span>
                    {agent.currentWork && (
                      <span className={styles.currentWork}>
                        <small>Current work</small>
                        <span>{agent.currentWork}</span>
                      </span>
                    )}
                  </a>

                  <footer className={styles.cardFooter}>
                    <span className={styles.cardMetadata}>
                      <Badge>{agent.runtimeLabel}</Badge>
                      {agent.observationMode !== null && (
                        <span>{agent.recentRuns.length} runs</span>
                      )}
                    </span>
                    {agent.canRunInChat && (
                      <button
                        className={styles.runInChatButton}
                        type="button"
                        onClick={(event) => openAgentInChat(event, agent)}
                      >
                        <MessageSquare size={15} aria-hidden />
                        Chat
                      </button>
                    )}
                  </footer>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </section>
  );
}

export function prepareAgentChatSelection(agent: AgentDefinition) {
  const { clearPendingAgentRun, selectAgent } = useUiStore.getState();
  clearPendingAgentRun();
  selectAgent(agent);
}

function CatalogMessage({ children }: { children: string }) {
  return <div className={styles.catalogMessage}>{children}</div>;
}

export function filterAgents(agents: AgentDefinition[], search: string) {
  const normalizedSearch = search.trim().toLocaleLowerCase();
  if (!normalizedSearch) {
    return agents;
  }

  return agents.filter((agent) =>
    [
      agent.name,
      agent.role,
      agent.description,
      agent.graphId,
      agent.currentWork ?? "",
      ...agent.capabilities
    ]
      .join(" ")
      .toLocaleLowerCase()
      .includes(normalizedSearch)
  );
}

export function getReadinessPresentation(readiness: AgentReadiness) {
  const presentations = {
    ready: { label: "Ready", tone: "green" },
    degraded: { label: "Needs attention", tone: "amber" },
    offline: { label: "Offline", tone: "red" },
    draft: { label: "Draft", tone: "neutral" }
  } as const;
  return presentations[readiness];
}
