import { invoke } from "@tauri-apps/api/core";

import {
  activity,
  agents,
  approvals,
  systemHealth,
  tasks,
  workspace
} from "./mockData";
import {
  nextcloudFiles,
  nextcloudStatus,
  nextcloudTextFile
} from "./nextcloudMockData";
import type {
  ActivityEvent,
  AgentSummary,
  ApprovalRequest,
  CommandError,
  SystemHealth,
  TaskSummary,
  WorkspaceOverview
} from "../types/domain";
import type {
  NextcloudListFilesResponse,
  NextcloudStatus,
  NextcloudTextFileResponse
} from "../types/nextcloud";

type TauriWindow = Window & { __TAURI_INTERNALS__?: unknown };

const isTauriRuntime = () =>
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in (window as TauriWindow);

const delay = async () => new Promise((resolve) => window.setTimeout(resolve, 90));

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
  getWorkspace: () =>
    callCommand<WorkspaceOverview>("workspace_get", () => workspace),
  getSystemHealth: () =>
    callCommand<SystemHealth>("system_health", () => systemHealth),
  listTasks: () => callCommand<TaskSummary[]>("tasks_list", () => tasks),
  getTask: (id: string) =>
    callCommand<TaskSummary>(
      "tasks_get",
      () => {
        const task = tasks.find((item) => item.id === id);
        if (!task) {
          throw normalizeCommandError({
            code: "not_found",
            message: `Task with id '${id}' was not found.`
          });
        }
        return task;
      },
      { id }
    ),
  listApprovals: () =>
    callCommand<ApprovalRequest[]>("approvals_list", () => approvals),
  getApproval: (id: string) =>
    callCommand<ApprovalRequest>(
      "approvals_get",
      () => {
        const approval = approvals.find((item) => item.id === id);
        if (!approval) {
          throw normalizeCommandError({
            code: "not_found",
            message: `Approval request with id '${id}' was not found.`
          });
        }
        return approval;
      },
      { id }
    ),
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
  listActivity: () =>
    callCommand<ActivityEvent[]>("activity_list", () => activity),
  getNextcloudStatus: () =>
    callCommand<NextcloudStatus>("nextcloud_health", () => nextcloudStatus),
  listNextcloudFiles: (path: string) =>
    callCommand<NextcloudListFilesResponse>(
      "nextcloud_list_files",
      () => nextcloudFiles(path),
      { path }
    ),
  readNextcloudTextFile: (path: string) =>
    callCommand<NextcloudTextFileResponse>(
      "nextcloud_read_text_file",
      () => nextcloudTextFile(path),
      { path }
    ),
  getNextcloudDownloadUrl: (path: string) =>
    callCommand<string>(
      "nextcloud_download_url",
      () =>
        `http://127.0.0.1:8000/api/nextcloud/files/download?path=${encodeURIComponent(
          path
        )}`,
      { path }
    )
};
