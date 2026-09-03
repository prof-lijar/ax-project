import { useUiStore, type AppSection } from "../state/useUiStore";

export const sectionPaths: Record<AppSection, string> = {
  chat: "/chat",
  nextcloud: "/nextcloud",
  agents: "/agents",
  "test-agent": "/test-agent",
  rag: "/rag",
  settings: "/settings"
};

export function navigateToSection(section: AppSection) {
  const path = sectionPaths[section];
  navigateToLocation(section, path);
}

export function navigateToAgentDetail(agentId: string) {
  navigateToLocation("agents", `/agents/${encodeURIComponent(agentId)}`);
}

function navigateToLocation(section: AppSection, path: string) {
  if (normalizePath(window.location.pathname) !== path) {
    window.history.pushState({ section }, "", path);
  }
  useUiStore.getState().setActiveLocation(section, path);
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
    useUiStore.getState().setActiveLocation(section, path);
    return;
  }

  const fallback: AppSection = "chat";
  window.history.replaceState(
    { section: fallback },
    "",
    sectionPaths[fallback]
  );
  useUiStore.getState().setActiveLocation(fallback, sectionPaths[fallback]);
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

  if (getAgentIdFromPath(normalizedPathname)) {
    return { section: "agents", path: normalizedPathname };
  }

  const entry = Object.entries(sectionPaths).find(
    ([, path]) => path === normalizedPathname
  );
  const section = entry?.[0] as AppSection | undefined;
  return section ? { section, path: sectionPaths[section] } : null;
}

export function getAgentIdFromPath(pathname: string): string | null {
  const match = normalizePath(pathname).match(/^\/agents\/([^/]+)$/);
  if (!match) {
    return null;
  }

  try {
    return decodeURIComponent(match[1]);
  } catch {
    return null;
  }
}

function normalizePath(pathname: string) {
  if (pathname === "/") {
    return pathname;
  }
  return pathname.replace(/\/+$/, "") || "/";
}
