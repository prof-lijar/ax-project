import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import {
  EmbeddingPanel,
  isSupportedRagFile,
  parseTopK,
  RagTabs,
  SearchPanel
} from "./RagPage";

const noop = () => undefined;

describe("RagPage embedding UI", () => {
  it("renders the initial file-only embedding state", () => {
    const markup = embeddingMarkup();

    expect(markup).toContain("Embed a source file");
    expect(markup).toContain("Supported: UTF-8 TXT, UTF-8 MD, and text-based PDF.");
    expect(markup).toContain('accept=".txt,.md,.pdf"');
    expect(markup).toContain("Choose a source file");
    expect(markup).toContain('type="submit" disabled=""');
    expect(markup).not.toContain("Document embedded successfully");
  });

  it("shows the selected filename and accepts only supported extensions", () => {
    const file = new File(["# 한국어\n\n본문"], "자료.MD");
    const markup = embeddingMarkup({ selectedFile: file });

    expect(markup).toContain("자료.MD");
    expect(isSupportedRagFile(file)).toBe(true);
    expect(isSupportedRagFile({ name: "notes.txt" })).toBe(true);
    expect(isSupportedRagFile({ name: "report.pdf" })).toBe(true);
    expect(isSupportedRagFile({ name: "scan.png" })).toBe(false);
    expect(isSupportedRagFile({ name: "report.pdf.exe" })).toBe(false);
  });

  it("renders pending, success, client-validation, and API-error states", () => {
    expect(
      embeddingMarkup({
        selectedFile: new File(["text"], "notes.txt"),
        isPending: true
      })
    ).toContain("Embedding document…");
    expect(embeddingMarkup({ isSuccess: true })).toContain(
      "Document embedded successfully"
    );
    expect(embeddingMarkup({ fileError: "Choose a TXT, MD, or PDF file." })).toContain(
      'role="alert"'
    );
    expect(embeddingMarkup({ apiError: new Error("PDF has no extractable text.") })).toContain(
      "PDF has no extractable text."
    );
  });
});

describe("RagPage tabs and search UI", () => {
  it("marks Embedding initially and Search when selected", () => {
    const select = vi.fn();
    const embedding = renderToStaticMarkup(
      <RagTabs activeTab="embedding" onSelect={select} />
    );
    const search = renderToStaticMarkup(
      <RagTabs activeTab="search" onSelect={select} />
    );

    expect(embedding).toContain('id="rag-embedding-tab"');
    expect(embedding).toContain('aria-selected="true"');
    expect(search).toContain('id="rag-search-tab"');
    expect(search.indexOf('id="rag-search-tab"')).toBeLessThan(
      search.lastIndexOf('aria-selected="true"')
    );
  });

  it("uses top_k 5 by default and validates whole numbers from 1 to 20", () => {
    const markup = searchMarkup();

    expect(markup).toContain('value="5"');
    expect(markup).toContain('min="1"');
    expect(markup).toContain('max="20"');
    expect(parseTopK("1")).toBe(1);
    expect(parseTopK("20")).toBe(20);
    expect(parseTopK("0")).toBeNull();
    expect(parseTopK("21")).toBeNull();
    expect(parseTopK("1.5")).toBeNull();
    expect(parseTopK("")).toBeNull();
  });

  it("disables blank/invalid searches and renders pending and error states", () => {
    expect(searchMarkup()).toContain('type="submit" disabled=""');
    expect(searchMarkup({ query: "질문", topKIsValid: false })).toContain(
      "Enter a whole number from 1 to 20."
    );
    expect(searchMarkup({ query: "질문", isPending: true })).toContain("Searching…");
    expect(searchMarkup({ apiError: new Error("RAG server unavailable") })).toContain(
      "RAG server unavailable"
    );
  });

  it("preserves server rank order, similarity semantics, and context line breaks", () => {
    const markup = searchMarkup({
      query: "검색",
      results: [
        { id: 9, similarity: 0.8, context: "첫 줄\n둘째 줄" },
        { id: 2, similarity: 0.7, context: "다음 결과" }
      ]
    });

    expect(markup.indexOf("Rank 1")).toBeLessThan(markup.indexOf("Rank 2"));
    expect(markup.indexOf("첫 줄\n둘째 줄")).toBeLessThan(markup.indexOf("다음 결과"));
    expect(markup).toContain("Cosine similarity: 0.8");
    expect(markup).not.toContain("confidence");
    expect(markup).not.toContain("accuracy");
  });
});

function embeddingMarkup(
  overrides: Partial<Parameters<typeof EmbeddingPanel>[0]> = {}
) {
  return renderToStaticMarkup(
    <EmbeddingPanel
      selectedFile={null}
      fileError={null}
      isPending={false}
      isSuccess={false}
      apiError={null}
      onChooseFile={noop}
      onFileChange={noop}
      onSubmit={vi.fn()}
      {...overrides}
    />
  );
}

function searchMarkup(overrides: Partial<Parameters<typeof SearchPanel>[0]> = {}) {
  return renderToStaticMarkup(
    <SearchPanel
      query=""
      topKInput="5"
      topKIsValid
      isPending={false}
      apiError={null}
      results={null}
      onQueryChange={noop}
      onTopKChange={noop}
      onSubmit={vi.fn()}
      {...overrides}
    />
  );
}
