import {
  Activity,
  Bot,
  CheckSquare,
  Cloud,
  Gauge,
  Settings,
  ShieldCheck
} from "lucide-react";

import type { AppSection } from "../shared/state/useUiStore";

export const navItems: Array<{
  id: AppSection;
  label: string;
  icon: typeof Gauge;
}> = [
  { id: "mission-control", label: "Mission Control", icon: Gauge },
  { id: "nextcloud", label: "NextCloud", icon: Cloud },
  { id: "tasks", label: "Tasks", icon: CheckSquare },
  { id: "approvals", label: "Approvals", icon: ShieldCheck },
  { id: "agents", label: "Agents Team", icon: Bot },
  { id: "activity", label: "Activity", icon: Activity },
  { id: "settings", label: "Settings", icon: Settings }
];
