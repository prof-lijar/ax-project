import { useUiStore, type AppSection } from "../state/useUiStore";

export const sectionPaths: Record<AppSection, string> = {
  chat: "/chat",
  nextcloud: "/nextcloud",
  tasks: "/tasks",
  approvals: "/approvals",
  agents: "/agents",
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
  const location = resolveSectionLocation(pathname);

  if (location) {
    const { path, section } = location;
    if (currentPath !== path) {
      window.history.replaceState({ section }, "", path);
    }
    useUiStore.getState().setActiveSection(section);
    return;
  }

  const fallback: AppSection = "chat";
  window.history.replaceState(
    { section: fallback },
    "",
    sectionPaths[fallback]
  );
  useUiStore.getState().setActiveSection(fallback);
}

export function resolveSectionLocation(
  pathname: string
): { section: AppSection; path: string } | null {
  const normalizedPathname = normalizePath(pathname);

  if (normalizedPathname === "/") {
    return { section: "chat", path: sectionPaths.chat };
  }

  if (normalizedPathname === "/co-workers") {
    return { section: "agents", path: sectionPaths.agents };
  }

  const entry = Object.entries(sectionPaths).find(
    ([, path]) => path === normalizedPathname
  );
  const section = entry?.[0] as AppSection | undefined;
  return section ? { section, path: sectionPaths[section] } : null;
}

function normalizePath(pathname: string) {
  if (pathname === "/") {
    return pathname;
  }
  return pathname.replace(/\/+$/, "") || "/";
}
