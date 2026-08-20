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

  it("completes attachment streams without values events", async () => {
    const payload = [
      'event: custom\ndata: {"response_delta":"Visual"}\n\n',
      'event: custom\ndata: {"response_delta":" answer"}\n\n',
      'event: custom\ndata: {"response_complete":"Visual answer"}\n\n'
    ].join("");
    const streamedResponses: string[] = [];

    await expect(
      readFinalAssistantResponse(textStream([payload]), (response) =>
        streamedResponses.push(response)
      )
    ).resolves.toBe("Visual answer");
    expect(streamedResponses).toEqual(["Visual", "Visual answer"]);
  });

  it("surfaces safe streamed request errors", async () => {
    const payload =
      'event: custom\ndata: {"error":{"schema_version":"1","code":"vision_not_supported","message":"Image attachments are not supported by the configured model.","filename":"scan.png"}}\n\n';

    await expect(
      readFinalAssistantResponse(textStream([payload]))
    ).rejects.toMatchObject({
      code: "request_error",
      filename: "scan.png",
      serverCode: "vision_not_supported",
      message: "scan.png: Image attachments are not supported by the configured model."
    });
  });

  it("surfaces safe backend stream errors", async () => {
    const payload =
      'event: error\ndata: {"error":{"schema_version":"1","code":"agent_server_stream_error","message":"The chat stream ended unexpectedly."}}\n\n';

    await expect(
      readFinalAssistantResponse(textStream([payload]))
    ).rejects.toMatchObject({
      code: "request_error",
      message: "The chat stream ended unexpectedly."
    });
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

  it("sends prompt and files to the backend multipart chat boundary", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        textStream(['event: values\ndata: {"response":"done"}\n\n'])
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    const files = [
      new File(["notes"], "notes.md", { type: "text/markdown" }),
      new File([new Uint8Array([1, 2, 3])], "photo.png", {
        type: "image/png"
      })
    ];
    await expect(
      agentServerClient.streamChat("current message", { files })
    ).resolves.toBe("done");
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8000/api/chat/stream");
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ Accept: "text/event-stream" });
    expect(init.body).toBeInstanceOf(FormData);
    const body = init.body as FormData;
    expect(body.get("prompt")).toBe("current message");
    expect(body.getAll("files")).toEqual(files);
  });

  it("runs the weekly reporter with the selected reporting period", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(textStream([weeklyReportStream()]))
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      agentServerClient.runWeeklyReport({
        week_start: "2026-08-03",
        timezone: "Asia/Seoul",
        limit: 12
      })
    ).resolves.toMatchObject({ status: "completed", reports: [{ ward_id: 12031 }] });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/agent-server/runs/stream");
    expect(JSON.parse(init.body as string)).toEqual({
      assistant_id: "ansimk_weekly_reporter",
      input: { week_start: "2026-08-03", timezone: "Asia/Seoul", limit: 12 },
      config: { max_concurrency: 1 },
      stream_mode: ["custom", "values"],
      stream_subgraphs: true,
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

  it("maps structured attachment validation failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              schema_version: "1",
              code: "attachment_too_large",
              message: "brief.pdf exceeds the 10 MB per-file limit.",
              filename: "brief.pdf"
            }
          }),
          {
            status: 413,
            headers: { "Content-Type": "application/json" }
          }
        )
      )
    );

    await expect(agentServerClient.streamChat("hello")).rejects.toMatchObject({
      code: "attachment_error",
      filename: "brief.pdf",
      serverCode: "attachment_too_large",
      status: 413,
      message: expect.stringContaining("brief.pdf exceeds")
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
          'event: values\ndata: {"status":"completed","reports":[],"skipped":[],"next_cursor":null,"warnings":[]}\n\n'
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
            ...metricDelta(),
            danger_days: 0
          }
        },
        narrative: {
          headline: "차분한 한 주였어요",
          analysis_text: "확인된 주간 지표를 바탕으로 생활 흐름을 정리한 충분히 긴 분석 문장입니다. 이전 주와 비교해 눈에 띄는 변화가 크지 않아 평소 리듬을 이어가고 있는 모습이에요.",
          observations: ["주간 흐름이 안정적으로 이어졌어요."],
          suggestions: ["평소처럼 가볍게 안부를 나눠보세요."]
        },
        markdown: "# Ward 12031\n\n## 이번 주 요약",
        generation_mode: "llm",
        generation: {
          prompt_version: "weekly-ward-v1",
          model: "test-model",
          validation_status: "passed",
          fallback_reason: null
        }
      }
    ],
    skipped: [],
    next_cursor: "next-page",
    warnings: []
  };

  return [
    'event: custom\ndata: {"event":"batch_started","week_start":"2026-08-03"}\n\n',
    'event: custom\ndata: {"event":"risk_data_loaded","ward_count":1,"selection_truncated":true}\n\n',
    'event: custom|build_ward_report:branch-1\ndata: {"event":"ward_report_ready","generation_mode":"llm"}\n\n',
    'event: custom\ndata: {"event":"batch_completed","report_count":1,"fallback_count":0}\n\n',
    `event: values\ndata: ${JSON.stringify(report)}\n\n`
  ].join("");
}

function metricSnapshot() {
  return {
    covered_days: 7,
    daily_summary_count: 7,
    device_count: 1,
    temperature_avg: 23.5,
    temperature_min: 20,
    temperature_max: 27,
    temperature_count: 100,
    humidity_avg: 51,
    humidity_min: 40,
    humidity_max: 62,
    humidity_count: 100,
    light_avg: 120,
    light_min: 0,
    light_max: 400,
    light_count: 100,
    light_on_time_minutes_avg: 310,
    movement_count_avg: 42,
    remote_control_count_avg: 8,
    wake_up_time_avg: "07:30:00",
    sleep_time_avg: "22:40:00",
    night_awake_count_avg: 1,
    risk_detected_count: 3,
    risk_resolved_count: 2,
    risk_score_avg: 0.2,
    danger_days: 3,
    dispatch_request_count: 1,
    unresolved_dispatch_count: 0
  };
}

function metricDelta() {
  return {
    covered_days: 0,
    temperature_avg: 0,
    humidity_avg: 0,
    light_avg: 0,
    light_on_time_minutes_avg: 0,
    movement_count_avg: 0,
    remote_control_count_avg: 0,
    wake_up_time_minutes: 0,
    sleep_time_minutes: 0,
    night_awake_count_avg: 0,
    risk_detected_count: 0,
    risk_resolved_count: 0,
    risk_score_avg: 0,
    danger_days: 0,
    dispatch_request_count: 0,
    unresolved_dispatch_count: 0
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
