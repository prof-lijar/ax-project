export const DEFAULT_AGENT_SERVER_BASE_URL = "http://192.168.0.18:2024";

export type AgentServerErrorCode =
  | "cancelled"
  | "http_error"
  | "malformed_stream"
  | "network_error";

export class AgentServerError extends Error {
  readonly code: AgentServerErrorCode;
  readonly status?: number;
  readonly originalCause?: unknown;

  constructor(
    code: AgentServerErrorCode,
    message: string,
    options?: { cause?: unknown; status?: number }
  ) {
    super(message);
    this.name = "AgentServerError";
    this.code = code;
    this.status = options?.status;
    this.originalCause = options?.cause;
  }
}

interface RequestOptions {
  signal?: AbortSignal;
}

interface ChatRequestOptions extends RequestOptions {
  onResponse?: (response: string) => void;
}

interface SseEvent {
  event: string;
  data: string;
}

const configuredBaseUrl = (
  import.meta.env.VITE_AGENT_SERVER_BASE_URL?.trim() ||
  DEFAULT_AGENT_SERVER_BASE_URL
).replace(/\/+$/, "");

export const agentServerClient = {
  async checkHealth({ signal }: RequestOptions = {}): Promise<boolean> {
    try {
      const response = await fetch(agentServerUrl("/ok"), {
        method: "GET",
        headers: { Accept: "application/json" },
        signal
      });

      if (!response.ok) {
        throw await httpError(response, "Health check failed");
      }
      return true;
    } catch (error) {
      throw normalizeRequestError(error, signal, "Unable to reach the Agent Server.");
    }
  },

  async streamChat(
    message: string,
    { signal, onResponse }: ChatRequestOptions = {}
  ): Promise<string> {
    try {
      const response = await fetch(agentServerUrl("/runs/stream"), {
        method: "POST",
        headers: {
          Accept: "text/event-stream",
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          assistant_id: "chat",
          input: { message },
          stream_mode: ["custom", "values"],
          on_disconnect: "cancel"
        }),
        signal
      });

      if (!response.ok) {
        throw await httpError(response, "Chat request failed");
      }
      if (!response.body) {
        throw new AgentServerError(
          "malformed_stream",
          "The Agent Server returned an empty response stream."
        );
      }

      return await readFinalAssistantResponse(response.body, onResponse);
    } catch (error) {
      throw normalizeRequestError(
        error,
        signal,
        "The Agent Server could not complete the request."
      );
    }
  }
};

export async function readFinalAssistantResponse(
  stream: ReadableStream<Uint8Array>,
  onResponse?: (response: string) => void
): Promise<string> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let finalResponse: string | null = null;
  let streamedResponse = "";
  const parser = new SseParser((event) => {
    if (event.event === "custom") {
      const deltaEvent = parseJsonEvent(event.data, "streamed chat data");
      if (
        typeof deltaEvent !== "object" ||
        deltaEvent === null ||
        !("response_delta" in deltaEvent) ||
        typeof (deltaEvent as { response_delta?: unknown }).response_delta !==
          "string"
      ) {
        throw new AgentServerError(
          "malformed_stream",
          "The Agent Server returned an invalid response delta."
        );
      }
      streamedResponse += (
        deltaEvent as { response_delta: string }
      ).response_delta;
      onResponse?.(streamedResponse);
      return;
    }
    if (event.event !== "values") {
      return;
    }

    const value = parseJsonEvent(event.data, "chat data");
    if (typeof value !== "object" || value === null) {
      throw new AgentServerError(
        "malformed_stream",
        "The Agent Server returned an invalid chat event."
      );
    }

    if (!("response" in value)) {
      return;
    }

    const response = (value as { response?: unknown }).response;
    if (typeof response !== "string") {
      throw new AgentServerError(
        "malformed_stream",
        "The Agent Server returned an invalid assistant response."
      );
    }
    finalResponse = response;
    if (response !== streamedResponse) {
      streamedResponse = response;
      onResponse?.(response);
    }
  });

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      parser.push(decoder.decode(value, { stream: true }));
    }
    parser.push(decoder.decode());
    parser.finish();
  } finally {
    reader.releaseLock();
  }

  if (finalResponse === null) {
    throw new AgentServerError(
      "malformed_stream",
      "The Agent Server stream ended without an assistant response."
    );
  }

  return finalResponse;
}

function parseJsonEvent(data: string, description: string): unknown {
  try {
    return JSON.parse(data);
  } catch (error) {
    throw new AgentServerError(
      "malformed_stream",
      `The Agent Server returned malformed ${description}.`,
      { cause: error }
    );
  }
}

class SseParser {
  private buffer = "";
  private eventName = "";
  private dataLines: string[] = [];

  constructor(private readonly onEvent: (event: SseEvent) => void) {}

  push(chunk: string) {
    this.buffer += chunk;

    let newlineIndex = this.buffer.indexOf("\n");
    while (newlineIndex !== -1) {
      const rawLine = this.buffer.slice(0, newlineIndex);
      this.buffer = this.buffer.slice(newlineIndex + 1);
      this.consumeLine(rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine);
      newlineIndex = this.buffer.indexOf("\n");
    }
  }

  finish() {
    if (this.buffer.length > 0) {
      const line = this.buffer.endsWith("\r")
        ? this.buffer.slice(0, -1)
        : this.buffer;
      this.consumeLine(line);
      this.buffer = "";
    }
    this.dispatch();
  }

  private consumeLine(line: string) {
    if (line === "") {
      this.dispatch();
      return;
    }
    if (line.startsWith(":")) {
      return;
    }

    const colonIndex = line.indexOf(":");
    const field = colonIndex === -1 ? line : line.slice(0, colonIndex);
    let value = colonIndex === -1 ? "" : line.slice(colonIndex + 1);
    if (value.startsWith(" ")) {
      value = value.slice(1);
    }

    if (field === "event") {
      this.eventName = value;
    } else if (field === "data") {
      this.dataLines.push(value);
    }
  }

  private dispatch() {
    if (this.dataLines.length > 0) {
      this.onEvent({
        event: this.eventName || "message",
        data: this.dataLines.join("\n")
      });
    }
    this.eventName = "";
    this.dataLines = [];
  }
}

function agentServerUrl(path: string) {
  const baseUrl = isTauriRuntime() ? configuredBaseUrl : "/agent-server";
  return `${baseUrl}${path}`;
}

function isTauriRuntime() {
  return (
    typeof window !== "undefined" &&
    "__TAURI_INTERNALS__" in (window as Window & { __TAURI_INTERNALS__?: unknown })
  );
}

async function httpError(response: Response, prefix: string) {
  let detail = "";
  try {
    detail = (await response.text()).trim().slice(0, 300);
  } catch {
    // The status code still provides a useful error if the body cannot be read.
  }
  const suffix = detail ? `: ${detail}` : ".";
  return new AgentServerError(
    "http_error",
    `${prefix} (${response.status})${suffix}`,
    { status: response.status }
  );
}

function normalizeRequestError(
  error: unknown,
  signal: AbortSignal | undefined,
  fallbackMessage: string
) {
  if (error instanceof AgentServerError) {
    return error;
  }
  if (signal?.aborted || (error instanceof DOMException && error.name === "AbortError")) {
    return new AgentServerError("cancelled", "The request was cancelled.", {
      cause: error
    });
  }
  return new AgentServerError("network_error", fallbackMessage, { cause: error });
}
