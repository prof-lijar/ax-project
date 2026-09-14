import { useEffect, useLayoutEffect, useState } from "react";

import { AgentDetailPage } from "../features/agents/AgentDetailPage";
import { AgentsPage } from "../features/agents/AgentsPage";
import { ScoutWorkbenchPage } from "../features/agents/ScoutWorkbenchPage";
import { ChatPage } from "../features/chat/ChatPage";
import { createChatRunner } from "../features/chat/chatRunner";
import { NextcloudPage } from "../features/nextcloud/NextcloudPage";
import { RagPage } from "../features/rag/RagPage";
import { SettingsPage } from "../features/settings/SettingsPage";
import { WeeklyReporterPage } from "../features/weekly-report/WeeklyReporterPage";
import { SCOUT_AGENT_ID } from "../shared/api/agentCatalogClient";
import {
  getAgentIdFromPath,
  syncSectionFromLocation
} from "../shared/navigation/sections";
import { useUiStore } from "../shared/state/useUiStore";
import { AppShell } from "./shell/AppShell";

export function getAgentsRoute(agentId: string | null) {
  if (agentId === "1") {
    return { kind: "weekly-reporter" } as const;
  }
  if (agentId === SCOUT_AGENT_ID) {
    return { kind: "scout" } as const;
  }
  return agentId
    ? ({ kind: "detail", agentId } as const)
    : ({ kind: "catalog" } as const);
}

export function App() {
  const [chatRunner] = useState(createChatRunner);
  const activeSection = useUiStore((state) => state.activeSection);
  const activePath = useUiStore((state) => state.activePath);
  const activeAgentId =
    activeSection === "agents" ? getAgentIdFromPath(activePath) : null;
  const agentsRoute = getAgentsRoute(activeAgentId);

  // Menu navigation unmounts ChatPage, but the request belongs to this app session.
  useEffect(() => () => chatRunner.stop(), [chatRunner]);

  useLayoutEffect(() => {
    syncSectionFromLocation();
    window.addEventListener("popstate", syncSectionFromLocation);
    return () =>
      window.removeEventListener("popstate", syncSectionFromLocation);
  }, []);

  return (
    <AppShell>
      {activeSection === "chat" && <ChatPage runner={chatRunner} />}
      {activeSection === "nextcloud" && <NextcloudPage />}
      {activeSection === "agents" &&
        (agentsRoute.kind === "weekly-reporter" ? (
          <WeeklyReporterPage />
        ) : agentsRoute.kind === "scout" ? (
          <ScoutWorkbenchPage />
        ) : agentsRoute.kind === "detail" ? (
          <AgentDetailPage agentId={agentsRoute.agentId} />
        ) : (
          <AgentsPage />
        ))}
      {activeSection === "rag" && <RagPage />}
      {activeSection === "settings" && <SettingsPage />}
    </AppShell>
  );
}
