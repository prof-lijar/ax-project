import { useAccount } from "../accounts/accountContext";
import { t, useLanguage } from "../../shared/i18n";
import {
  ArrowRight,
  BookOpen,
  CircleAlert,
  FileBarChart,
  FileSpreadsheet,
  MessageSquare,
  Search,
  SearchX,
  Telescope,
  UsersRound,
  X
} from "lucide-react";
import { useRef, useState, type MouseEvent } from "react";

import {
  AX768_AGENT_ID,
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
  canViewDetails?: boolean;
  search: string;
  onSearchChange?: (value: string) => void;
  onRetry?: () => void;
  isLoading?: boolean;
  isError?: boolean;
  isRetrying?: boolean;
}

export function AgentsPage() {
  useLanguage((state) => state.language);
  const account = useAccount();
  const catalogQuery = useAgentCatalog();
  const [search, setSearch] = useState("");
  return (
    <AgentsPageView
      canViewDetails={account.is_admin}
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
    case AX768_AGENT_ID:
      return {
        icon: FileSpreadsheet, specialty: t("Spreadsheets"),
        description: t("Find the right user or AS row, then review the result."),
        capabilities: [t("Search users across cities"), t("Find the latest AS row")],
        tone: "reporting"
      };
    case WEEKLY_REPORTER_AGENT_ID:
      return {
        icon: FileBarChart,
        specialty: t("Reporting"),
        description: t("Turn weekly ward activity into clear risk reports."),
        capabilities: [
          t("Review ward risk and activity"),
          t("Download reports as a ZIP")
        ],
        tone: "reporting"
      };
    case RAG_CHAT_AGENT_ID:
      return {
        icon: BookOpen,
        specialty: t("Knowledge"),
        description:
          t("Find answers in your indexed knowledge, with sources to check."),
        capabilities: [
          t("Ask about indexed documents"),
          t("Follow sources in each answer")
        ],
        tone: "knowledge"
      };
    case SCOUT_AGENT_ID:
      return {
        icon: Telescope,
        specialty: t("Research"),
        description:
          t("Explore a topic on the web and bring the findings together."),
        capabilities: [
          t("Search and review web sources"),
          t("Create a sourced research report")
        ],
        tone: "research"
      };
    case SUMIN_AGENT_ID:
      return {
        icon: MessageSquare,
        specialty: t("Slack files"),
        description:
          t("Keep channel uploads organized and find them again from a mention."),
        capabilities: [
          t("Archive Slack files in Nextcloud"),
          t("Find uploads from names and context")
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
  canViewDetails = false,
  search,
  onSearchChange,
  onRetry,
  isLoading = false,
  isError = false,
  isRetrying = false
}: AgentsPageViewProps) {
  useLanguage((state) => state.language);
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
    if (!canViewDetails) {
      event.preventDefault();
      return;
    }
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
          <h1 id="coworkers-title">{t("Agents")}</h1>
          <p>
            {t("Choose an agent. Open their workspace or start a conversation.")}
          </p>
        </div>
      </header>
      <div className={styles.catalogTools}>
        <p className={styles.resultCount} role="status">
          {isLoading
            ? t("Loading agents…")
            : isError
              ? t("Couldn't load agents")
              : search.trim()
                ? t("{0} of {1} agents", { 0: visibleAgents.length, 1: agents.length })
                : t("{0} agent{1}", { 0: agents.length, 1: agents.length === 1 ? "" : "s" })}
        </p>
        <div className={styles.searchBox}>
          <Search size={17} aria-hidden />
          <input
            ref={searchRef}
            aria-label={t("Find an agent")}
            placeholder={t("Find an agent…")}
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
              aria-label={t("Clear search")}
              title={t("Clear search")}
              onClick={clearSearch}
            >
              <X size={15} />
            </button>
          )}
        </div>
      </div>
      {!canViewDetails && <p className={styles.accessNotice} role="status">
        {t("Agent details and workspaces are available to administrators only.")}
      </p>}
      {hasPreviewAgents && (
        <p className={styles.previewNotice}>
          <CircleAlert size={16} aria-hidden />
          <span>
            {t("Preview data is marked on each sample agent. Their status and activity are examples.")}
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
          <h2>{t("Agents are unavailable")}</h2>
          <p>{t("Try loading your team again.")}</p>
          {onRetry && (
            <button
              type="button"
              className={styles.secondaryAction}
              onClick={onRetry}
              disabled={isRetrying}
            >
              {isRetrying ? t("Trying again…") : t("Try again")}
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
          <h2>{agents.length ? t("No agents found") : t("No agents yet")}</h2>
          <p>
            {agents.length
              ? t("Try a name, a role, or the work you need help with.")
              : t("Connected agents will appear here.")}
          </p>
          {search && onSearchChange && (
            <button
              type="button"
              className={styles.secondaryAction}
              onClick={clearSearch}
            >
              {t("Clear search")}</button>
          )}
        </div>
      )}
      {showCatalog && visibleAgents.length > 0 && (
        <div className={styles.agentList} role="list" aria-label={t("Agents")}>
          {visibleAgents.map((agent) => {
            const presentation = getAgentPresentation(agent);
            const Icon = presentation.icon;
            const readiness = agent.readiness
              ? getReadinessPresentation(agent.readiness)
              : null;
            const selected =
              agent.canRunInChat && agent.id === selectedAgent?.id;
            const contextLabel = selected
              ? t("Selected in Chat")
              : agent.canRunInChat
                ? t("Available in Chat")
                : agent.id === SUMIN_AGENT_ID
                  ? t("Works in Slack")
                  : t("Dedicated workspace");
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
                    <Icon size={18} strokeWidth={1.7} />
                  </span>
                  <div className={styles.cardIdentity}>
                    <h2 id={`coworker-${agent.id}`}>
                      {canViewDetails ? <a
                        href={href}
                        onClick={(event) => openAgentDetail(event, agent)}
                      >
                        {t(agent.name)}
                      </a> : <span>{t(agent.name)}</span>}
                    </h2>
                  </div>
                  <div className={styles.cardStatus}>
                    {agent.observationMode === "preview" && (
                      <Badge tone="amber">{t("Preview data")}</Badge>
                    )}
                    {readiness && (
                      <Badge tone={readiness.tone}>{readiness.label}</Badge>
                    )}
                  </div>
                </div>
                <p className={styles.cardDescription} title={presentation.description}>
                  {presentation.description}
                </p>
                <footer className={styles.cardFooter}>
                  <div className={styles.cardContext}>
                    <span>{contextLabel}</span>
                    {agent.id === RAG_CHAT_AGENT_ID && <span>{t("Text only")}</span>}
                  </div>
                  <div className={styles.cardActions}>
                    {agent.canRunInChat ? (
                      <>
                        <button
                          type="button"
                          className={styles.primaryAction}
                          onClick={() => openAgentInChat(agent)}
                          aria-label={t("Start chat with {0}", { 0: agent.name })}
                        >
                          <MessageSquare size={16} aria-hidden />
                          {t("Start chat")}
                        </button>
                        {canViewDetails ? <a
                          className={styles.detailsLink}
                          href={href}
                          onClick={(event) => openAgentDetail(event, agent)}
                          aria-label={t("View {0} details", { 0: agent.name })}
                        >
                          {t("Details")} <ArrowRight size={14} aria-hidden />
                        </a> : <button type="button" className={styles.detailsLink} disabled title={t("Admin only")}>{t("Details")}</button>}
                      </>
                    ) : !canViewDetails ? (
                      <button type="button" className={styles.primaryAction} disabled title={t("Admin only")}>
                        {agent.id === SUMIN_AGENT_ID ? t("View details") : t("Open workspace")}
                      </button>
                    ) : (
                      <a
                        className={styles.primaryAction}
                        href={href}
                        onClick={(event) => openAgentDetail(event, agent)}
                        aria-label={
                          agent.id === SUMIN_AGENT_ID
                            ? t("View {0} details", { 0: agent.name })
                            : t("Open {0} workspace", { 0: agent.name })
                        }
                      >
                        {agent.id === SUMIN_AGENT_ID
                          ? t("View details")
                          : t("Open workspace")}
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
    ready: { label: t("Ready"), tone: "green" },
    degraded: { label: t("Needs attention"), tone: "amber" },
    offline: { label: t("Offline"), tone: "red" },
    draft: { label: t("Draft"), tone: "neutral" }
  } as const;
  return presentations[readiness];
}
