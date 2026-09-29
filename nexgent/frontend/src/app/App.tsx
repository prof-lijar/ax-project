import { useEffect, useLayoutEffect, useState } from "react";
import { AdminOnly } from "../features/accounts/AdminOnly";

import { AgentDetailPage } from "../features/agents/AgentDetailPage";
import { AgentsPage } from "../features/agents/AgentsPage";
import { ScoutWorkbenchPage } from "../features/agents/ScoutWorkbenchPage";
import { ChatPage } from "../features/chat/ChatPage";
import { createPersistentChatRunner } from "../features/chat/persistentChatRunner";
import { useSavedChatHistory } from "../features/chat/useSavedChatHistory";
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
  const [chatRunner] = useState(createPersistentChatRunner);
  const chatHistory = useSavedChatHistory(chatRunner);
  const activeSection = useUiStore((state) => state.activeSection);
  const activePath = useUiStore((state) => state.activePath);
  const activeAgentId =
    activeSection === "agents" ? getAgentIdFromPath(activePath) : null;
  const agentsRoute = getAgentsRoute(activeAgentId);

  // Menu navigation unmounts ChatPage, but the request belongs to this app session.
  useEffect(() => () => chatRunner.detach(), [chatRunner]);

  useLayoutEffect(() => {
    syncSectionFromLocation();
    window.addEventListener("popstate", syncSectionFromLocation);
    return () =>
      window.removeEventListener("popstate", syncSectionFromLocation);
  }, []);

  return (
    <AppShell>
      {activeSection === "chat" && <ChatPage runner={chatRunner} history={chatHistory} />}
      {activeSection === "nextcloud" && <NextcloudPage />}
      {activeSection === "agents" &&
        (agentsRoute.kind === "weekly-reporter" ? (
          <AdminOnly><WeeklyReporterPage /></AdminOnly>
        ) : agentsRoute.kind === "scout" ? (
          <AdminOnly><ScoutWorkbenchPage /></AdminOnly>
        ) : agentsRoute.kind === "detail" ? (
          <AdminOnly><AgentDetailPage agentId={agentsRoute.agentId} /></AdminOnly>
        ) : (
          <AgentsPage />
        ))}
      {activeSection === "rag" && <AdminOnly><RagPage /></AdminOnly>}
      {activeSection === "settings" && <SettingsPage />}
    </AppShell>
  );
}
