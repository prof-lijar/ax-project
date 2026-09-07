import { afterEach, describe, expect, it, vi } from "vitest";

import {
  DEFAULT_RAG_MAX_CHUNK_TOKENS,
  DEFAULT_RAG_TOP_K,
  RagClientError,
  ragClient,
  resolveRagServerBaseUrl
} from "./ragClient";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ragClient.embedFile", () => {
  it("uploads one file under the multipart field named file", async () => {
    const payload = embedPayload();
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(payload));
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["한국어 문서"], "notes.md", {
      type: "text/markdown"
    });

    await expect(ragClient.embedFile(file)).resolves.toEqual(payload);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8765/rag/v1/embed");
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("file")).toEqual(file);
    expect((init.body as FormData).get("max_chunk_tokens")).toBe(
      String(DEFAULT_RAG_MAX_CHUNK_TOKENS)
    );
    expect(new Headers(init.headers).has("Content-Type")).toBe(false);
  });

  it.each([100, 350, 1000])(
    "passes the valid maximum chunk size %s",
    async (maxChunkTokens) => {
      const fetchMock = vi
        .fn()
        .mockResolvedValue(jsonResponse(embedPayload(maxChunkTokens)));
      vi.stubGlobal("fetch", fetchMock);

      await ragClient.embedFile(
        new File(["문서"], "document.txt"),
        maxChunkTokens
      );

      const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect((init.body as FormData).get("max_chunk_tokens")).toBe(
        String(maxChunkTokens)
      );
    }
  );

  it.each([99, 1001, 100.5, Number.NaN])(
    "rejects invalid max_chunk_tokens %s",
    async (maxChunkTokens) => {
      await expect(
        ragClient.embedFile(
          new File(["문서"], "document.txt"),
          maxChunkTokens
        )
      ).rejects.toMatchObject({
        message: "max_chunk_tokens must be a whole number from 100 to 1000."
      });
    }
  );

  it("surfaces a FastAPI detail string", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ detail: "PDF OCR service is unavailable." }, 503)
      )
    );

    await expect(
      ragClient.embedFile(new File(["pdf"], "scan.pdf"))
    ).rejects.toMatchObject({
      status: 503,
      message: "PDF OCR service is unavailable."
    });
  });
});

describe("ragClient.embedText", () => {
  it("posts preserved text, a trimmed optional title, and max_chunk_tokens as JSON", async () => {
    const payload = embedPayload(350, "text");
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(payload));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      ragClient.embedText("첫 줄\n\n둘째 문단", "  직접 입력 제목  ", 350)
    ).resolves.toEqual(payload);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8765/rag/v1/embed/text");
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("Content-Type")).toBe(
      "application/json"
    );
    expect(JSON.parse(String(init.body))).toEqual({
      text: "첫 줄\n\n둘째 문단",
      title: "직접 입력 제목",
      max_chunk_tokens: 350
    });
  });

  it("omits a blank title and rejects blank text before fetch", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(embedPayload(500, "text"))
    );
    vi.stubGlobal("fetch", fetchMock);

    await ragClient.embedText("본문", "   ");
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({
      text: "본문",
      max_chunk_tokens: 500
    });

    await expect(ragClient.embedText(" \n\t ")).rejects.toMatchObject({
      message: "Enter non-empty text to embed."
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("ragClient.search", () => {
  it("uses GET, safely encodes the query, and defaults top_k to 5", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(searchPayload([])));
    vi.stubGlobal("fetch", fetchMock);

    await ragClient.search("서울 수도 & 행정?");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const parsed = new URL(url);
    expect(parsed.origin).toBe("http://127.0.0.1:8765");
    expect(parsed.pathname).toBe("/rag/v1/search");
    expect(parsed.searchParams.get("query")).toBe("서울 수도 & 행정?");
    expect(parsed.searchParams.get("top_k")).toBe(String(DEFAULT_RAG_TOP_K));
    expect(init.method).toBe("GET");
    expect(init.body).toBeUndefined();
  });

  it("passes an explicit top_k", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(searchPayload([])));
    vi.stubGlobal("fetch", fetchMock);

    await ragClient.search("한라산", 3);

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(new URL(url, "http://nexgent.test").searchParams.get("top_k")).toBe(
      "3"
    );
  });

  it("normalizes the configured direct RAG server base URL", () => {
    expect(
      resolveRagServerBaseUrl("  http://192.168.0.18:8765/  ")
    ).toBe("http://192.168.0.18:8765");
  });

  it.each(["", "   ", "\n\t"])("rejects an invalid query %j", async (query) => {
    await expect(ragClient.search(query)).rejects.toEqual(
      expect.objectContaining<Partial<RagClientError>>({
        message: "Enter a non-empty search query."
      })
    );
  });

  it.each([0, 21, 1.5, Number.NaN])("rejects invalid top_k %s", async (topK) => {
    await expect(ragClient.search("query", topK)).rejects.toEqual(
      expect.objectContaining<Partial<RagClientError>>({
        message: "top_k must be a whole number from 1 to 20."
      })
    );
  });

  it("parses results without changing their server order", async () => {
    const results = [
      searchResult(8, 0.81, "첫 번째", {
        document_id: 21,
        source_type: "file",
        source_name: "project.md",
        chunk_index: 2,
        source_start_character: 420,
        source_end_character: 600,
        token_count: 130
      }),
      searchResult(3, 0.77, "두 번째")
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(searchPayload(results)))
    );

    await expect(ragClient.search("순서", 2)).resolves.toEqual(
      searchPayload(results)
    );
  });

  it("joins FastAPI validation messages", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          { detail: [{ msg: "Input should be less than or equal to 20" }] },
          422
        )
      )
    );

    await expect(ragClient.search("query")).rejects.toMatchObject({
      status: 422,
      message: "Input should be less than or equal to 20"
    });
  });

  it("rejects malformed successful responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(searchPayload([{ id: "bad" }] as never))
      )
    );

    await expect(ragClient.search("query")).rejects.toMatchObject({
      message: "The RAG server returned an invalid search response."
    });
  });
});

describe("ragClient RAG data administration", () => {
  it("loads lightweight RAG data counts", async () => {
    const payload = dataStatsPayload();
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(payload));
    vi.stubGlobal("fetch", fetchMock);

    await expect(ragClient.getDataStats()).resolves.toEqual(payload);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8765/rag/v1/data/stats");
    expect(init.method).toBe("GET");
    expect(init.body).toBeUndefined();
  });

  it("requires exact DELETE and sends only the confirmation contract", async () => {
    const payload = {
      deleted_embedding_rows: 80,
      deleted_document_rows: 2
    };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(payload));
    vi.stubGlobal("fetch", fetchMock);

    await expect(ragClient.deleteAllData("DELETE")).resolves.toEqual(payload);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:8765/rag/v1/data");
    expect(init.method).toBe("DELETE");
    expect(new Headers(init.headers).get("Content-Type")).toBe(
      "application/json"
    );
    expect(JSON.parse(String(init.body))).toEqual({ confirmation: "DELETE" });
  });

  it.each(["", "delete", "Delete", " DELETE", "DELETE "])(
    "rejects inexact destructive confirmation %j before fetch",
    async (confirmation) => {
      const fetchMock = vi.fn();
      vi.stubGlobal("fetch", fetchMock);

      await expect(ragClient.deleteAllData(confirmation)).rejects.toMatchObject({
        message: 'confirmation must be exactly "DELETE".'
      });
      expect(fetchMock).not.toHaveBeenCalled();
    }
  );

  it("rejects malformed stats and delete responses", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({ ...dataStatsPayload(), embedding_rows: 79 })
      )
      .mockResolvedValueOnce(jsonResponse({ deleted_embedding_rows: "80" }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(ragClient.getDataStats()).rejects.toMatchObject({
      message: "The RAG server returned invalid data statistics."
    });
    await expect(ragClient.deleteAllData("DELETE")).rejects.toMatchObject({
      message: "The RAG server returned an invalid delete response."
    });
  });

  it("surfaces a sanitized backend deletion error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ detail: "Unable to empty the RAG database." }, 500)
      )
    );

    await expect(ragClient.deleteAllData("DELETE")).rejects.toMatchObject({
      status: 500,
      message: "Unable to empty the RAG database."
    });
  });
});

function embedPayload(
  maxChunkTokens = 500,
  sourceType: "file" | "text" = "file"
) {
  return {
    ok: true as const,
    source: {
      document_id: 21,
      source_type: sourceType,
      source_name: sourceType === "file" ? "notes.md" : "직접 입력 제목",
      filename: sourceType === "file" ? "notes.md" : null,
      size_bytes: 1200,
      character_count: 600,
      token_count: 420
    },
    chunking: {
      max_chunk_tokens: maxChunkTokens,
      chunk_count: 2,
      chunk_token_counts: [350, 130],
      preview_truncated: false,
      chunks: [
        {
          index: 1,
          token_count: 350,
          character_count: 500,
          source_start_character: 0,
          source_end_character: 500,
          overlap_with_previous_tokens: 0,
          context: "첫 번째 청크"
        },
        {
          index: 2,
          token_count: 130,
          character_count: 180,
          source_start_character: 420,
          source_end_character: 600,
          overlap_with_previous_tokens: 60,
          context: "두 번째 청크"
        }
      ]
    },
    timing_ms: { chunking: 1.25, embedding: 20.5, total: 25.75 }
  };
}

function searchResult(
  id: number,
  similarity: number,
  context: string,
  provenance: Partial<{
    document_id: number | null;
    source_type: "file" | "text" | null;
    source_name: string | null;
    chunk_index: number | null;
    source_start_character: number | null;
    source_end_character: number | null;
    token_count: number | null;
  }> = {}
) {
  return {
    id,
    similarity,
    context,
    document_id: null,
    source_type: null,
    source_name: null,
    chunk_index: null,
    source_start_character: null,
    source_end_character: null,
    token_count: null,
    ...provenance
  };
}

function searchPayload(results: unknown[]) {
  return {
    results,
    timing_ms: {
      query_embedding: 8.25,
      database_search: 1.5,
      total: 9.75
    }
  };
}

function dataStatsPayload() {
  return {
    embedding_rows: 80,
    document_rows: 2,
    legacy_embedding_rows: 71,
    provenance_embedding_rows: 9
  };
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}
