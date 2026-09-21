import { authenticatedFetch } from "./authenticatedFetch";
export const DEFAULT_RAG_TOP_K = 5;
export const MIN_RAG_TOP_K = 1;
export const MAX_RAG_TOP_K = 20;
export const DEFAULT_RAG_MAX_CHUNK_TOKENS = 500;
export const MIN_RAG_MAX_CHUNK_TOKENS = 100;
export const MAX_RAG_MAX_CHUNK_TOKENS = 1000;

export const RAG_SERVER_BASE_URL = "/rag-api";

export interface RagEmbedResponse {
  ok: true;
  source: RagEmbedSourceMetrics;
  chunking: RagChunkingMetrics;
  timing_ms: RagEmbedTiming;
}

export interface RagEmbedSourceMetrics {
  document_id: number;
  source_type: "file" | "text";
  source_name: string;
  filename: string | null;
  size_bytes: number;
  character_count: number;
  token_count: number;
}

export interface RagChunkPreview {
  index: number;
  token_count: number;
  character_count: number;
  source_start_character: number;
  source_end_character: number;
  overlap_with_previous_tokens: number;
  context: string;
}

export interface RagChunkingMetrics {
  max_chunk_tokens: number;
  chunk_count: number;
  chunk_token_counts: number[];
  preview_truncated: boolean;
  chunks: RagChunkPreview[];
}

export interface RagEmbedTiming {
  chunking: number;
  embedding: number;
  total: number;
}

export interface RagSearchResult {
  id: number;
  similarity: number;
  context: string;
  document_id: number | null;
  source_type: "file" | "text" | null;
  source_name: string | null;
  chunk_index: number | null;
  source_start_character: number | null;
  source_end_character: number | null;
  token_count: number | null;
}

export interface RagSearchResponse {
  results: RagSearchResult[];
  timing_ms: RagSearchTiming;
}

export interface RagSearchTiming {
  query_embedding: number;
  database_search: number;
  total: number;
}

export interface RagDataStats {
  embedding_rows: number;
  document_rows: number;
  legacy_embedding_rows: number;
  provenance_embedding_rows: number;
}

export interface RagDeleteDataResponse {
  deleted_embedding_rows: number;
  deleted_document_rows: number;
}

export interface RagFileEmbedInput {
  mode: "file";
  file: File;
  maxChunkTokens?: number;
}

export interface RagTextEmbedInput {
  mode: "text";
  text: string;
  title?: string;
  maxChunkTokens?: number;
}

export type RagEmbedInput = RagFileEmbedInput | RagTextEmbedInput;

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
    maxChunkTokens = DEFAULT_RAG_MAX_CHUNK_TOKENS,
    { signal }: RequestOptions = {}
  ): Promise<RagEmbedResponse> {
    if (
      !Number.isInteger(maxChunkTokens) ||
      maxChunkTokens < MIN_RAG_MAX_CHUNK_TOKENS ||
      maxChunkTokens > MAX_RAG_MAX_CHUNK_TOKENS
    ) {
      throw new RagClientError(
        "max_chunk_tokens must be a whole number from 100 to 1000."
      );
    }

    const body = new FormData();
    body.append("file", file, file.name);
    body.append("max_chunk_tokens", String(maxChunkTokens));

    const response = await request(
      ragServerUrl("/rag/v1/embed"),
      {
        method: "POST",
        headers: { Accept: "application/json" },
        body,
        signal
      }
    );
    const payload = await readJson(response);
    if (!isEmbedResponse(payload)) {
      throw new RagClientError("The RAG server returned an invalid embed response.");
    }
    return payload;
  },

  async embedText(
    text: string,
    title?: string,
    maxChunkTokens = DEFAULT_RAG_MAX_CHUNK_TOKENS,
    { signal }: RequestOptions = {}
  ): Promise<RagEmbedResponse> {
    if (!text.trim()) {
      throw new RagClientError("Enter non-empty text to embed.");
    }
    validateMaxChunkTokens(maxChunkTokens);

    const normalizedTitle = title?.trim();
    const response = await request(
      ragServerUrl("/rag/v1/embed/text"),
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          text,
          ...(normalizedTitle ? { title: normalizedTitle } : {}),
          max_chunk_tokens: maxChunkTokens
        }),
        signal
      }
    );
    const payload = await readJson(response);
    if (!isEmbedResponse(payload)) {
      throw new RagClientError("The RAG server returned an invalid embed response.");
    }
    return payload;
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
      `${ragServerUrl("/rag/v1/search")}?${parameters.toString()}`,
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
  },

  async getDataStats(
    { signal }: RequestOptions = {}
  ): Promise<RagDataStats> {
    const response = await request(
      ragServerUrl("/rag/v1/data/stats"),
      {
        method: "GET",
        headers: { Accept: "application/json" },
        signal
      }
    );
    const payload = await readJson(response);
    if (!isDataStats(payload)) {
      throw new RagClientError("The RAG server returned invalid data statistics.");
    }
    return payload;
  },

  async deleteAllData(
    confirmation: string,
    { signal }: RequestOptions = {}
  ): Promise<RagDeleteDataResponse> {
    if (confirmation !== "DELETE") {
      throw new RagClientError('confirmation must be exactly "DELETE".');
    }
    const response = await request(
      ragServerUrl("/rag/v1/data"),
      {
        method: "DELETE",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ confirmation }),
        signal
      }
    );
    const payload = await readJson(response);
    if (!isDeleteDataResponse(payload)) {
      throw new RagClientError("The RAG server returned an invalid delete response.");
    }
    return payload;
  }
};

export function resolveRagServerBaseUrl(_configured?: string) {
  return "/rag-api";
}

function ragServerUrl(path: string) {
  return `${RAG_SERVER_BASE_URL}${path}`;
}


async function request(url: string, init: RequestInit) {
  try {
    const response = await authenticatedFetch(url, init);
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
        typeof item.context === "string" &&
        isNullableFiniteNumber(item.document_id) &&
        (item.source_type === null ||
          item.source_type === "file" ||
          item.source_type === "text") &&
        (item.source_name === null || typeof item.source_name === "string") &&
        isNullableFiniteNumber(item.chunk_index) &&
        isNullableFiniteNumber(item.source_start_character) &&
        isNullableFiniteNumber(item.source_end_character) &&
        isNullableFiniteNumber(item.token_count)
    ) &&
    isSearchTiming(value.timing_ms)
  );
}

function isEmbedResponse(value: unknown): value is RagEmbedResponse {
  if (
    !isRecord(value) ||
    value.ok !== true ||
    !isRecord(value.source) ||
    !isRecord(value.chunking) ||
    !isEmbedTiming(value.timing_ms)
  ) {
    return false;
  }

  const source = value.source;
  const chunking = value.chunking;
  return (
    isFiniteNumber(source.document_id) &&
    (source.source_type === "file" || source.source_type === "text") &&
    typeof source.source_name === "string" &&
    (source.filename === null || typeof source.filename === "string") &&
    isFiniteNumber(source.size_bytes) &&
    isFiniteNumber(source.character_count) &&
    isFiniteNumber(source.token_count) &&
    isFiniteNumber(chunking.max_chunk_tokens) &&
    isFiniteNumber(chunking.chunk_count) &&
    Array.isArray(chunking.chunk_token_counts) &&
    chunking.chunk_token_counts.every(isFiniteNumber) &&
    typeof chunking.preview_truncated === "boolean" &&
    Array.isArray(chunking.chunks) &&
    chunking.chunks.every(isChunkPreview)
  );
}

function isDataStats(value: unknown): value is RagDataStats {
  return (
    isRecord(value) &&
    isNonNegativeInteger(value.embedding_rows) &&
    isNonNegativeInteger(value.document_rows) &&
    isNonNegativeInteger(value.legacy_embedding_rows) &&
    isNonNegativeInteger(value.provenance_embedding_rows) &&
    value.legacy_embedding_rows + value.provenance_embedding_rows ===
      value.embedding_rows
  );
}

function isDeleteDataResponse(value: unknown): value is RagDeleteDataResponse {
  return (
    isRecord(value) &&
    isNonNegativeInteger(value.deleted_embedding_rows) &&
    isNonNegativeInteger(value.deleted_document_rows)
  );
}

function validateMaxChunkTokens(maxChunkTokens: number) {
  if (
    !Number.isInteger(maxChunkTokens) ||
    maxChunkTokens < MIN_RAG_MAX_CHUNK_TOKENS ||
    maxChunkTokens > MAX_RAG_MAX_CHUNK_TOKENS
  ) {
    throw new RagClientError(
      "max_chunk_tokens must be a whole number from 100 to 1000."
    );
  }
}

function isNullableFiniteNumber(value: unknown): value is number | null {
  return value === null || isFiniteNumber(value);
}

function isChunkPreview(value: unknown): value is RagChunkPreview {
  return (
    isRecord(value) &&
    isFiniteNumber(value.index) &&
    isFiniteNumber(value.token_count) &&
    isFiniteNumber(value.character_count) &&
    isFiniteNumber(value.source_start_character) &&
    isFiniteNumber(value.source_end_character) &&
    isFiniteNumber(value.overlap_with_previous_tokens) &&
    typeof value.context === "string"
  );
}

function isEmbedTiming(value: unknown): value is RagEmbedTiming {
  return (
    isRecord(value) &&
    isFiniteNumber(value.chunking) &&
    isFiniteNumber(value.embedding) &&
    isFiniteNumber(value.total)
  );
}

function isSearchTiming(value: unknown): value is RagSearchTiming {
  return (
    isRecord(value) &&
    isFiniteNumber(value.query_embedding) &&
    isFiniteNumber(value.database_search) &&
    isFiniteNumber(value.total)
  );
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isNonNegativeInteger(value: unknown): value is number {
  return isFiniteNumber(value) && Number.isInteger(value) && value >= 0;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
