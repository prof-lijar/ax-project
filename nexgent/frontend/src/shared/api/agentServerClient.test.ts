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
