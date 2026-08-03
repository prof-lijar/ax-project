import { useLayoutEffect } from "react";

import { ActivityPage } from "../features/activity/ActivityPage";
import { AgentsPage } from "../features/agents/AgentsPage";
import { ApprovalsPage } from "../features/approvals/ApprovalsPage";
import { MissionControl } from "../features/mission-control/MissionControl";
import { NextcloudPage } from "../features/nextcloud/NextcloudPage";
import { SettingsPage } from "../features/settings/SettingsPage";
import { TasksPage } from "../features/tasks/TasksPage";
import { syncSectionFromLocation } from "../shared/navigation/sections";
import { useUiStore } from "../shared/state/useUiStore";
import { AppShell } from "./shell/AppShell";

export function App() {
  const activeSection = useUiStore((state) => state.activeSection);

  useLayoutEffect(() => {
    syncSectionFromLocation();
    window.addEventListener("popstate", syncSectionFromLocation);
    return () => window.removeEventListener("popstate", syncSectionFromLocation);
  }, []);

  return (
    <AppShell>
      {activeSection === "mission-control" && <MissionControl />}
      {activeSection === "nextcloud" && <NextcloudPage />}
      {activeSection === "tasks" && <TasksPage />}
      {activeSection === "approvals" && <ApprovalsPage />}
      {activeSection === "agents" && <AgentsPage />}
      {activeSection === "activity" && <ActivityPage />}
      {activeSection === "settings" && <SettingsPage />}
    </AppShell>
  );
}
