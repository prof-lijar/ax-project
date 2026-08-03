import { useUiStore, type AppSection } from "../state/useUiStore";

export const sectionPaths: Record<AppSection, string> = {
  "mission-control": "/workspace",
  nextcloud: "/nextcloud",
  tasks: "/tasks",
  approvals: "/approvals",
  agents: "/co-workers",
  activity: "/activity",
  settings: "/settings"
};

export function navigateToSection(section: AppSection) {
  const path = sectionPaths[section];
  if (normalizePath(window.location.pathname) !== path) {
    window.history.pushState({ section }, "", path);
  }
  useUiStore.getState().setActiveSection(section);
}

export function syncSectionFromLocation() {
  const currentPath = window.location.pathname;
  const pathname = normalizePath(currentPath);
  const section = sectionFromPath(pathname);

  if (section) {
    const path = sectionPaths[section];
    if (currentPath !== path) {
      window.history.replaceState({ section }, "", path);
    }
    useUiStore.getState().setActiveSection(section);
    return;
  }

  const fallback: AppSection = "mission-control";
  window.history.replaceState(
    { section: fallback },
    "",
    sectionPaths[fallback]
  );
  useUiStore.getState().setActiveSection(fallback);
}

function sectionFromPath(pathname: string): AppSection | null {
  if (pathname === "/") {
    return "mission-control";
  }

  const entry = Object.entries(sectionPaths).find(
    ([, path]) => path === pathname
  );
  return (entry?.[0] as AppSection | undefined) ?? null;
}

function normalizePath(pathname: string) {
  if (pathname === "/") {
    return pathname;
  }
  return pathname.replace(/\/+$/, "") || "/";
}
