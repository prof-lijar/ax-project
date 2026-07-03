import { useQuery } from "@tanstack/react-query";

import { desktopApi } from "./client";

export const queryKeys = {
  workspace: ["workspace"] as const,
  health: ["system-health"] as const,
  tasks: ["tasks"] as const,
  approvals: ["approvals"] as const,
  agents: ["agents"] as const,
  activity: ["activity"] as const
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
