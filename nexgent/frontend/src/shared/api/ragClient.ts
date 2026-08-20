export const RAG_BROWSER_PROXY_PATH = "/rag-server";
export const DEFAULT_RAG_TOP_K = 5;
export const MIN_RAG_TOP_K = 1;
export const MAX_RAG_TOP_K = 20;

export interface RagEmbedResponse {
  ok: true;
}

export interface RagSearchResult {
  id: number;
  similarity: number;
  context: string;
}

export interface RagSearchResponse {
  results: RagSearchResult[];
}

export interface RagSearchInput {
  query: string;
  topK?: number;
}

interface RequestOptions {
  signal?: AbortSignal;
}

export class RagClientError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "RagClientError";
    this.status = status;
  }
}

export const ragClient = {
  async embedFile(
    file: File,
    { signal }: RequestOptions = {}
  ): Promise<RagEmbedResponse> {
    const body = new FormData();
    body.append("file", file, file.name);

    const response = await request(
      `${RAG_BROWSER_PROXY_PATH}/rag/v1/embed`,
      {
        method: "POST",
        headers: { Accept: "application/json" },
        body,
        signal
      }
    );
    const payload = await readJson(response);
    if (!isRecord(payload) || payload.ok !== true) {
      throw new RagClientError("The RAG server returned an invalid embed response.");
    }
    return { ok: true };
  },

  async search(
    query: string,
    topK = DEFAULT_RAG_TOP_K,
    { signal }: RequestOptions = {}
  ): Promise<RagSearchResponse> {
    const normalizedQuery = query.trim();
    if (!normalizedQuery) {
      throw new RagClientError("Enter a non-empty search query.");
    }
    if (!Number.isInteger(topK) || topK < MIN_RAG_TOP_K || topK > MAX_RAG_TOP_K) {
      throw new RagClientError("top_k must be a whole number from 1 to 20.");
    }

    const parameters = new URLSearchParams({
      query: normalizedQuery,
      top_k: String(topK)
    });
    const response = await request(
      `${RAG_BROWSER_PROXY_PATH}/rag/v1/search?${parameters.toString()}`,
      {
        method: "GET",
        headers: { Accept: "application/json" },
        signal
      }
    );
    const payload = await readJson(response);
    if (!isSearchResponse(payload)) {
      throw new RagClientError("The RAG server returned an invalid search response.");
    }
    return payload;
  }
};

async function request(url: string, init: RequestInit) {
  try {
    const response = await fetch(url, init);
    if (!response.ok) {
      throw new RagClientError(await errorMessage(response), response.status);
    }
    return response;
  } catch (error) {
    if (error instanceof RagClientError) {
      throw error;
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new RagClientError("The RAG request was cancelled.");
    }
    throw new RagClientError("Unable to reach the RAG server.");
  }
}

async function errorMessage(response: Response) {
  const fallback = `RAG request failed with HTTP ${response.status}.`;
  const rawBody = (await response.text()).trim();
  if (!rawBody) {
    return fallback;
  }

  try {
    const payload = JSON.parse(rawBody) as unknown;
    if (!isRecord(payload)) {
      return fallback;
    }
    if (typeof payload.detail === "string" && payload.detail.trim()) {
      return payload.detail.trim();
    }
    if (Array.isArray(payload.detail)) {
      const messages = payload.detail
        .map((item) =>
          isRecord(item) && typeof item.msg === "string" ? item.msg.trim() : ""
        )
        .filter(Boolean);
      if (messages.length > 0) {
        return messages.join(" ");
      }
    }
  } catch {
    return rawBody.slice(0, 300) || fallback;
  }
  return fallback;
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return JSON.parse(await response.text()) as unknown;
  } catch {
    throw new RagClientError("The RAG server returned invalid JSON.");
  }
}

function isSearchResponse(value: unknown): value is RagSearchResponse {
  return (
    isRecord(value) &&
    Array.isArray(value.results) &&
    value.results.every(
      (item) =>
        isRecord(item) &&
        typeof item.id === "number" &&
        Number.isFinite(item.id) &&
        typeof item.similarity === "number" &&
        Number.isFinite(item.similarity) &&
        typeof item.context === "string"
    )
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
