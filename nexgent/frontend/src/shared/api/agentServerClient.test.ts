import { afterEach, describe, expect, it, vi } from "vitest";

import {
  AgentServerError,
  agentServerClient,
  readFinalAssistantResponse
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
    expect(url).toBe("/api/chat/stream");
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("Accept")).toBe("text/event-stream");
    expect(init.body).toBeInstanceOf(FormData);
    const body = init.body as FormData;
    expect(body.get("prompt")).toBe("current message");
    expect(body.getAll("files")).toEqual(files);
  });

  it("sends text-only questions to the dedicated RAG Chat API", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        textStream([
          'event: custom\ndata: {"response_delta":"grounded"}\n\n',
          'event: values\ndata: {"response":"grounded answer"}\n\n'
        ])
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      agentServerClient.streamRagChat("original question")
    ).resolves.toBe("grounded answer");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/rag/chat/stream");
    expect(init).toMatchObject({
      method: "POST",
      headers: {
        accept: "text/event-stream",
        "content-type": "application/json"
      },
      body: JSON.stringify({ question: "original question" })
    });
    expect(init.body).not.toBeInstanceOf(FormData);
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
              message: "brief.pdf exceeds the 50 MB per-file limit.",
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


it("sends the session ID with the current prompt and no client-owned history", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(
    'event: custom\ndata: {"response_complete":"remembered"}\n\n',
    { headers: { "Content-Type": "text/event-stream" } }
  ));
  vi.stubGlobal("fetch", fetchMock);
  const sessionId = "8c3d48cd-ea61-45a0-87ec-2c7c33dbd725";
  await expect(agentServerClient.streamChat("Follow up", { sessionId })).resolves.toBe("remembered");
  const body = fetchMock.mock.calls[0][1].body as FormData;
  expect(body.get("session_id")).toBe(sessionId);
  expect(body.get("prompt")).toBe("Follow up");
  expect(body.has("history")).toBe(false);
});
