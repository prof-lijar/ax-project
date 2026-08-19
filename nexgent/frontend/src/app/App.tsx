import { useLayoutEffect } from "react";

import { ActivityPage } from "../features/activity/ActivityPage";
import { AgentDetailPage } from "../features/agents/AgentDetailPage";
import { AgentsPage } from "../features/agents/AgentsPage";
import { ApprovalsPage } from "../features/approvals/ApprovalsPage";
import { ChatPage } from "../features/chat/ChatPage";
import { NextcloudPage } from "../features/nextcloud/NextcloudPage";
import { SettingsPage } from "../features/settings/SettingsPage";
import { TasksPage } from "../features/tasks/TasksPage";
import { TestAgentPage } from "../features/test-agent/TestAgentPage";
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
  return agentId
    ? ({ kind: "detail", agentId } as const)
    : ({ kind: "catalog" } as const);
}

export function App() {
  const activeSection = useUiStore((state) => state.activeSection);
  const activePath = useUiStore((state) => state.activePath);
  const activeAgentId =
    activeSection === "agents" ? getAgentIdFromPath(activePath) : null;
  const agentsRoute = getAgentsRoute(activeAgentId);

  useLayoutEffect(() => {
    syncSectionFromLocation();
    window.addEventListener("popstate", syncSectionFromLocation);
    return () => window.removeEventListener("popstate", syncSectionFromLocation);
  }, []);

  return (
    <AppShell>
      {activeSection === "chat" && <ChatPage />}
      {activeSection === "nextcloud" && <NextcloudPage />}
      {activeSection === "tasks" && <TasksPage />}
      {activeSection === "approvals" && <ApprovalsPage />}
      {activeSection === "agents" &&
        (agentsRoute.kind === "weekly-reporter" ? (
          <TestAgentPage mode="agent" />
        ) : agentsRoute.kind === "detail" ? (
          <AgentDetailPage agentId={agentsRoute.agentId} />
        ) : (
          <AgentsPage />
        ))}
      {activeSection === "test-agent" && <TestAgentPage />}
      {activeSection === "activity" && <ActivityPage />}
      {activeSection === "settings" && <SettingsPage />}
    </AppShell>
  );
}
