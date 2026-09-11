import {
  Children,
  isValidElement,
  type ReactElement,
  type ReactNode
} from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import {
  EmbedResult,
  EmbeddingPanel,
  isDeleteConfirmationValid,
  isSupportedRagFile,
  parseMaxChunkTokens,
  parseTopK,
  RagDataPanel,
  SearchPanel
} from "./RagPage";

const noop = () => undefined;

describe("RagPage embedding UI", () => {
  it("renders the initial file-only embedding state", () => {
    const markup = embeddingMarkup();

    expect(markup).toContain("Add to your knowledge");
    expect(markup).toContain("File upload");
    expect(markup).toContain("Paste text");
    expect(markup).toContain("Supported: UTF-8 TXT, UTF-8 MD, DOCX, and PDF.");
    expect(markup).toContain("Scanned PDF pages use automatic OCR.");
    expect(markup).toContain("Images embedded in DOCX are not OCRed.");
    expect(markup).toContain('accept=".txt,.md,.docx,.pdf"');
    expect(markup).toContain("Choose a source file");
    expect(markup).toContain("Maximum tokens per chunk");
    expect(markup).toContain('value="500"');
    expect(markup).toContain('min="100"');
    expect(markup).toContain('max="1000"');
    expect(markup).toContain("Natural boundaries may produce shorter chunks.");
    expect(markup).toContain('type="submit" disabled=""');
    expect(markup).not.toContain("Source added to knowledge");
  });

  it("renders direct text, optional title, and blank-source validation", () => {
    const blank = embeddingMarkup({ inputMode: "text" });
    const populated = embeddingMarkup({
      inputMode: "text",
      directTextTitle: "직접 입력 제목",
      directText: "첫 줄\n\n둘째 문단"
    });

    expect(blank).toContain("Display title (optional)");
    expect(blank).toContain("Source text");
    expect(blank).toContain("Type or paste source text");
    expect(blank).toContain('type="submit" disabled=""');
    expect(populated).toContain('value="직접 입력 제목"');
    expect(populated).toContain("첫 줄\n\n둘째 문단");
    expect(populated).not.toContain('type="submit" disabled=""');
  });

  it("shows the selected filename and accepts only supported extensions", () => {
    const file = new File(["# 한국어\n\n본문"], "자료.MD");
    const markup = embeddingMarkup({ selectedFile: file });

    expect(markup).toContain("자료.MD");
    expect(isSupportedRagFile(file)).toBe(true);
    expect(isSupportedRagFile({ name: "notes.txt" })).toBe(true);
    expect(isSupportedRagFile({ name: "report.pdf" })).toBe(true);
    expect(isSupportedRagFile({ name: "document.docx" })).toBe(true);
    expect(isSupportedRagFile({ name: "document.DOCX" })).toBe(true);
    expect(isSupportedRagFile({ name: "legacy.doc" })).toBe(false);
    expect(isSupportedRagFile({ name: "document.docx.exe" })).toBe(false);
    expect(isSupportedRagFile({ name: "scan.png" })).toBe(false);
    expect(isSupportedRagFile({ name: "report.pdf.exe" })).toBe(false);
  });

  it("renders pending, success, client-validation, and API-error states", () => {
    expect(
      embeddingMarkup({
        selectedFile: new File(["text"], "notes.txt"),
        isPending: true
      })
    ).toContain("Adding to knowledge…");
    expect(embeddingMarkup({ result: embedResponse() })).toContain(
      "Source added to knowledge"
    );
    expect(
      embeddingMarkup({ fileError: "Choose a TXT, MD, DOCX, or PDF file." })
    ).toContain('role="alert"');
    expect(
      embeddingMarkup({ apiError: new Error("PDF has no extractable text.") })
    ).toContain("PDF has no extractable text.");
  });

  it("validates whole-number maximum chunk sizes from 100 to 1000", () => {
    expect(parseMaxChunkTokens("100")).toBe(100);
    expect(parseMaxChunkTokens("500")).toBe(500);
    expect(parseMaxChunkTokens("1000")).toBe(1000);
    expect(parseMaxChunkTokens("99")).toBeNull();
    expect(parseMaxChunkTokens("1001")).toBeNull();
    expect(parseMaxChunkTokens("350.5")).toBeNull();
    expect(parseMaxChunkTokens("")).toBeNull();

    const invalid = embeddingMarkup({
      maxChunkTokensInput: "99",
      maxChunkTokensIsValid: false,
      selectedFile: new File(["문서"], "document.txt")
    });
    expect(invalid).toContain("Enter a whole number from 100 to 1000.");
    expect(invalid).toContain('type="submit" disabled=""');
  });

  it("renders compact embedding metrics, chunk spans, overlap, and truncation", () => {
    const markup = renderToStaticMarkup(
      <EmbedResult result={embedResponse(true)} />
    );

    expect(markup).toContain("Processing summary");
    expect(markup).toContain("Source");
    expect(markup).toContain("project.md");
    expect(markup).toContain("1,024 bytes");
    expect(markup).toContain("Document tokens");
    expect(markup).toContain("420");
    expect(markup).toContain("Chunking");
    expect(markup).toContain("1.250 ms");
    expect(markup).toContain("Embedding");
    expect(markup).toContain("20.500 ms");
    expect(markup).toContain("Chunk preview");
    expect(markup).toContain("Showing the first 10 of 12 chunks.");
    expect(markup).toContain("Chunk 1");
    expect(markup).toContain("350 tokens");
    expect(markup).toContain("500 characters");
    expect(markup).toContain("Source characters [0, 500)");
    expect(markup).toContain("Overlap with previous: 0 tokens");
    expect(markup).toContain("첫 줄\n둘째 줄");
  });
});

describe("RAG data administration UI", () => {
  it("renders current document, embedding, legacy, and provenance counts", () => {
    const markup = renderToStaticMarkup(ragDataPanel());

    expect(markup).toContain("RAG data");
    expect(markup).toContain("Documents");
    expect(markup).toContain("Embedding chunks");
    expect(markup).toContain("Legacy chunks");
    expect(markup).toContain("Provenance chunks");
    expect(markup).toContain("80");
    expect(markup).toContain("71");
    expect(markup).toContain("Empty database");
  });

  it("opens an explicit confirmation dialog with current counts", () => {
    const closed = renderToStaticMarkup(
      ragDataPanel({ isConfirmationOpen: false })
    );
    const open = renderToStaticMarkup(
      ragDataPanel({ isConfirmationOpen: true })
    );

    expect(closed).not.toContain("Delete all RAG data?");
    expect(open).toContain('role="dialog"');
    expect(open).toContain("Delete all RAG data?");
    expect(open).toContain(
      "The database structure itself will remain unchanged."
    );
    expect(open).toContain("Documents: 2 · Embedding chunks: 80");
    expect(open).toContain("Type <strong>DELETE</strong> to confirm");
  });

  it("enables final deletion only for exact DELETE", () => {
    expect(isDeleteConfirmationValid("DELETE")).toBe(true);
    for (const value of ["", "delete", "Delete", " DELETE", "DELETE "]) {
      expect(isDeleteConfirmationValid(value)).toBe(false);
      const button = findElement(
        ragDataPanel({ isConfirmationOpen: true, confirmation: value }),
        (element) => elementText(element.props.children) === "Delete all data"
      );
      expect(button.props.disabled).toBe(true);
    }

    const exactButton = findElement(
      ragDataPanel({ isConfirmationOpen: true, confirmation: "DELETE" }),
      (element) => elementText(element.props.children) === "Delete all data"
    );
    expect(exactButton.props.disabled).toBe(false);
  });

  it("keeps cancel and destructive callbacks separate", () => {
    const onOpenConfirmation = vi.fn();
    const onCancel = vi.fn();
    const onDelete = vi.fn();
    const panel = ragDataPanel({
      isConfirmationOpen: true,
      confirmation: "DELETE",
      onOpenConfirmation,
      onCancel,
      onDelete
    });
    const openButton = findElement(
      panel,
      (element) => elementText(element.props.children) === "Empty database"
    );
    const cancelButton = findElement(
      panel,
      (element) => elementText(element.props.children) === "Cancel"
    );
    const deleteButton = findElement(
      panel,
      (element) => elementText(element.props.children) === "Delete all data"
    );

    (openButton.props.onClick as () => void)();
    expect(onOpenConfirmation).toHaveBeenCalledOnce();
    expect(onDelete).not.toHaveBeenCalled();

    (cancelButton.props.onClick as () => void)();
    expect(onCancel).toHaveBeenCalledOnce();
    expect(onDelete).not.toHaveBeenCalled();

    (deleteButton.props.onClick as () => void)();
    expect(onDelete).toHaveBeenCalledOnce();
  });

  it("renders refreshed empty counts, success, and backend errors", () => {
    const success = renderToStaticMarkup(
      ragDataPanel({
        stats: {
          embedding_rows: 0,
          document_rows: 0,
          legacy_embedding_rows: 0,
          provenance_embedding_rows: 0
        },
        deleteResult: {
          deleted_embedding_rows: 80,
          deleted_document_rows: 2
        }
      })
    );
    const failure = renderToStaticMarkup(
      ragDataPanel({
        deleteError: new Error("Unable to empty the RAG database.")
      })
    );

    expect(success).toContain("RAG database emptied successfully.");
    expect(success).toContain("Removed 80 embedding chunks and 2 documents.");
    expect(failure).toContain('role="alert"');
    expect(failure).toContain("Unable to empty the RAG database.");
  });
});

describe("RagPage search workspace", () => {
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
    expect(searchMarkup({ query: "질문", isPending: true })).toContain(
      "Searching…"
    );
    expect(
      searchMarkup({ apiError: new Error("RAG server unavailable") })
    ).toContain("RAG server unavailable");
  });

  it("preserves server rank order, similarity semantics, and context line breaks", () => {
    const markup = searchMarkup({
      query: "검색",
      results: [
        searchResult(9, 0.8, "첫 줄\n둘째 줄", {
          document_id: 44,
          source_type: "file",
          source_name: "project.md",
          chunk_index: 3,
          source_start_character: 420,
          source_end_character: 600,
          token_count: 130
        }),
        searchResult(2, 0.7, "다음 결과")
      ],
      timing: {
        query_embedding: 8.25,
        database_search: 1.5,
        total: 9.75
      }
    });

    expect(markup.indexOf(">01<")).toBeLessThan(markup.indexOf(">02<"));
    expect(markup.indexOf("첫 줄\n둘째 줄")).toBeLessThan(
      markup.indexOf("다음 결과")
    );
    expect(markup).toContain("<dt>Cosine similarity</dt><dd>0.8</dd>");
    expect(markup).toContain("project.md");
    expect(markup).toContain("File · Passage 3");
    expect(markup).toContain("<dt>Passage</dt><dd>3</dd>");
    expect(markup).toContain("Source details unavailable");
    expect(markup).not.toContain("confidence");
    expect(markup).not.toContain("accuracy");
    expect(markup).toContain("Server processing time");
    expect(markup).toContain("Query embedding: 8.250 ms");
    expect(markup).toContain("DB search: 1.500 ms");
    expect(markup).toContain("Total: 9.750 ms");
  });
});

function embeddingMarkup(
  overrides: Partial<Parameters<typeof EmbeddingPanel>[0]> = {}
) {
  return renderToStaticMarkup(
    <EmbeddingPanel
      inputMode="file"
      selectedFile={null}
      fileError={null}
      directText=""
      directTextTitle=""
      maxChunkTokensInput="500"
      maxChunkTokensIsValid
      isPending={false}
      result={null}
      apiError={null}
      onInputModeChange={noop}
      onChooseFile={noop}
      onFileChange={noop}
      onDirectTextChange={noop}
      onDirectTextTitleChange={noop}
      onMaxChunkTokensChange={noop}
      onSubmit={vi.fn()}
      {...overrides}
    />
  );
}

function searchMarkup(
  overrides: Partial<Parameters<typeof SearchPanel>[0]> = {}
) {
  return renderToStaticMarkup(
    <SearchPanel
      query=""
      topKInput="5"
      topKIsValid
      isPending={false}
      apiError={null}
      results={null}
      timing={null}
      onQueryChange={noop}
      onTopKChange={noop}
      onSubmit={vi.fn()}
      {...overrides}
    />
  );
}

function ragDataPanel(
  overrides: Partial<Parameters<typeof RagDataPanel>[0]> = {}
) {
  return RagDataPanel({
    stats: {
      embedding_rows: 80,
      document_rows: 2,
      legacy_embedding_rows: 71,
      provenance_embedding_rows: 9
    },
    statsPending: false,
    statsError: null,
    isConfirmationOpen: false,
    confirmation: "",
    deletePending: false,
    deleteResult: null,
    deleteError: null,
    onOpenConfirmation: vi.fn(),
    onConfirmationChange: vi.fn(),
    onCancel: vi.fn(),
    onDelete: vi.fn(),
    ...overrides
  });
}

function findElement(
  node: ReactNode,
  predicate: (element: ReactElement<Record<string, unknown>>) => boolean
): ReactElement<Record<string, unknown>> {
  const match = findElementOrNull(node, predicate);
  if (!match) {
    throw new Error("Expected React element was not found");
  }
  return match;
}

function findElementOrNull(
  node: ReactNode,
  predicate: (element: ReactElement<Record<string, unknown>>) => boolean
): ReactElement<Record<string, unknown>> | null {
  for (const child of Children.toArray(node)) {
    if (!isValidElement<Record<string, unknown>>(child)) {
      continue;
    }
    if (predicate(child)) {
      return child;
    }
    const nested = findElementOrNull(
      child.props.children as ReactNode,
      predicate
    );
    if (nested) {
      return nested;
    }
  }
  return null;
}

function elementText(node: unknown): string {
  return Children.toArray(node as ReactNode)
    .map((child) =>
      typeof child === "string" || typeof child === "number"
        ? String(child)
        : isValidElement<Record<string, unknown>>(child)
          ? elementText(child.props.children)
          : ""
    )
    .join("");
}

function embedResponse(previewTruncated = false) {
  return {
    ok: true as const,
    source: {
      document_id: 44,
      source_type: "file" as const,
      source_name: "project.md",
      filename: "project.md",
      size_bytes: 1024,
      character_count: 600,
      token_count: 420
    },
    chunking: {
      max_chunk_tokens: 500,
      chunk_count: previewTruncated ? 12 : 2,
      chunk_token_counts: previewTruncated
        ? [350, 130, 300, 300, 300, 300, 300, 300, 300, 300, 300, 120]
        : [350, 130],
      preview_truncated: previewTruncated,
      chunks: [
        {
          index: 1,
          token_count: 350,
          character_count: 500,
          source_start_character: 0,
          source_end_character: 500,
          overlap_with_previous_tokens: 0,
          context: "첫 줄\n둘째 줄"
        },
        {
          index: 2,
          token_count: 130,
          character_count: 180,
          source_start_character: 420,
          source_end_character: 600,
          overlap_with_previous_tokens: 60,
          context: "둘째 청크"
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

describe("Knowledge workflow refinements", () => {
  it("keeps indexing configuration and processing metrics behind disclosure controls", () => {
    const markup = embeddingMarkup({ result: embedResponse() });
    expect(markup).toContain("<summary>Indexing options</summary>");
    expect(markup).toContain("<summary>Processing details</summary>");
    expect(markup).toContain("searchable passages added");
    expect(markup).not.toContain("<details open");
  });
  it("does not report success when the current source has an error", () => {
    const markup = embeddingMarkup({
      result: embedResponse(),
      fileError: "Unsupported file"
    });
    expect(markup).not.toContain("Source added to knowledge");
    expect(markup).not.toContain("Processing summary");
    expect(markup).toContain("Unsupported file");
  });
  it("keeps the displayed results associated with the submitted query", () => {
    const markup = searchMarkup({
      query: "new draft",
      searchedQuery: "previous query",
      results: [searchResult(1, 0.6, "a passage")]
    });
    expect(markup).toContain("previous query");
    expect(markup).toContain("1 matching passage");
    expect(markup).toContain("<summary>Source details</summary>");
  });
  it("prevents deletion while another knowledge operation is pending", () => {
    const panel = ragDataPanel({
      operationsPending: true,
      isConfirmationOpen: true,
      confirmation: "DELETE"
    });
    const open = findElement(
      panel,
      (element) => elementText(element.props.children) === "Empty database"
    );
    const remove = findElement(
      panel,
      (element) => elementText(element.props.children) === "Delete all data"
    );
    expect(open.props.disabled).toBe(true);
    expect(remove.props.disabled).toBe(true);
  });
});
