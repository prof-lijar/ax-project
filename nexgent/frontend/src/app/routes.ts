import {
  Activity,
  FlaskConical,
  Bot,
  CheckSquare,
  Cloud,
  MessageSquare,
  Settings,
  ShieldCheck
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { sectionPaths } from "../shared/navigation/sections";
import type { AppSection } from "../shared/state/useUiStore";

export const navItems: Array<{
  id: AppSection;
  label: string;
  icon: LucideIcon;
  path: string;
}> = [
  {
    id: "chat",
    label: "Chat",
    icon: MessageSquare,
    path: sectionPaths.chat
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
  { id: "agents", label: "Agents", icon: Bot, path: sectionPaths.agents },
  {
    id: "test-agent",
    label: "Test agent",
    icon: FlaskConical,
    path: sectionPaths["test-agent"]
  },
  {
    id: "activity",
    label: "Activity",
    icon: Activity,
    path: sectionPaths.activity
  },
  { id: "settings", label: "Settings", icon: Settings, path: sectionPaths.settings }
];
