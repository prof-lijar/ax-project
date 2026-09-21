import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ScoutClientError,
  resolveScoutServerBaseUrl,
  scoutClient,
  type ScoutRunResponse
} from "./scoutClient";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("scoutClient.run", () => {
  it("posts the normalized Scout contract through the authenticated backend", async () => {
    const payload = scoutResponse();
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(payload));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      scoutClient.run({
        topic: "  고독사 예방 AI IoT 서비스 최근 동향  ",
        keywords: [" AI 돌봄 ", "IoT 모니터링"],
        additional_instructions: "  Focus on public-sector cases.  "
      })
    ).resolves.toEqual(payload);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/scout-api/v1/scout/runs");
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("Content-Type")).toBe(
      "application/json"
    );
    expect(JSON.parse(String(init.body))).toEqual({
      topic: "고독사 예방 AI IoT 서비스 최근 동향",
      keywords: ["AI 돌봄", "IoT 모니터링"],
      additional_instructions: "Focus on public-sector cases."
    });
  });

  it("omits blank additional instructions", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(scoutResponse()));
    vi.stubGlobal("fetch", fetchMock);

    await scoutClient.run({
      topic: "valid topic",
      keywords: [],
      additional_instructions: " \n "
    });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({
      topic: "valid topic",
      keywords: []
    });
  });

  it("ignores legacy direct URL configuration", async () => {
    vi.stubEnv(
      "VITE_SCOUT_API_BASE_URL",
      "  http://192.168.0.18:8091/  "
    );
    vi.resetModules();
    const { scoutClient: configuredScoutClient } = await import(
      "./scoutClient"
    );
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(scoutResponse()));
    vi.stubGlobal("fetch", fetchMock);

    await configuredScoutClient.run({ topic: "valid topic", keywords: [] });

    expect(fetchMock).toHaveBeenCalledWith(
      "/scout-api/v1/scout/runs",
      expect.objectContaining({ method: "POST" })
    );
  });

  it("resolves configured Scout base URLs like the RAG client", () => {
    expect(
      resolveScoutServerBaseUrl("  http://192.168.0.18:8091///  ")
    ).toBe("/scout-api");
  });

  it("rejects invalid requests before using the network", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      scoutClient.run({ topic: " ", keywords: [] })
    ).rejects.toBeInstanceOf(ScoutClientError);
    await expect(
      scoutClient.run({
        topic: "valid topic",
        keywords: [],
        additional_instructions: "x".repeat(2_001)
      })
    ).rejects.toBeInstanceOf(ScoutClientError);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("surfaces FastAPI 503 details without exposing a stack", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ detail: "Scout service is not configured." }, 503)
      )
    );

    await expect(
      scoutClient.run({ topic: "valid topic", keywords: [] })
    ).rejects.toMatchObject({
      status: 503,
      message: "Scout service is not configured."
    });
  });

  it("keeps safe terminal metadata from a failed Scout run", async () => {
    const run = scoutFailure();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ detail: "Scout run failed.", run }, 502)
      )
    );

    await expect(
      scoutClient.run({ topic: "valid topic", keywords: [] })
    ).rejects.toMatchObject({
      status: 502,
      message: "Scout run failed.",
      run
    });
  });

  it("rejects malformed successful responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ ...scoutResponse(), report_artifact: null })
      )
    );

    await expect(
      scoutClient.run({ topic: "valid topic", keywords: [] })
    ).rejects.toMatchObject({
      message: "The Scout service returned an unexpected response."
    });
  });

  it.each([
    ["malformed timestamp", { completed_at: "not-a-timestamp" }],
    ["negative duration", { duration_seconds: -1 }],
    ["mismatched source count", { source_count: 2 }]
  ])("rejects %s in successful responses", async (_label, updates) => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ ...scoutResponse(), ...updates })
      )
    );

    await expect(
      scoutClient.run({ topic: "valid topic", keywords: [] })
    ).rejects.toMatchObject({
      message: "The Scout service returned an unexpected response."
    });
  });

  it("returns a useful network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("failed")));

    await expect(
      scoutClient.run({ topic: "valid topic", keywords: [] })
    ).rejects.toMatchObject({
      status: null,
      message:
        "Could not reach the Scout service. Confirm that it is running and try again."
    });
  });
});

function scoutResponse(): ScoutRunResponse {
  return {
    run_id: "20260828T103000Z-abc123",
    status: "success",
    started_at: "2026-08-28T01:30:00+00:00",
    completed_at: "2026-08-28T01:31:17.896000+00:00",
    duration_seconds: 77.896,
    source_count: 1,
    report:
      "# Scout Report\n\n## Topic\n\nAI 돌봄\n\n## Summary\n\n요약\n\n## Key Findings\n\n- 결과\n\n## Sources\n\n- https://example.com/source",
    sources: ["https://example.com/source"],
    report_artifact: "runs/20260828T103000Z-abc123/report.md",
    log_artifact: "runs/20260828T103000Z-abc123/execution.jsonl"
  };
}

function scoutFailure() {
  return {
    run_id: "20260828T103200Z-failed",
    status: "failed" as const,
    started_at: "2026-08-28T01:32:00+00:00",
    completed_at: "2026-08-28T01:32:12.341000+00:00",
    duration_seconds: 12.341,
    source_count: 0 as const,
    log_artifact: "runs/20260828T103200Z-failed/execution.jsonl"
  };
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}
