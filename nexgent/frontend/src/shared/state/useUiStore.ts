import { create } from "zustand";

export type AppSection =
  | "mission-control"
  | "nextcloud"
  | "tasks"
  | "approvals"
  | "agents"
  | "activity"
  | "settings";

interface UiState {
  activeSection: AppSection;
  search: string;
  setActiveSection: (section: AppSection) => void;
  setSearch: (search: string) => void;
}

export const useUiStore = create<UiState>((set) => ({
  activeSection: "mission-control",
  search: "",
  setActiveSection: (activeSection) => set({ activeSection }),
  setSearch: (search) => set({ search })
}));
