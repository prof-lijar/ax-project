import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Database,
  FileText,
  Search,
  TextCursorInput,
  Trash2,
  Upload
} from "lucide-react";
import {
  type FormEvent,
  type RefObject,
  useRef,
  useState
} from "react";

import {
  useRagDataStats,
  useRagDeleteData,
  useRagEmbed,
  useRagSearch
} from "../../shared/api/queries";
import {
  DEFAULT_RAG_MAX_CHUNK_TOKENS,
  DEFAULT_RAG_TOP_K,
  MAX_RAG_MAX_CHUNK_TOKENS,
  MAX_RAG_TOP_K,
  MIN_RAG_MAX_CHUNK_TOKENS,
  MIN_RAG_TOP_K,
  type RagDataStats,
  type RagDeleteDataResponse,
  type RagEmbedResponse,
  type RagSearchTiming,
  type RagSearchResult
} from "../../shared/api/ragClient";
import styles from "./RagPage.module.css";

export type RagTab = "embedding" | "search";
export type RagInputMode = "file" | "text";

export const RAG_FILE_ACCEPT = ".txt,.md,.docx,.pdf";

export function RagPage() {
  const [activeTab, setActiveTab] = useState<RagTab>("embedding");
  const [inputMode, setInputMode] = useState<RagInputMode>("file");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [directText, setDirectText] = useState("");
  const [directTextTitle, setDirectTextTitle] = useState("");
  const [maxChunkTokensInput, setMaxChunkTokensInput] = useState(
    String(DEFAULT_RAG_MAX_CHUNK_TOKENS)
  );
  const [query, setQuery] = useState("");
  const [topKInput, setTopKInput] = useState(String(DEFAULT_RAG_TOP_K));
  const [deleteConfirmationOpen, setDeleteConfirmationOpen] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const embedMutation = useRagEmbed();
  const searchMutation = useRagSearch();
  const dataStatsQuery = useRagDataStats(activeTab === "embedding");
  const deleteDataMutation = useRagDeleteData();
  const maxChunkTokens = parseMaxChunkTokens(maxChunkTokensInput);
  const topK = parseTopK(topKInput);

  function selectFile(file: File | null) {
    embedMutation.reset();
    if (!file) {
      setSelectedFile(null);
      setFileError(null);
      return;
    }
    if (!isSupportedRagFile(file)) {
      setSelectedFile(null);
      setFileError("Choose a TXT, MD, DOCX, or PDF file.");
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      return;
    }
    setSelectedFile(file);
    setFileError(null);
  }

  function submitEmbed(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (maxChunkTokens === null || embedMutation.isPending) {
      return;
    }
    if (inputMode === "file" && selectedFile) {
      embedMutation.mutate({ mode: "file", file: selectedFile, maxChunkTokens });
    }
    if (inputMode === "text" && directText.trim()) {
      embedMutation.mutate({
        mode: "text",
        text: directText,
        title: directTextTitle,
        maxChunkTokens
      });
    }
  }

  function changeInputMode(mode: RagInputMode) {
    embedMutation.reset();
    setFileError(null);
    setInputMode(mode);
  }

  function changeMaxChunkTokens(value: string) {
    embedMutation.reset();
    setMaxChunkTokensInput(value);
  }

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (query.trim() && topK !== null && !searchMutation.isPending) {
      searchMutation.mutate({ query, topK });
    }
  }

  function openDeleteConfirmation() {
    deleteDataMutation.reset();
    setDeleteConfirmation("");
    setDeleteConfirmationOpen(true);
  }

  function cancelDeleteConfirmation() {
    if (!deleteDataMutation.isPending) {
      setDeleteConfirmation("");
      setDeleteConfirmationOpen(false);
    }
  }

  function deleteAllRagData() {
    if (
      !isDeleteConfirmationValid(deleteConfirmation) ||
      deleteDataMutation.isPending
    ) {
      return;
    }
    deleteDataMutation.mutate(deleteConfirmation, {
      onSuccess: () => {
        setDeleteConfirmation("");
        setDeleteConfirmationOpen(false);
        embedMutation.reset();
        searchMutation.reset();
      }
    });
  }

  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <span className={styles.headerIcon} aria-hidden>
          <Database size={22} />
        </span>
        <div>
          <h1>RAG</h1>
          <p>Embed source files and search the indexed context.</p>
        </div>
      </header>

      <RagTabs activeTab={activeTab} onSelect={setActiveTab} />

      <div className={styles.workspace}>
        {activeTab === "embedding" ? (
          <EmbeddingPanel
            inputMode={inputMode}
            selectedFile={selectedFile}
            fileInputRef={fileInputRef}
            fileError={fileError}
            directText={directText}
            directTextTitle={directTextTitle}
            maxChunkTokensInput={maxChunkTokensInput}
            maxChunkTokensIsValid={maxChunkTokens !== null}
            isPending={embedMutation.isPending}
            result={embedMutation.data ?? null}
            apiError={embedMutation.error}
            onInputModeChange={changeInputMode}
            onChooseFile={() => fileInputRef.current?.click()}
            onFileChange={selectFile}
            onDirectTextChange={(value) => {
              embedMutation.reset();
              setDirectText(value);
            }}
            onDirectTextTitleChange={(value) => {
              embedMutation.reset();
              setDirectTextTitle(value);
            }}
            onMaxChunkTokensChange={changeMaxChunkTokens}
            onSubmit={submitEmbed}
          />
        ) : (
          <SearchPanel
            query={query}
            topKInput={topKInput}
            topKIsValid={topK !== null}
            isPending={searchMutation.isPending}
            apiError={searchMutation.error}
            results={searchMutation.data?.results ?? null}
            timing={searchMutation.data?.timing_ms ?? null}
            onQueryChange={setQuery}
            onTopKChange={setTopKInput}
            onSubmit={submitSearch}
          />
        )}
      </div>

      {activeTab === "embedding" && (
        <RagDataPanel
          stats={dataStatsQuery.data ?? null}
          statsPending={dataStatsQuery.isPending}
          statsError={dataStatsQuery.error}
          isConfirmationOpen={deleteConfirmationOpen}
          confirmation={deleteConfirmation}
          deletePending={deleteDataMutation.isPending}
          deleteResult={deleteDataMutation.data ?? null}
          deleteError={deleteDataMutation.error}
          onOpenConfirmation={openDeleteConfirmation}
          onConfirmationChange={setDeleteConfirmation}
          onCancel={cancelDeleteConfirmation}
          onDelete={deleteAllRagData}
        />
      )}
    </section>
  );
}

export function RagDataPanel({
  stats,
  statsPending,
  statsError,
  isConfirmationOpen,
  confirmation,
  deletePending,
  deleteResult,
  deleteError,
  onOpenConfirmation,
  onConfirmationChange,
  onCancel,
  onDelete
}: {
  stats: RagDataStats | null;
  statsPending: boolean;
  statsError: unknown;
  isConfirmationOpen: boolean;
  confirmation: string;
  deletePending: boolean;
  deleteResult: RagDeleteDataResponse | null;
  deleteError: unknown;
  onOpenConfirmation: () => void;
  onConfirmationChange: (value: string) => void;
  onCancel: () => void;
  onDelete: () => void;
}) {
  const statsErrorMessage = errorMessage(statsError);
  const deleteErrorMessage = errorMessage(deleteError);
  const canDelete = isDeleteConfirmationValid(confirmation) && !deletePending;

  return (
    <section className={styles.dataPanel} aria-labelledby="rag-data-heading">
      <div className={styles.dataPanelHeading}>
        <div>
          <h2 id="rag-data-heading">RAG data</h2>
          <p>Administrative controls for indexed documents and chunks.</p>
        </div>
        <button
          className={styles.emptyDataButton}
          type="button"
          onClick={onOpenConfirmation}
          disabled={stats === null || statsPending || deletePending}
        >
          <Trash2 size={16} />
          Empty database
        </button>
      </div>

      {statsPending && stats === null && (
        <p className={styles.dataStatus}>Loading RAG data counts…</p>
      )}
      {statsErrorMessage && (
        <p className={styles.error} role="alert">
          <AlertCircle size={17} />
          {statsErrorMessage}
        </p>
      )}
      {stats && (
        <dl className={styles.dataCounts}>
          <Metric label="Documents" value={formatCount(stats.document_rows)} />
          <Metric
            label="Embedding chunks"
            value={formatCount(stats.embedding_rows)}
          />
          <Metric
            label="Legacy chunks"
            value={formatCount(stats.legacy_embedding_rows)}
          />
          <Metric
            label="Provenance chunks"
            value={formatCount(stats.provenance_embedding_rows)}
          />
        </dl>
      )}

      {deleteResult && !deletePending && !deleteErrorMessage && (
        <p className={styles.success} role="status">
          <CheckCircle2 size={17} />
          RAG database emptied successfully. Removed {formatCount(
            deleteResult.deleted_embedding_rows
          )} embedding chunks and {formatCount(
            deleteResult.deleted_document_rows
          )} documents.
        </p>
      )}
      {deleteErrorMessage && (
        <p className={styles.error} role="alert">
          <AlertCircle size={17} />
          {deleteErrorMessage}
        </p>
      )}

      {isConfirmationOpen && (
        <div className={styles.dialogBackdrop}>
          <section
            className={styles.confirmationDialog}
            role="dialog"
            aria-modal="true"
            aria-labelledby="rag-delete-title"
            aria-describedby="rag-delete-description"
          >
            <span className={styles.warningIcon} aria-hidden>
              <AlertTriangle size={22} />
            </span>
            <h2 id="rag-delete-title">Delete all RAG data?</h2>
            <p id="rag-delete-description">
              This permanently removes all indexed RAG documents and embedding
              chunks. The database structure itself will remain unchanged.
            </p>
            {stats && (
              <p className={styles.confirmationCounts}>
                Documents: {formatCount(stats.document_rows)} · Embedding chunks:{" "}
                {formatCount(stats.embedding_rows)}
              </p>
            )}
            <label className={styles.confirmationField}>
              <span>
                Type <strong>DELETE</strong> to confirm
              </span>
              <input
                id="rag-delete-confirmation"
                type="text"
                value={confirmation}
                onChange={(event) => onConfirmationChange(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                  }
                }}
                autoComplete="off"
                spellCheck="false"
                disabled={deletePending}
              />
            </label>
            <div className={styles.dialogActions}>
              <button type="button" onClick={onCancel} disabled={deletePending}>
                Cancel
              </button>
              <button
                className={styles.deleteDataButton}
                type="button"
                onClick={onDelete}
                disabled={!canDelete}
              >
                <Trash2 size={16} />
                {deletePending ? "Deleting…" : "Delete all data"}
              </button>
            </div>
          </section>
        </div>
      )}
    </section>
  );
}

export function isDeleteConfirmationValid(value: string) {
  return value === "DELETE";
}

export function RagTabs({
  activeTab,
  onSelect
}: {
  activeTab: RagTab;
  onSelect: (tab: RagTab) => void;
}) {
  return (
    <div className={styles.tabs} role="tablist" aria-label="RAG operations">
      <button
        id="rag-embedding-tab"
        className={activeTab === "embedding" ? styles.tabActive : styles.tab}
        type="button"
        role="tab"
        aria-selected={activeTab === "embedding"}
        aria-controls="rag-embedding-panel"
        onClick={() => onSelect("embedding")}
      >
        <Upload size={16} />
        Embedding
      </button>
      <button
        id="rag-search-tab"
        className={activeTab === "search" ? styles.tabActive : styles.tab}
        type="button"
        role="tab"
        aria-selected={activeTab === "search"}
        aria-controls="rag-search-panel"
        onClick={() => onSelect("search")}
      >
        <Search size={16} />
        Search
      </button>
    </div>
  );
}

export function EmbeddingPanel({
  inputMode,
  selectedFile,
  fileInputRef,
  fileError,
  directText,
  directTextTitle,
  maxChunkTokensInput,
  maxChunkTokensIsValid,
  isPending,
  result,
  apiError,
  onInputModeChange,
  onChooseFile,
  onFileChange,
  onDirectTextChange,
  onDirectTextTitleChange,
  onMaxChunkTokensChange,
  onSubmit
}: {
  inputMode: RagInputMode;
  selectedFile: File | null;
  fileInputRef?: RefObject<HTMLInputElement>;
  fileError: string | null;
  directText: string;
  directTextTitle: string;
  maxChunkTokensInput: string;
  maxChunkTokensIsValid: boolean;
  isPending: boolean;
  result: RagEmbedResponse | null;
  apiError: unknown;
  onInputModeChange: (mode: RagInputMode) => void;
  onChooseFile: () => void;
  onFileChange: (file: File | null) => void;
  onDirectTextChange: (value: string) => void;
  onDirectTextTitleChange: (value: string) => void;
  onMaxChunkTokensChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const error = fileError ?? errorMessage(apiError);
  const hasSource =
    inputMode === "file" ? selectedFile !== null : directText.trim().length > 0;

  return (
    <section
      id="rag-embedding-panel"
      className={styles.panel}
      role="tabpanel"
      aria-labelledby="rag-embedding-tab"
    >
      <div className={styles.panelHeading}>
        <h2>Embed a source document</h2>
        <p>Upload a supported file or enter text directly.</p>
      </div>

      <form className={styles.form} onSubmit={onSubmit}>
        <div className={styles.inputMode} aria-label="Embedding input method">
          <button
            className={inputMode === "file" ? styles.inputModeActive : undefined}
            type="button"
            aria-pressed={inputMode === "file"}
            onClick={() => onInputModeChange("file")}
            disabled={isPending}
          >
            <FileText size={16} />
            File upload
          </button>
          <button
            className={inputMode === "text" ? styles.inputModeActive : undefined}
            type="button"
            aria-pressed={inputMode === "text"}
            onClick={() => onInputModeChange("text")}
            disabled={isPending}
          >
            <TextCursorInput size={16} />
            Direct text
          </button>
        </div>

        {inputMode === "file" ? (
          <>
            <input
              ref={fileInputRef}
              className={styles.fileInput}
              type="file"
              accept={RAG_FILE_ACCEPT}
              onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
            />

            <button
              className={styles.filePicker}
              type="button"
              onClick={onChooseFile}
              disabled={isPending}
            >
              <FileText size={18} />
              <span>
                {selectedFile ? selectedFile.name : "Choose a source file"}
              </span>
            </button>
            <p className={styles.note}>
              Supported: UTF-8 TXT, UTF-8 MD, DOCX, and PDF. Scanned PDF pages
              use automatic OCR. Images embedded in DOCX are not OCRed.
            </p>
          </>
        ) : (
          <div className={styles.directTextFields}>
            <label>
              <span>Display title (optional)</span>
              <input
                type="text"
                value={directTextTitle}
                onChange={(event) => onDirectTextTitleChange(event.target.value)}
                placeholder="A useful source title"
                disabled={isPending}
              />
            </label>
            <label>
              <span>Source text</span>
              <textarea
                value={directText}
                onChange={(event) => onDirectTextChange(event.target.value)}
                placeholder="Type or paste source text"
                rows={10}
                disabled={isPending}
              />
            </label>
            <p className={styles.note}>
              Without a title, a short display name is generated from the first
              non-empty line.
            </p>
          </div>
        )}

        <label className={styles.chunkTokenField}>
          <span>Maximum tokens per chunk</span>
          <input
            type="number"
            min={MIN_RAG_MAX_CHUNK_TOKENS}
            max={MAX_RAG_MAX_CHUNK_TOKENS}
            step="1"
            inputMode="numeric"
            value={maxChunkTokensInput}
            onChange={(event) => onMaxChunkTokensChange(event.target.value)}
            aria-invalid={!maxChunkTokensIsValid}
            aria-describedby="rag-max-chunk-tokens-help"
            disabled={isPending}
          />
          <small id="rag-max-chunk-tokens-help">
            {maxChunkTokensIsValid
              ? "Choose 100–1000. Natural boundaries may produce shorter chunks."
              : "Enter a whole number from 100 to 1000."}
          </small>
        </label>

        <p className={styles.note}>
          Ingesting the same source again can create duplicate document and
          chunk rows.
        </p>

        <button
          className={styles.primaryButton}
          type="submit"
          disabled={!hasSource || !maxChunkTokensIsValid || isPending}
        >
          <Upload size={17} />
          {isPending ? "Embedding document…" : "Embed document"}
        </button>
      </form>

      {result && !isPending && (
        <p className={styles.success} role="status">
          <CheckCircle2 size={17} />
          Document embedded successfully
        </p>
      )}
      {error && (
        <p className={styles.error} role="alert">
          <AlertCircle size={17} />
          {error}
        </p>
      )}

      {result && !isPending && !error && <EmbedResult result={result} />}
    </section>
  );
}

export function EmbedResult({ result }: { result: RagEmbedResponse }) {
  return (
    <section className={styles.embedResult} aria-label="Embedding result">
      <div className={styles.resultSectionHeading}>
        <h3>Processing summary</h3>
        <span>Maximum {result.chunking.max_chunk_tokens} tokens per chunk</span>
      </div>

      <dl className={styles.metricsGrid}>
        <Metric label="Source" value={result.source.source_name} />
        <Metric label="Type" value={sourceTypeLabel(result.source.source_type)} />
        {result.source.filename && (
          <Metric label="Filename" value={result.source.filename} />
        )}
        <Metric label="Source size" value={formatBytes(result.source.size_bytes)} />
        <Metric label="Document tokens" value={String(result.source.token_count)} />
        <Metric label="Chunks" value={String(result.chunking.chunk_count)} />
        <Metric
          label="Chunking"
          value={formatMilliseconds(result.timing_ms.chunking)}
        />
        <Metric
          label="Embedding"
          value={formatMilliseconds(result.timing_ms.embedding)}
        />
        <Metric label="Total" value={formatMilliseconds(result.timing_ms.total)} />
      </dl>

      <div className={styles.previewHeading}>
        <h3>Chunk preview</h3>
        {result.chunking.preview_truncated && (
          <p>Showing the first 10 of {result.chunking.chunk_count} chunks.</p>
        )}
      </div>

      <div className={styles.chunkPreviewList}>
        {result.chunking.chunks.map((chunk) => (
          <article className={styles.chunkPreview} key={chunk.index}>
            <header>
              <strong>Chunk {chunk.index}</strong>
              <span>{chunk.token_count} tokens</span>
              <span>{chunk.character_count} characters</span>
              <span>
                Source characters [{chunk.source_start_character}, {chunk.source_end_character})
              </span>
              <span>
                Overlap with previous: {chunk.overlap_with_previous_tokens} tokens
              </span>
            </header>
            <p>{chunk.context}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

export function SearchPanel({
  query,
  topKInput,
  topKIsValid,
  isPending,
  apiError,
  results,
  timing,
  onQueryChange,
  onTopKChange,
  onSubmit
}: {
  query: string;
  topKInput: string;
  topKIsValid: boolean;
  isPending: boolean;
  apiError: unknown;
  results: RagSearchResult[] | null;
  timing: RagSearchTiming | null;
  onQueryChange: (value: string) => void;
  onTopKChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const error = errorMessage(apiError);

  return (
    <section
      id="rag-search-panel"
      className={styles.panel}
      role="tabpanel"
      aria-labelledby="rag-search-tab"
    >
      <div className={styles.panelHeading}>
        <h2>Search indexed context</h2>
        <p>Results use exact pgvector cosine retrieval.</p>
      </div>

      <form className={styles.searchForm} onSubmit={onSubmit}>
        <label className={styles.queryField}>
          <span>Query</span>
          <input
            type="search"
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="Enter a search question"
            disabled={isPending}
          />
        </label>

        <label className={styles.topKField}>
          <span>Top results</span>
          <input
            type="number"
            min={MIN_RAG_TOP_K}
            max={MAX_RAG_TOP_K}
            step="1"
            inputMode="numeric"
            value={topKInput}
            onChange={(event) => onTopKChange(event.target.value)}
            aria-invalid={!topKIsValid}
            aria-describedby="rag-top-k-help"
            disabled={isPending}
          />
        </label>

        <small className={styles.topKHelp} id="rag-top-k-help">
          {topKIsValid ? "Choose 1–20. Default: 5." : "Enter a whole number from 1 to 20."}
        </small>

        <button
          className={styles.primaryButton}
          type="submit"
          disabled={!query.trim() || !topKIsValid || isPending}
        >
          <Search size={17} />
          {isPending ? "Searching…" : "Search"}
        </button>
      </form>

      {error && (
        <p className={styles.error} role="alert">
          <AlertCircle size={17} />
          {error}
        </p>
      )}

      {results !== null && !isPending && !error && (
        <div className={styles.results} aria-live="polite">
          {timing && <SearchTimingSummary timing={timing} />}
          {results.length === 0 ? (
            <p className={styles.empty}>No matching context found.</p>
          ) : (
            results.map((result, index) => (
              <article className={styles.result} key={`${result.id}-${index}`}>
                <header className={styles.resultHeader}>
                  <strong>Rank {index + 1}</strong>
                  <span>Cosine similarity: {result.similarity}</span>
                </header>
                {result.document_id === null ? (
                  <p className={styles.provenance}>Source unavailable — legacy row</p>
                ) : (
                  <p className={styles.provenance}>
                    <span>Source: {result.source_name}</span>
                    <span>Type: {sourceTypeLabel(result.source_type)}</span>
                    <span>Chunk: {result.chunk_index}</span>
                  </p>
                )}
                <p className={styles.context}>{result.context}</p>
              </article>
            ))
          )}
        </div>
      )}
    </section>
  );
}

export function SearchTimingSummary({ timing }: { timing: RagSearchTiming }) {
  return (
    <p className={styles.searchTiming}>
      <strong>Server processing time</strong>
      <span>Query embedding: {formatMilliseconds(timing.query_embedding)}</span>
      <span>DB search: {formatMilliseconds(timing.database_search)}</span>
      <span>Total: {formatMilliseconds(timing.total)}</span>
    </p>
  );
}

export function isSupportedRagFile(file: Pick<File, "name">) {
  return /\.(txt|md|docx|pdf)$/i.test(file.name);
}

export function parseTopK(value: string): number | null {
  if (!/^\d+$/.test(value.trim())) {
    return null;
  }
  const parsed = Number(value);
  return Number.isInteger(parsed) &&
    parsed >= MIN_RAG_TOP_K &&
    parsed <= MAX_RAG_TOP_K
    ? parsed
    : null;
}

export function parseMaxChunkTokens(value: string): number | null {
  if (!/^\d+$/.test(value.trim())) {
    return null;
  }
  const parsed = Number(value);
  return Number.isInteger(parsed) &&
    parsed >= MIN_RAG_MAX_CHUNK_TOKENS &&
    parsed <= MAX_RAG_MAX_CHUNK_TOKENS
    ? parsed
    : null;
}

function formatMilliseconds(value: number) {
  return `${value.toFixed(3)} ms`;
}

function formatBytes(value: number) {
  return `${value.toLocaleString()} bytes`;
}

function formatCount(value: number) {
  return value.toLocaleString();
}

function sourceTypeLabel(sourceType: "file" | "text" | null) {
  if (sourceType === "file") {
    return "File";
  }
  if (sourceType === "text") {
    return "Direct text";
  }
  return "Unavailable";
}

function errorMessage(error: unknown) {
  if (!error) {
    return null;
  }
  return error instanceof Error ? error.message : "The RAG request failed.";
}
