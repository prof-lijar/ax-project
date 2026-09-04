import {
  Bot,
  Cloud,
  Database,
  MessageSquare,
  Settings
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
  { id: "agents", label: "Agents", icon: Bot, path: sectionPaths.agents },
  { id: "rag", label: "RAG", icon: Database, path: sectionPaths.rag },
  { id: "settings", label: "Settings", icon: Settings, path: sectionPaths.settings }
];
