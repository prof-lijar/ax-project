import { create } from "zustand";

import type { AgentDefinition } from "../types/agents";

export type AppSection =
  | "chat"
  | "nextcloud"
  | "tasks"
  | "approvals"
  | "agents"
  | "test-agent"
  | "activity"
  | "settings";

interface UiState {
  activeSection: AppSection;
  activePath: string;
  search: string;
  selectedAgent: AgentDefinition | null;
  pendingAgentRun: { agentId: string; requestId: string } | null;
  setActiveSection: (section: AppSection) => void;
  setActiveLocation: (section: AppSection, path: string) => void;
  setSearch: (search: string) => void;
  selectAgent: (agent: AgentDefinition) => void;
  requestAgentRun: (agent: AgentDefinition) => void;
  clearPendingAgentRun: () => void;
  clearSelectedAgent: () => void;
}

export const useUiStore = create<UiState>((set) => ({
  activeSection: "chat",
  activePath: "/chat",
  search: "",
  selectedAgent: null,
  pendingAgentRun: null,
  setActiveSection: (activeSection) => set({ activeSection }),
  setActiveLocation: (activeSection, activePath) =>
    set({ activeSection, activePath }),
  setSearch: (search) => set({ search }),
  selectAgent: (selectedAgent) => set({ selectedAgent }),
  requestAgentRun: (selectedAgent) =>
    set({
      selectedAgent,
      pendingAgentRun: {
        agentId: selectedAgent.id,
        requestId: `${Date.now()}-${selectedAgent.id}`
      }
    }),
  clearPendingAgentRun: () => set({ pendingAgentRun: null }),
  clearSelectedAgent: () => set({ selectedAgent: null })
}));
