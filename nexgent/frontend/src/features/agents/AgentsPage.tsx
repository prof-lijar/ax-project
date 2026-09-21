import {
  ArrowRight,
  BookOpen,
  CircleAlert,
  FileBarChart,
  MessageSquare,
  Search,
  SearchX,
  Telescope,
  UsersRound,
  X
} from "lucide-react";
import { useRef, useState, type MouseEvent } from "react";

import {
  RAG_CHAT_AGENT_ID,
  SCOUT_AGENT_ID,
  SUMIN_AGENT_ID,
  WEEKLY_REPORTER_AGENT_ID
} from "../../shared/api/agentCatalogClient";
import { useAgentCatalog } from "../../shared/api/queries";
import { Badge } from "../../shared/components/Badge";
import {
  navigateToAgentDetail,
  navigateToSection
} from "../../shared/navigation/sections";
import { useUiStore } from "../../shared/state/useUiStore";
import type {
  AgentDefinition,
  AgentReadiness
} from "../../shared/types/agents";
import styles from "./AgentsPage.module.css";

interface AgentsPageViewProps {
  agents: AgentDefinition[];
  search: string;
  onSearchChange?: (value: string) => void;
  onRetry?: () => void;
  isLoading?: boolean;
  isError?: boolean;
  isRetrying?: boolean;
}

export function AgentsPage() {
  const catalogQuery = useAgentCatalog();
  const [search, setSearch] = useState("");
  return (
    <AgentsPageView
      agents={catalogQuery.data ?? []}
      search={search}
      onSearchChange={setSearch}
      onRetry={() => void catalogQuery.refetch()}
      isLoading={catalogQuery.isLoading}
      isError={catalogQuery.isError}
      isRetrying={catalogQuery.isFetching}
    />
  );
}

// Product copy belongs to this presentation layer, not the shared catalog/API.
export function getAgentPresentation(agent: AgentDefinition) {
  switch (agent.id) {
    case WEEKLY_REPORTER_AGENT_ID:
      return {
        icon: FileBarChart,
        specialty: "Reporting",
        description: "Turn weekly ward activity into clear risk reports.",
        capabilities: [
          "Review ward risk and activity",
          "Download reports as a ZIP"
        ],
        tone: "reporting"
      };
    case RAG_CHAT_AGENT_ID:
      return {
        icon: BookOpen,
        specialty: "Knowledge",
        description:
          "Find answers in your indexed knowledge, with sources to check.",
        capabilities: [
          "Ask about indexed documents",
          "Follow sources in each answer"
        ],
        tone: "knowledge"
      };
    case SCOUT_AGENT_ID:
      return {
        icon: Telescope,
        specialty: "Research",
        description:
          "Explore a topic on the web and bring the findings together.",
        capabilities: [
          "Search and review web sources",
          "Create a sourced research report"
        ],
        tone: "research"
      };
    case SUMIN_AGENT_ID:
      return {
        icon: MessageSquare,
        specialty: "Slack files",
        description:
          "Keep channel uploads organized and find them again from a mention.",
        capabilities: [
          "Archive Slack files in Nextcloud",
          "Find uploads from names and context"
        ],
        tone: "knowledge"
      };
    default:
      return {
        icon: UsersRound,
        specialty: agent.role,
        description: agent.description,
        capabilities: agent.capabilities.slice(0, 2),
        tone: "neutral"
      };
  }
}

export function AgentsPageView({
  agents,
  search,
  onSearchChange,
  onRetry,
  isLoading = false,
  isError = false,
  isRetrying = false
}: AgentsPageViewProps) {
  const selectedAgent = useUiStore((state) => state.selectedAgent);
  const searchRef = useRef<HTMLInputElement>(null);
  const visibleAgents = filterAgents(agents, search);
  const hasPreviewAgents = agents.some(
    (agent) => agent.observationMode === "preview"
  );
  const showCatalog = !isLoading && !isError;
  function openAgentDetail(
    event: MouseEvent<HTMLAnchorElement>,
    agent: AgentDefinition
  ) {
    if (
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    )
      return;
    event.preventDefault();
    navigateToAgentDetail(agent.id);
  }
  function openAgentInChat(agent: AgentDefinition) {
    prepareAgentChatSelection(agent);
    navigateToSection("chat");
  }
  function clearSearch() {
    onSearchChange?.("");
    searchRef.current?.focus();
  }
  return (
    <section className={styles.page} aria-labelledby="coworkers-title">
      <header className={styles.pageHeader}>
        <div>
          <h1 id="coworkers-title">Your co-workers</h1>
          <p>
            Choose a co-worker. Open their workspace or start a conversation.
          </p>
        </div>
      </header>
      <div className={styles.catalogTools}>
        <p className={styles.resultCount} role="status">
          {isLoading
            ? "Loading co-workers…"
            : isError
              ? "Couldn't load co-workers"
              : search.trim()
                ? `${visibleAgents.length} of ${agents.length} co-workers`
                : `${agents.length} co-worker${agents.length === 1 ? "" : "s"}`}
        </p>
        <div className={styles.searchBox}>
          <Search size={17} aria-hidden />
          <input
            ref={searchRef}
            aria-label="Find a co-worker"
            placeholder="Find a co-worker…"
            type="search"
            value={search}
            readOnly={!onSearchChange}
            onChange={(event) => onSearchChange?.(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") clearSearch();
            }}
          />
          {search && (
            <button
              type="button"
              aria-label="Clear search"
              title="Clear search"
              onClick={clearSearch}
            >
              <X size={15} />
            </button>
          )}
        </div>
      </div>
      {hasPreviewAgents && (
        <p className={styles.previewNotice}>
          <CircleAlert size={16} aria-hidden />
          <span>
            Preview data is marked on each sample co-worker. Their status and
            activity are examples.
          </span>
        </p>
      )}
      {isLoading && (
        <div className={styles.agentList} aria-hidden>
          {[0, 1, 2].map((index) => (
            <div key={index} className={styles.skeletonCard}>
              <span />
              <span />
              <span />
              <span />
            </div>
          ))}
        </div>
      )}
      {isError && (
        <div className={styles.catalogMessage} role="alert">
          <CircleAlert size={25} aria-hidden />
          <h2>Co-workers are unavailable</h2>
          <p>Try loading your team again.</p>
          {onRetry && (
            <button
              type="button"
              className={styles.secondaryAction}
              onClick={onRetry}
              disabled={isRetrying}
            >
              {isRetrying ? "Trying again…" : "Try again"}
            </button>
          )}
        </div>
      )}
      {showCatalog && visibleAgents.length === 0 && (
        <div className={styles.catalogMessage}>
          {agents.length ? (
            <SearchX size={26} aria-hidden />
          ) : (
            <UsersRound size={26} aria-hidden />
          )}
          <h2>{agents.length ? "No co-workers found" : "No co-workers yet"}</h2>
          <p>
            {agents.length
              ? "Try a name, a role, or the work you need help with."
              : "Connected co-workers will appear here."}
          </p>
          {search && onSearchChange && (
            <button
              type="button"
              className={styles.secondaryAction}
              onClick={clearSearch}
            >
              Clear search
            </button>
          )}
        </div>
      )}
      {showCatalog && visibleAgents.length > 0 && (
        <div className={styles.agentList} role="list" aria-label="Co-workers">
          {visibleAgents.map((agent) => {
            const presentation = getAgentPresentation(agent);
            const Icon = presentation.icon;
            const readiness = agent.readiness
              ? getReadinessPresentation(agent.readiness)
              : null;
            const selected =
              agent.canRunInChat && agent.id === selectedAgent?.id;
            const contextLabel = selected
              ? "Selected in Chat"
              : agent.canRunInChat
                ? "Available in Chat"
                : agent.id === SUMIN_AGENT_ID
                  ? "Works in Slack"
                  : "Dedicated workspace";
            const href = `/agents/${encodeURIComponent(agent.id)}`;
            return (
              <article
                className={styles.agentCard}
                key={agent.id}
                role="listitem"
                aria-labelledby={`coworker-${agent.id}`}
              >
                <div className={styles.cardTop}>
                  <span
                    className={`${styles.agentAvatar} ${styles[presentation.tone]}`}
                    aria-hidden
                  >
                    <Icon size={23} strokeWidth={1.7} />
                  </span>
                  <div className={styles.cardStatus}>
                    {agent.observationMode === "preview" && (
                      <Badge tone="amber">Preview data</Badge>
                    )}
                    {readiness && (
                      <Badge tone={readiness.tone}>{readiness.label}</Badge>
                    )}
                  </div>
                </div>
                <div className={styles.cardIdentity}>
                  <p className={styles.specialty}>{presentation.specialty}</p>
                  <h2 id={`coworker-${agent.id}`}>
                    <a
                      href={href}
                      onClick={(event) => openAgentDetail(event, agent)}
                    >
                      {agent.name}
                    </a>
                  </h2>
                </div>
                <p className={styles.cardDescription}>
                  {presentation.description}
                </p>
                <ul
                  className={styles.capabilities}
                  aria-label={`${agent.name} can help with`}
                >
                  {presentation.capabilities.map((capability) => (
                    <li key={capability}>
                      <CheckMark />
                      <span>{capability}</span>
                    </li>
                  ))}
                </ul>
                {agent.currentWork && agent.observationMode !== null && (
                  <p className={styles.currentWork}>
                    <span>Current work</span>
                    {agent.currentWork}
                  </p>
                )}
                <footer className={styles.cardFooter}>
                  <div className={styles.cardContext}>
                    <span>{contextLabel}</span>
                    {agent.id === RAG_CHAT_AGENT_ID && <span>Text only</span>}
                  </div>
                  <div className={styles.cardActions}>
                    {agent.canRunInChat ? (
                      <>
                        <button
                          type="button"
                          className={styles.primaryAction}
                          onClick={() => openAgentInChat(agent)}
                          aria-label={`Start chat with ${agent.name}`}
                        >
                          <MessageSquare size={16} aria-hidden />
                          Start chat
                        </button>
                        <a
                          className={styles.detailsLink}
                          href={href}
                          onClick={(event) => openAgentDetail(event, agent)}
                          aria-label={`View ${agent.name} details`}
                        >
                          Details
                          <ArrowRight size={14} aria-hidden />
                        </a>
                      </>
                    ) : (
                      <a
                        className={styles.primaryAction}
                        href={href}
                        onClick={(event) => openAgentDetail(event, agent)}
                        aria-label={
                          agent.id === SUMIN_AGENT_ID
                            ? `View ${agent.name} details`
                            : `Open ${agent.name} workspace`
                        }
                      >
                        {agent.id === SUMIN_AGENT_ID
                          ? "View details"
                          : "Open workspace"}
                        <ArrowRight size={16} aria-hidden />
                      </a>
                    )}
                  </div>
                </footer>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

function CheckMark() {
  return <span className={styles.capabilityDot} aria-hidden />;
}

export function prepareAgentChatSelection(agent: AgentDefinition) {
  const { clearPendingAgentRun, selectAgent } = useUiStore.getState();
  clearPendingAgentRun();
  selectAgent(agent);
}

export function filterAgents(agents: AgentDefinition[], search: string) {
  const normalizedSearch = search.trim().toLocaleLowerCase();
  if (!normalizedSearch) return agents;
  return agents.filter((agent) => {
    const presentation = getAgentPresentation(agent);
    return [
      agent.name,
      agent.role,
      agent.description,
      agent.graphId,
      agent.currentWork ?? "",
      ...agent.capabilities,
      presentation.specialty,
      presentation.description,
      ...presentation.capabilities
    ]
      .join(" ")
      .toLocaleLowerCase()
      .includes(normalizedSearch);
  });
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
