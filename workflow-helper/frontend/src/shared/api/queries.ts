import { useMutation, useQuery } from "@tanstack/react-query";

import { desktopApi } from "./client";

export const queryKeys = {
  workspace: ["workspace"] as const,
  health: ["system-health"] as const,
  tasks: ["tasks"] as const,
  approvals: ["approvals"] as const,
  agents: ["agents"] as const,
  activity: ["activity"] as const,
  nextcloudStatus: ["nextcloud-status"] as const,
  nextcloudFiles: (path: string) => ["nextcloud-files", path] as const,
  nextcloudTextFile: (path: string) => ["nextcloud-text-file", path] as const,
  nextcloudPreview: (path: string) => ["nextcloud-preview", path] as const
};

export function useWorkspace() {
  return useQuery({
    queryKey: queryKeys.workspace,
    queryFn: desktopApi.getWorkspace
  });
}

export function useSystemHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: desktopApi.getSystemHealth,
    refetchInterval: 30_000
  });
}

export function useTasks() {
  return useQuery({
    queryKey: queryKeys.tasks,
    queryFn: desktopApi.listTasks
  });
}

export function useApprovals() {
  return useQuery({
    queryKey: queryKeys.approvals,
    queryFn: desktopApi.listApprovals
  });
}

export function useAgents() {
  return useQuery({
    queryKey: queryKeys.agents,
    queryFn: desktopApi.listAgents
  });
}

export function useActivity() {
  return useQuery({
    queryKey: queryKeys.activity,
    queryFn: desktopApi.listActivity
  });
}

export function useNextcloudStatus() {
  return useQuery({
    queryKey: queryKeys.nextcloudStatus,
    queryFn: desktopApi.getNextcloudStatus,
    refetchInterval: 30_000
  });
}

export function useNextcloudFiles(path: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.nextcloudFiles(path),
    queryFn: () => desktopApi.listNextcloudFiles(path),
    enabled
  });
}

export function useNextcloudTextFile(path: string, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.nextcloudTextFile(path),
    queryFn: () => desktopApi.readNextcloudTextFile(path),
    enabled
  });
}

export function useNextcloudPreviewFile(path: string, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.nextcloudPreview(path),
    queryFn: () => desktopApi.previewNextcloudFile(path),
    enabled,
    gcTime: 0,
    staleTime: 0
  });
}

export function useNextcloudDownloadFile() {
  return useMutation({
    mutationFn: (path: string) => desktopApi.downloadNextcloudFile(path)
  });
}
