import {
  Bot,
  Braces,
  CalendarClock,
  CircleAlert,
  Clock3,
  Workflow
} from "lucide-react";
import { useState, type ReactNode } from "react";

import { useAgentCatalog } from "../../shared/api/queries";
import { Badge } from "../../shared/components/Badge";
import { useUiStore } from "../../shared/state/useUiStore";
import type {
  AgentDefinition,
  AgentReadiness,
  AgentRunStatus
} from "../../shared/types/agents";
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
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const visibleAgents = filterAgents(agents, search);
  const selectedAgent =
    visibleAgents.find((agent) => agent.id === selectedId) ??
    visibleAgents[0] ??
    null;

  return (
    <section className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <h1>Agents</h1>
          <p>Monitor the LangGraph workflows that work alongside your team.</p>
        </div>
        <Badge tone="amber">Preview data</Badge>
      </header>

      <div className={styles.previewNotice} role="note">
        <CircleAlert size={17} aria-hidden />
        <span>
          Status and run history are samples. Live Agent Server monitoring will
          be connected with the first agent integration.
        </span>
      </div>

      <div className={styles.workspace}>
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
            <div className={styles.agentList} role="listbox" aria-label="Agents">
              {visibleAgents.map((agent) => {
                const readiness = getReadinessPresentation(agent.readiness);
                const selected = agent.id === selectedAgent?.id;

                return (
                  <button
                    className={selected ? styles.agentCardSelected : styles.agentCard}
                    key={agent.id}
                    type="button"
                    role="option"
                    aria-selected={selected}
                    onClick={() => setSelectedId(agent.id)}
                  >
                    <span className={styles.agentIdentity}>
                      <span className={styles.agentAvatar} aria-hidden>
                        <Bot size={20} />
                      </span>
                      <span>
                        <strong>{agent.name}</strong>
                        <small>{agent.role}</small>
                      </span>
                    </span>
                    <span className={styles.cardBadges}>
                      <Badge tone={readiness.tone}>{readiness.label}</Badge>
                      <Badge>{agent.runtimeLabel}</Badge>
                    </span>
                    <span className={styles.currentWork}>{agent.currentWork}</span>
                    <span className={styles.cardFooter}>
                      <span>{agent.graphId}</span>
                      <span>{agent.recentRuns.length} sample runs</span>
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </section>

        <AgentInspector agent={selectedAgent} />
      </div>
    </section>
  );
}

function CatalogMessage({ children }: { children: string }) {
  return <div className={styles.catalogMessage}>{children}</div>;
}

function AgentInspector({ agent }: { agent: AgentDefinition | null }) {
  if (!agent) {
    return (
      <aside className={styles.emptyInspector} aria-label="Agent details">
        <Bot size={24} aria-hidden />
        <strong>Select an agent to inspect</strong>
        <span>Configuration and recent work will appear here.</span>
      </aside>
    );
  }

  const readiness = getReadinessPresentation(agent.readiness);

  return (
    <aside className={styles.inspector} aria-label={`${agent.name} details`}>
      <header className={styles.inspectorHeader}>
        <span className={styles.inspectorIcon} aria-hidden>
          <Bot size={24} />
        </span>
        <div className={styles.inspectorTitle}>
          <div>
            <h2>{agent.name}</h2>
            <Badge tone="amber">Preview data</Badge>
          </div>
          <p>{agent.role}</p>
        </div>
        <Badge tone={readiness.tone}>{readiness.label}</Badge>
      </header>

      <p className={styles.description}>{agent.description}</p>

      <dl className={styles.factGrid}>
        <div>
          <dt><Workflow size={15} aria-hidden /> Graph ID</dt>
          <dd><code>{agent.graphId}</code></dd>
        </div>
        <div>
          <dt><Braces size={15} aria-hidden /> Runtime</dt>
          <dd>{agent.runtimeLabel}</dd>
        </div>
        <div>
          <dt><Clock3 size={15} aria-hidden /> Last observed</dt>
          <dd>{formatObservedAt(agent.lastObservedAt)}</dd>
        </div>
      </dl>

      <InspectorSection title="Capabilities">
        <div className={styles.capabilities}>
          {agent.capabilities.map((capability) => (
            <Badge key={capability}>{capability}</Badge>
          ))}
        </div>
      </InspectorSection>

      <InspectorSection title="Contract">
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
      </InspectorSection>

      <InspectorSection title="Configuration">
        <dl className={styles.configuration}>
          {agent.configuration.map((item) => (
            <div key={item.label}>
              <dt>{item.label}</dt>
              <dd>{item.value}</dd>
            </div>
          ))}
        </dl>
      </InspectorSection>

      <InspectorSection title="Current limitations">
        <ul className={styles.limitations}>
          {agent.limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
      </InspectorSection>

      <InspectorSection title="Recent runs" detail="Sample history">
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
      </InspectorSection>
    </aside>
  );
}

function InspectorSection({
  title,
  detail,
  children
}: {
  title: string;
  detail?: string;
  children: ReactNode;
}) {
  return (
    <section className={styles.inspectorSection}>
      <header>
        <h3>{title}</h3>
        {detail && <span>{detail}</span>}
      </header>
      {children}
    </section>
  );
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
      agent.currentWork,
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
