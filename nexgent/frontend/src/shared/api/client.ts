import { invoke } from "@tauri-apps/api/core";

import {
  agents,
  systemHealth
} from "./mockData";
import {
  downloadBrowserNextcloudFile,
  getBrowserNextcloudStatus,
  listBrowserNextcloudFiles,
  previewBrowserNextcloudFile,
  readBrowserNextcloudTextFile
} from "./nextcloudBackendClient";
import type {
  AgentSummary,
  CommandError,
  SystemHealth
} from "../types/domain";
import type {
  NextcloudDownloadResponse,
  NextcloudListFilesResponse,
  NextcloudPreviewResponse,
  NextcloudStatus,
  NextcloudTextFileResponse,
  NextcloudViewerKind
} from "../types/nextcloud";

type TauriWindow = Window & { __TAURI_INTERNALS__?: unknown };

const isTauriRuntime = () =>
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in (window as TauriWindow);

const delay = async () => new Promise((resolve) => window.setTimeout(resolve, 90));

interface DesktopNextcloudPreviewResponse {
  path: string;
  filename: string;
  contentType: string;
  viewerKind: string;
  bytes: number[];
}

async function callCommand<T>(
  command: string,
  fallback: () => T,
  args?: Record<string, unknown>
): Promise<T> {
  if (isTauriRuntime()) {
    try {
      return await invoke<T>(command, args);
    } catch (error) {
      throw normalizeCommandError(error);
    }
  }

  await delay();
  return fallback();
}

async function callDesktopOrBrowser<T>(
  command: string,
  browserFallback: () => Promise<T>,
  args?: Record<string, unknown>
): Promise<T> {
  if (isTauriRuntime()) {
    try {
      return await invoke<T>(command, args);
    } catch (error) {
      throw normalizeCommandError(error);
    }
  }

  return browserFallback();
}

function normalizeCommandError(error: unknown): CommandError {
  if (typeof error === "object" && error !== null && "message" in error) {
    return error as CommandError;
  }

  return {
    code: "unknown_command_error",
    message: "The desktop command failed.",
    recoveryAction: "Refresh the view and try again."
  };
}

export const desktopApi = {
  getSystemHealth: () =>
    callCommand<SystemHealth>("system_health", () => systemHealth),
  listAgents: () => callCommand<AgentSummary[]>("agents_list", () => agents),
  getAgent: (id: string) =>
    callCommand<AgentSummary>(
      "agents_get",
      () => {
        const agent = agents.find((item) => item.id === id);
        if (!agent) {
          throw normalizeCommandError({
            code: "not_found",
            message: `Agent with id '${id}' was not found.`
          });
        }
        return agent;
      },
      { id }
    ),
  getNextcloudStatus: () =>
    callDesktopOrBrowser<NextcloudStatus>(
      "nextcloud_health",
      getBrowserNextcloudStatus
    ),
  listNextcloudFiles: (path: string) =>
    callDesktopOrBrowser<NextcloudListFilesResponse>(
      "nextcloud_list_files",
      () => listBrowserNextcloudFiles(path),
      { path }
    ),
  readNextcloudTextFile: (path: string) =>
    callDesktopOrBrowser<NextcloudTextFileResponse>(
      "nextcloud_read_text_file",
      () => readBrowserNextcloudTextFile(path),
      { path }
    ),
  previewNextcloudFile: async (path: string) => {
    if (isTauriRuntime()) {
      try {
        return desktopPreviewToViewer(
          await invoke<DesktopNextcloudPreviewResponse>("nextcloud_preview_file", {
            path
          })
        );
      } catch (error) {
        throw normalizeCommandError(error);
      }
    }

    return previewBrowserNextcloudFile(path);
  },
  downloadNextcloudFile: (path: string) =>
    callDesktopOrBrowser<NextcloudDownloadResponse>(
      "nextcloud_download_file",
      () => downloadBrowserNextcloudFile(path),
      { path }
    )
};

function desktopPreviewToViewer(
  response: DesktopNextcloudPreviewResponse
): NextcloudPreviewResponse {
  const viewerKind = normalizeViewerKind(response.viewerKind, response.contentType);
  const bytes = new Uint8Array(response.bytes);

  if (viewerKind === "text") {
    return {
      path: response.path,
      filename: response.filename,
      contentType: response.contentType,
      viewerKind,
      text: new TextDecoder("utf-8").decode(bytes)
    };
  }

  return {
    path: response.path,
    filename: response.filename,
    contentType: response.contentType,
    viewerKind,
    objectUrl: URL.createObjectURL(
      new Blob([bytes], { type: response.contentType })
    )
  };
}

function normalizeViewerKind(
  value: string,
  contentType: string
): NextcloudViewerKind {
  if (value === "pdf" || value === "image" || value === "text") {
    return value;
  }

  const normalized = contentType.split(";", 1)[0]?.trim().toLowerCase();
  if (normalized === "application/pdf") {
    return "pdf";
  }
  if (normalized?.startsWith("image/")) {
    return "image";
  }
  return "text";
}
