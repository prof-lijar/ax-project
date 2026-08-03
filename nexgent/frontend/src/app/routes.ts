import {
  Activity,
  Bot,
  CheckSquare,
  Cloud,
  Gauge,
  Settings,
  ShieldCheck
} from "lucide-react";

import { sectionPaths } from "../shared/navigation/sections";
import type { AppSection } from "../shared/state/useUiStore";

export const navItems: Array<{
  id: AppSection;
  label: string;
  icon: typeof Gauge;
  path: string;
}> = [
  {
    id: "mission-control",
    label: "Workspace",
    icon: Gauge,
    path: sectionPaths["mission-control"]
  },
  {
    id: "nextcloud",
    label: "NextCloud",
    icon: Cloud,
    path: sectionPaths.nextcloud
  },
  { id: "tasks", label: "Tasks", icon: CheckSquare, path: sectionPaths.tasks },
  {
    id: "approvals",
    label: "Approvals",
    icon: ShieldCheck,
    path: sectionPaths.approvals
  },
  { id: "agents", label: "Co-workers", icon: Bot, path: sectionPaths.agents },
  {
    id: "activity",
    label: "Activity",
    icon: Activity,
    path: sectionPaths.activity
  },
  { id: "settings", label: "Settings", icon: Settings, path: sectionPaths.settings }
];
