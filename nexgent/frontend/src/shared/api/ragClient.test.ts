import { afterEach, describe, expect, it, vi } from "vitest";

import {
  DEFAULT_RAG_TOP_K,
  RagClientError,
  ragClient
} from "./ragClient";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ragClient.embedFile", () => {
  it("uploads one file under the multipart field named file", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["한국어 문서"], "notes.md", {
      type: "text/markdown"
    });

    await expect(ragClient.embedFile(file)).resolves.toEqual({ ok: true });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/rag-server/rag/v1/embed");
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("file")).toEqual(file);
    expect(new Headers(init.headers).has("Content-Type")).toBe(false);
  });

  it("surfaces a FastAPI detail string", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ detail: "Scanned PDFs are not supported." }, 400)
      )
    );

    await expect(
      ragClient.embedFile(new File(["pdf"], "scan.pdf"))
    ).rejects.toMatchObject({
      status: 400,
      message: "Scanned PDFs are not supported."
    });
  });
});

describe("ragClient.search", () => {
  it("uses GET, safely encodes the query, and defaults top_k to 5", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ results: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await ragClient.search("서울 수도 & 행정?");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const parsed = new URL(url, "http://nexgent.test");
    expect(parsed.pathname).toBe("/rag-server/rag/v1/search");
    expect(parsed.searchParams.get("query")).toBe("서울 수도 & 행정?");
    expect(parsed.searchParams.get("top_k")).toBe(String(DEFAULT_RAG_TOP_K));
    expect(init.method).toBe("GET");
    expect(init.body).toBeUndefined();
  });

  it("passes an explicit top_k", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ results: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await ragClient.search("한라산", 3);

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(new URL(url, "http://nexgent.test").searchParams.get("top_k")).toBe(
      "3"
    );
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
      { id: 8, similarity: 0.81, context: "첫 번째" },
      { id: 3, similarity: 0.77, context: "두 번째" }
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ results }))
    );

    await expect(ragClient.search("순서", 2)).resolves.toEqual({ results });
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
      vi.fn().mockResolvedValue(jsonResponse({ results: [{ id: "bad" }] }))
    );

    await expect(ragClient.search("query")).rejects.toMatchObject({
      message: "The RAG server returned an invalid search response."
    });
  });
});

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}
