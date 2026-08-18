import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAgentRunStore } from "./useAgentRunStore";

function startRun(agentId: string, prompt = `Prompt for ${agentId}`) {
  return useAgentRunStore.getState().startRun({
    agentId,
    agentName: `Agent ${agentId}`,
    assistantMessageId: `message-${agentId}`,
    prompt
  });
}

describe("useAgentRunStore", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-14T12:00:00+09:00"));
    useAgentRunStore.getState().resetRuns();
  });

  afterEach(() => {
    useAgentRunStore.getState().resetRuns();
    vi.useRealTimers();
  });

  it("keeps independent frontend runs for multiple agents", () => {
    startRun("1");
    startRun("2");

    vi.advanceTimersByTime(700);

    const runs = useAgentRunStore.getState().runsByAgentId;
    expect(runs["1"].activeStageIndex).toBe(1);
    expect(runs["2"].activeStageIndex).toBe(1);
  });

  it("replaces only the previous run for the same agent", () => {
    const firstRunId = startRun("1", "First prompt");
    startRun("2");
    const replacementRunId = startRun("1", "Replacement prompt");

    const runs = useAgentRunStore.getState().runsByAgentId;
    expect(replacementRunId).not.toBe(firstRunId);
    expect(runs["1"].prompt).toBe("Replacement prompt");
    expect(runs["2"].status).toBe("running");
  });

  it("holds the final stage open until the request lifecycle completes it", () => {
    const runId = startRun("1");

    vi.advanceTimersByTime(7_000);

    let run = useAgentRunStore.getState().runsByAgentId["1"];
    expect(run.status).toBe("running");
    expect(run.activeStageIndex).toBe(3);
    expect(run.durationSeconds).toBeNull();
    expect(useAgentRunStore.getState().latestRunsByAgentId["1"]).toBeUndefined();

    useAgentRunStore.getState().completeRun("1", runId);
    run = useAgentRunStore.getState().runsByAgentId["1"];
    expect(run.status).toBe("completed");
    expect(run.activeStageIndex).toBe(3);
    expect(run.durationSeconds).toBe(7);
    expect(useAgentRunStore.getState().latestRunsByAgentId["1"]).toEqual(run);
  });

  it("preserves the latest terminal run while a replacement is running", () => {
    const firstRunId = startRun("1", "First prompt");
    useAgentRunStore.getState().completeRun("1", firstRunId);

    startRun("1", "Replacement prompt");

    const state = useAgentRunStore.getState();
    expect(state.runsByAgentId["1"]).toMatchObject({
      prompt: "Replacement prompt",
      status: "running"
    });
    expect(state.latestRunsByAgentId["1"]).toMatchObject({
      prompt: "First prompt",
      status: "completed"
    });
  });

  it("preserves cancellation and does not stop another agent", () => {
    const runId = startRun("1");
    startRun("2");

    useAgentRunStore.getState().cancelRun("1", runId);
    vi.advanceTimersByTime(2_800);

    const runs = useAgentRunStore.getState().runsByAgentId;
    expect(runs["1"].status).toBe("cancelled");
    expect(runs["2"]).toMatchObject({
      activeStageIndex: 3,
      status: "running"
    });
    expect(useAgentRunStore.getState().latestRunsByAgentId["1"].status).toBe(
      "cancelled"
    );
  });

  it("does not overwrite a terminal run with a late completion", () => {
    const runId = startRun("1");
    useAgentRunStore.getState().failRun("1", runId);
    useAgentRunStore.getState().completeRun("1", runId);

    expect(useAgentRunStore.getState().runsByAgentId["1"].status).toBe(
      "failed"
    );
    expect(useAgentRunStore.getState().latestRunsByAgentId["1"].status).toBe(
      "failed"
    );
  });

  it("clears current and latest run records together", () => {
    const runId = startRun("1");
    useAgentRunStore.getState().completeRun("1", runId);

    useAgentRunStore.getState().resetRuns();

    expect(useAgentRunStore.getState().runsByAgentId).toEqual({});
    expect(useAgentRunStore.getState().latestRunsByAgentId).toEqual({});
  });
});
