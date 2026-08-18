import { create } from "zustand";

export const MOCK_AGENT_RUN_STAGES = [
  "Planning request",
  "Reading relevant data",
  "Processing information",
  "Generating response"
] as const;

export type MockAgentRunStatus =
  | "running"
  | "completed"
  | "cancelled"
  | "failed";

export interface MockAgentRun {
  runId: string;
  agentId: string;
  agentName: string;
  assistantMessageId: string;
  prompt: string;
  activeStageIndex: number;
  startedAt: number;
  completedAt: number | null;
  durationSeconds: number | null;
  status: MockAgentRunStatus;
}

interface StartMockAgentRunInput {
  agentId: string;
  agentName: string;
  assistantMessageId: string;
  prompt: string;
}

interface AgentRunState {
  runsByAgentId: Record<string, MockAgentRun>;
  latestRunsByAgentId: Record<string, MockAgentRun>;
  startRun: (input: StartMockAgentRunInput) => string;
  completeRun: (agentId: string, runId: string) => void;
  failRun: (agentId: string, runId: string) => void;
  cancelRun: (agentId: string, runId?: string) => void;
  resetRuns: () => void;
}

const MOCK_STAGE_INTERVAL_MS = 700;
const runTimers = new Map<string, ReturnType<typeof setInterval>>();
let runSequence = 0;

export const useAgentRunStore = create<AgentRunState>((set, get) => ({
  runsByAgentId: {},
  latestRunsByAgentId: {},
  startRun: (input) => {
    clearRunTimer(input.agentId);
    runSequence += 1;
    const startedAt = Date.now();
    const runId = `${startedAt}-${runSequence}-${input.agentId}`;

    set((state) => ({
      runsByAgentId: {
        ...state.runsByAgentId,
        [input.agentId]: {
          ...input,
          runId,
          activeStageIndex: 0,
          startedAt,
          completedAt: null,
          durationSeconds: null,
          status: "running"
        }
      }
    }));

    const timer = setInterval(() => {
      const current = get().runsByAgentId[input.agentId];
      if (!current || current.runId !== runId || current.status !== "running") {
        clearRunTimer(input.agentId);
        return;
      }

      const finalStageIndex = MOCK_AGENT_RUN_STAGES.length - 1;
      if (current.activeStageIndex < finalStageIndex) {
        set((state) => ({
          runsByAgentId: {
            ...state.runsByAgentId,
            [input.agentId]: {
              ...current,
              activeStageIndex: current.activeStageIndex + 1
            }
          }
        }));
        return;
      }

      // The stage timer is presentation-only. Keep the final stage active
      // until Chat reports the actual request outcome.
      set((state) => ({
        runsByAgentId: {
          ...state.runsByAgentId,
          [input.agentId]: { ...current }
        }
      }));
    }, MOCK_STAGE_INTERVAL_MS);
    runTimers.set(input.agentId, timer);

    return runId;
  },
  completeRun: (agentId, runId) => {
    finishRun(agentId, runId, "completed", set, get);
  },
  failRun: (agentId, runId) => {
    finishRun(agentId, runId, "failed", set, get);
  },
  cancelRun: (agentId, runId) => {
    const current = get().runsByAgentId[agentId];
    if (
      !current ||
      current.status !== "running" ||
      (runId && current.runId !== runId)
    ) {
      return;
    }
    finishRun(agentId, current.runId, "cancelled", set, get);
  },
  resetRuns: () => {
    for (const agentId of runTimers.keys()) {
      clearRunTimer(agentId);
    }
    set({ runsByAgentId: {}, latestRunsByAgentId: {} });
  }
}));

export function getMockAgentRunStageState(
  run: MockAgentRun,
  stageIndex: number
): "pending" | "active" | "completed" {
  if (run.status === "completed" || stageIndex < run.activeStageIndex) {
    return "completed";
  }
  if (run.status === "running" && stageIndex === run.activeStageIndex) {
    return "active";
  }
  return "pending";
}

function finishRun(
  agentId: string,
  runId: string,
  status: Exclude<MockAgentRunStatus, "running">,
  set: (
    update:
      | Partial<AgentRunState>
      | ((state: AgentRunState) => Partial<AgentRunState>)
  ) => void,
  get: () => AgentRunState
) {
  const current = get().runsByAgentId[agentId];
  if (!current || current.runId !== runId || current.status !== "running") {
    return;
  }

  clearRunTimer(agentId);
  const completedAt = Date.now();
  const finishedRun: MockAgentRun = {
    ...current,
    activeStageIndex:
      status === "completed"
        ? MOCK_AGENT_RUN_STAGES.length - 1
        : current.activeStageIndex,
    completedAt,
    durationSeconds: (completedAt - current.startedAt) / 1000,
    status
  };
  set((state) => ({
    runsByAgentId: {
      ...state.runsByAgentId,
      [agentId]: finishedRun
    },
    latestRunsByAgentId: {
      ...state.latestRunsByAgentId,
      [agentId]: finishedRun
    }
  }));
}

function clearRunTimer(agentId: string) {
  const timer = runTimers.get(agentId);
  if (timer !== undefined) {
    clearInterval(timer);
    runTimers.delete(agentId);
  }
}
