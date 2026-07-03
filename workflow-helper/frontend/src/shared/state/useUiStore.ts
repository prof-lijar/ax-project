import { create } from "zustand";

export type AppSection =
  | "mission-control"
  | "nextcloud"
  | "tasks"
  | "approvals"
  | "agents"
  | "activity"
  | "settings";

type InspectorTarget =
  | { type: "task"; id: string }
  | { type: "approval"; id: string }
  | { type: "agent"; id: string }
  | { type: "event"; id: string }
  | null;

interface UiState {
  activeSection: AppSection;
  inspectorTarget: InspectorTarget;
  search: string;
  setActiveSection: (section: AppSection) => void;
  setInspectorTarget: (target: InspectorTarget) => void;
  setSearch: (search: string) => void;
}

export const useUiStore = create<UiState>((set) => ({
  activeSection: "mission-control",
  inspectorTarget: null,
  search: "",
  setActiveSection: (activeSection) => set({ activeSection }),
  setInspectorTarget: (inspectorTarget) => set({ inspectorTarget }),
  setSearch: (search) => set({ search })
}));
