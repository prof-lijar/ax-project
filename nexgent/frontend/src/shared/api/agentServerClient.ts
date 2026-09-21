import { authenticatedFetch } from "./authenticatedFetch";
import { backendUrl } from "./nextcloudBackendClient";


export type AgentServerErrorCode =
  | "attachment_error"
  | "cancelled"
  | "http_error"
  | "malformed_stream"
  | "network_error"
  | "request_error";

export class AgentServerError extends Error {
  readonly code: AgentServerErrorCode;
  readonly status?: number;
  readonly serverCode?: string;
  readonly filename?: string;
  readonly originalCause?: unknown;

  constructor(
    code: AgentServerErrorCode,
    message: string,
    options?: {
      cause?: unknown;
      filename?: string;
      serverCode?: string;
      status?: number;
    }
  ) {
    super(message);
    this.name = "AgentServerError";
    this.code = code;
    this.status = options?.status;
    this.serverCode = options?.serverCode;
    this.filename = options?.filename;
    this.originalCause = options?.cause;
  }
}

interface RequestOptions {
  signal?: AbortSignal;
}

interface ChatRequestOptions extends RequestOptions {
  sessionId?: string;
  files?: readonly File[];
  onResponse?: (response: string) => void;
}

interface RagChatRequestOptions extends RequestOptions {
  onResponse?: (response: string) => void;
}

interface SseEvent {
  event: string;
  data: string;
}

export const agentServerClient = {
  async checkHealth({ signal }: RequestOptions = {}): Promise<boolean> {
    try {
      const response = await authenticatedFetch(agentServerUrl("/ok"), {
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
    { files = [], sessionId, signal, onResponse }: ChatRequestOptions = {}
  ): Promise<string> {
    try {
      const body = new FormData();
      body.append("prompt", message);
      if (sessionId) body.append("session_id", sessionId);
      for (const file of files) {
        body.append("files", file, file.name);
      }

      const response = await authenticatedFetch(backendUrl("/api/chat/stream"), {
        method: "POST",
        headers: { Accept: "text/event-stream" },
        body,
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
  },

  async streamRagChat(
    question: string,
    { signal, onResponse }: RagChatRequestOptions = {}
  ): Promise<string> {
    try {
      const response = await authenticatedFetch(backendUrl("/api/rag/chat/stream"), {
        method: "POST",
        headers: {
          Accept: "text/event-stream",
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ question }),
        signal
      });

      if (!response.ok) {
        throw await httpError(response, "RAG Chat request failed");
      }
      if (!response.body) {
        throw new AgentServerError(
          "malformed_stream",
          "The RAG Chat service returned an empty response stream."
        );
      }

      return await readFinalAssistantResponse(response.body, onResponse);
    } catch (error) {
      throw normalizeRequestError(
        error,
        signal,
        "The RAG Chat service could not complete the request."
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
  let fullyRead = false;
  const parser = new SseParser((event) => {
    if (event.event === "custom" || event.event === "error") {
      const deltaEvent = parseJsonEvent(event.data, "streamed chat data");
      const requestError = parseStreamedRequestError(deltaEvent);
      if (requestError) {
        throw requestError;
      }
      if (event.event === "error") {
        throw new AgentServerError(
          "malformed_stream",
          "The chat service returned an invalid error event."
        );
      }
      if (
        isRecord(deltaEvent) &&
        typeof deltaEvent.response_complete === "string"
      ) {
        finalResponse = deltaEvent.response_complete;
        if (finalResponse !== streamedResponse) {
          streamedResponse = finalResponse;
          onResponse?.(finalResponse);
        }
        return;
      }
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
    fullyRead = true;
  } finally {
    if (!fullyRead) {
      try {
        await reader.cancel();
      } catch {
        // Preserve the original stream/parser error.
      }
    }
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

function parseStreamedRequestError(value: unknown): AgentServerError | null {
  if (!isRecord(value)) {
    return null;
  }

  const nested = isRecord(value.error) ? value.error : value;
  const code = nested.code ?? nested.error_code;
  const message = nested.message ?? nested.error_message;
  if (typeof code !== "string" || typeof message !== "string") {
    return null;
  }
  const filename = typeof nested.filename === "string" ? nested.filename : undefined;
  return new AgentServerError(
    "request_error",
    structuredErrorMessage(message, filename),
    { filename, serverCode: code }
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
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
  const baseUrl = "/agent-server";
  return `${baseUrl}${path}`;
}



async function httpError(response: Response, prefix: string) {
  let detail = "";
  let errorCode: AgentServerErrorCode = "http_error";
  let filename: string | undefined;
  let serverCode: string | undefined;
  try {
    const rawBody = (await response.text()).trim();
    if (rawBody) {
      try {
        const parsed = JSON.parse(rawBody) as unknown;
        if (isRecord(parsed)) {
          const nested = isRecord(parsed.detail)
            ? parsed.detail
            : isRecord(parsed.error)
              ? parsed.error
              : parsed;
          const message = nested.message ?? nested.detail;
          if (typeof message === "string") {
            detail = message.slice(0, 300);
          }
          if (typeof nested.code === "string") {
            errorCode = "attachment_error";
            serverCode = nested.code;
          }
          if (typeof nested.filename === "string") {
            filename = nested.filename;
          }
        }
      } catch {
        detail = rawBody.slice(0, 300);
      }
    }
  } catch {
    // The status code still provides a useful error if the body cannot be read.
  }
  const suffix = detail ? `: ${structuredErrorMessage(detail, filename)}` : ".";
  return new AgentServerError(
    errorCode,
    `${prefix} (${response.status})${suffix}`,
    { filename, serverCode, status: response.status }
  );
}

function structuredErrorMessage(message: string, filename?: string) {
  if (!filename || message.includes(filename)) {
    return message;
  }
  return `${filename}: ${message}`;
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
