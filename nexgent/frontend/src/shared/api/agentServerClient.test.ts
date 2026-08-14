import { afterEach, describe, expect, it, vi } from "vitest";

import {
  AgentServerError,
  agentServerClient,
  readFinalAssistantResponse,
  readWeeklyReportResult
} from "./agentServerClient";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("readFinalAssistantResponse", () => {
  it("parses CRLF events split at every byte and preserves split UTF-8 text", async () => {
    const payload = [
      "event: metadata\r\n",
      'data: {"run_id":"run-1"}\r\n\r\n',
      "event: values\r\n",
      'data: {"message":"안녕"}\r\n\r\n',
      "event: values\r\n",
      'data: {"message":"안녕","response":"반가워요 👋"}\r\n\r\n'
    ].join("");
    const bytes = new TextEncoder().encode(payload);

    await expect(
      readFinalAssistantResponse(byteStream([...bytes].map((byte) => [byte])))
    ).resolves.toBe("반가워요 👋");
  });

  it("uses the last response event and flushes a final event without a blank line", async () => {
    const payload = [
      'event: values\ndata: {"response":"draft"}\n\n',
      'event: values\ndata: {"response":"final"}'
    ].join("");

    const streamedResponses: string[] = [];
    await expect(
      readFinalAssistantResponse(textStream([payload]), (response) =>
        streamedResponses.push(response)
      )
    ).resolves.toBe("final");
    expect(streamedResponses).toEqual(["draft", "final"]);
  });

  it("combines custom token deltas and verifies the final values response", async () => {
    const payload = [
      'event: custom\ndata: {"response_delta":"Hello"}\n\n',
      'event: custom\ndata: {"response_delta":" world"}\n\n',
      'event: values\ndata: {"message":"hi","response":"Hello world"}\n\n'
    ].join("");
    const streamedResponses: string[] = [];

    await expect(
      readFinalAssistantResponse(textStream([payload]), (response) =>
        streamedResponses.push(response)
      )
    ).resolves.toBe("Hello world");
    expect(streamedResponses).toEqual(["Hello", "Hello world"]);
  });

  it("ignores malformed metadata and values events without a response", async () => {
    const payload = [
      "event: metadata\ndata: not-json\n\n",
      'event: values\ndata: {"message":"hello"}\n\n',
      'event: values\ndata: {"response":"answer"}\n\n'
    ].join("");

    await expect(readFinalAssistantResponse(textStream([payload]))).resolves.toBe(
      "answer"
    );
  });

  it.each([
    ["invalid JSON", "event: values\ndata: {bad}\n\n"],
    ["invalid custom delta", 'event: custom\ndata: {"response_delta":42}\n\n'],
    ["invalid response type", 'event: values\ndata: {"response":42}\n\n'],
    ["missing final response", 'event: values\ndata: {"message":"hi"}\n\n'],
    ["empty stream", ""]
  ])("reports %s as a malformed stream", async (_name, payload) => {
    await expect(readFinalAssistantResponse(textStream([payload]))).rejects.toMatchObject({
      code: "malformed_stream"
    });
  });
});

describe("agentServerClient", () => {
  it("checks server availability through the same-origin browser proxy", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("ok"));
    vi.stubGlobal("fetch", fetchMock);

    await expect(agentServerClient.checkHealth()).resolves.toBe(true);

    expect(fetchMock).toHaveBeenCalledWith(
      "/agent-server/ok",
      expect.objectContaining({ method: "GET" })
    );
  });

  it("sends one message and cancels the run when its stream disconnects", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        textStream(['event: values\ndata: {"response":"done"}\n\n'])
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(agentServerClient.streamChat("current message")).resolves.toBe(
      "done"
    );
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/agent-server/runs/stream");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      assistant_id: "chat",
      input: { message: "current message" },
      stream_mode: ["custom", "values"],
      on_disconnect: "cancel"
    });
    expect(init.headers).toEqual({
      Accept: "text/event-stream",
      "Content-Type": "application/json"
    });
  });

  it("runs the weekly reporter with the selected reporting period", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(textStream([weeklyReportStream()]))
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      agentServerClient.runWeeklyReport({
        week_start: "2026-08-03",
        timezone: "Asia/Seoul"
      })
    ).resolves.toMatchObject({ status: "completed", reports: [{ ward_id: 12031 }] });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/agent-server/runs/stream");
    expect(JSON.parse(init.body as string)).toEqual({
      assistant_id: "ansimk_weekly_reporter",
      input: { week_start: "2026-08-03", timezone: "Asia/Seoul" },
      stream_mode: ["custom", "values"],
      on_disconnect: "cancel"
    });
  });

  it("reports HTTP failures with their status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("not ready", { status: 503 }))
    );

    await expect(agentServerClient.streamChat("hello")).rejects.toMatchObject({
      code: "http_error",
      status: 503
    });
  });

  it("reports network failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));

    await expect(agentServerClient.checkHealth()).rejects.toMatchObject({
      code: "network_error"
    });
  });

  it("reports cancellation separately", async () => {
    const controller = new AbortController();
    controller.abort();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new DOMException("Aborted", "AbortError"))
    );

    await expect(
      agentServerClient.streamChat("hello", { signal: controller.signal })
    ).rejects.toEqual(
      expect.objectContaining<Partial<AgentServerError>>({ code: "cancelled" })
    );
  });

  it("rejects a successful response without a stream body", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null)));

    await expect(agentServerClient.streamChat("hello")).rejects.toMatchObject({
      code: "malformed_stream"
    });
  });
});

describe("readWeeklyReportResult", () => {
  it("reports progress and returns the final batch result", async () => {
    const progress: string[] = [];
    const result = await readWeeklyReportResult(
      textStream([weeklyReportStream()]),
      (event) => progress.push(event.event)
    );

    expect(progress).toEqual([
      "batch_started",
      "risk_data_loaded",
      "ward_report_ready",
      "batch_completed"
    ]);
    expect(result.reports[0]).toMatchObject({
      display_name: "Ward 12031",
      generation_mode: "llm"
    });
  });

  it("rejects a completed event with an invalid report contract", async () => {
    await expect(
      readWeeklyReportResult(
        textStream([
          'event: values\ndata: {"status":"completed","reports":[]}\n\n'
        ])
      )
    ).rejects.toMatchObject({ code: "malformed_stream" });
  });
});

function weeklyReportStream() {
  const report = {
    status: "completed",
    week_start: "2026-08-03",
    week_end: "2026-08-10",
    timezone: "Asia/Seoul",
    reports: [
      {
        ward_id: 12031,
        display_name: "Ward 12031",
        metrics: {
          ward_id: 12031,
          display_name: "Ward 12031",
          week_start: "2026-08-03",
          week_end: "2026-08-10",
          current: metricSnapshot(),
          previous: metricSnapshot(),
          delta: {
            danger_days: 0
          }
        },
        markdown: "# Ward 12031\n\n## 이번 주 요약",
        generation_mode: "llm"
      }
    ],
    warnings: []
  };

  return [
    'event: custom\ndata: {"event":"batch_started","week_start":"2026-08-03"}\n\n',
    'event: custom\ndata: {"event":"risk_data_loaded","ward_count":1,"selection_truncated":true}\n\n',
    'event: custom\ndata: {"event":"ward_report_ready","generation_mode":"llm"}\n\n',
    'event: custom\ndata: {"event":"batch_completed","report_count":1,"fallback_count":0}\n\n',
    `event: values\ndata: ${JSON.stringify(report)}\n\n`
  ].join("");
}

function metricSnapshot() {
  return {
    danger_days: 3
  };
}

function textStream(chunks: string[]) {
  const encoder = new TextEncoder();
  return byteStream(chunks.map((chunk) => encoder.encode(chunk)));
}

function byteStream(chunks: ArrayLike<number>[]) {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(Uint8Array.from(chunk));
      }
      controller.close();
    }
  });
}
