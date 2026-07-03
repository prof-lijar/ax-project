import { ActivityPage } from "../features/activity/ActivityPage";
import { AgentsPage } from "../features/agents/AgentsPage";
import { ApprovalsPage } from "../features/approvals/ApprovalsPage";
import { MissionControl } from "../features/mission-control/MissionControl";
import { SettingsPage } from "../features/settings/SettingsPage";
import { TasksPage } from "../features/tasks/TasksPage";
import { useUiStore } from "../shared/state/useUiStore";
import { AppShell } from "./shell/AppShell";
import { InspectorPanel } from "./shell/InspectorPanel";

export function App() {
  const activeSection = useUiStore((state) => state.activeSection);

  return (
    <AppShell inspector={<InspectorPanel />}>
      {activeSection === "mission-control" && <MissionControl />}
      {activeSection === "tasks" && <TasksPage />}
      {activeSection === "approvals" && <ApprovalsPage />}
      {activeSection === "agents" && <AgentsPage />}
      {activeSection === "activity" && <ActivityPage />}
      {activeSection === "settings" && <SettingsPage />}
    </AppShell>
  );
}
