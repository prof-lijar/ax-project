import {
  Plus,
  ArrowLeft,
  Settings2,
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  BookOpen,
  ArrowRight,
  X,
  FileText,
  Search,
  TextCursorInput,
  Trash2,
  Upload
} from "lucide-react";
import { type FormEvent, type RefObject, useRef, useState } from "react";

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
import { RagDialog } from "./RagDialog";
import styles from "./RagPage.module.css";

export type RagInputMode = "file" | "text";

export const RAG_FILE_ACCEPT = ".txt,.md,.docx,.pdf";

export function RagPage() {
  const [sourceOpen, setSourceOpen] = useState(false);
  const [manageOpen, setManageOpen] = useState(false);
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
  const dataStatsQuery = useRagDataStats();
  const deleteDataMutation = useRagDeleteData();
  const maxChunkTokens = parseMaxChunkTokens(maxChunkTokensInput);
  const topK = parseTopK(topKInput);

  function selectFile(file: File | null) {
    embedMutation.reset();
    if (!file) {
      setSelectedFile(null);
      setFileError(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
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
    if (
      maxChunkTokens === null ||
      embedMutation.isPending ||
      deleteDataMutation.isPending ||
      (fileError && inputMode === "file")
    ) {
      return;
    }
    if (inputMode === "file" && selectedFile) {
      embedMutation.mutate({
        mode: "file",
        file: selectedFile,
        maxChunkTokens
      });
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
    if (
      query.trim() &&
      topK !== null &&
      !searchMutation.isPending &&
      !deleteDataMutation.isPending
    ) {
      searchMutation.mutate({ query, topK });
    }
  }

  function openDeleteConfirmation() {
    if (embedMutation.isPending || searchMutation.isPending) return;
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
      deleteDataMutation.isPending ||
      embedMutation.isPending ||
      searchMutation.isPending
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
        <div>
          <h1>Knowledge</h1>
          <p>
            Add source material your co-workers can use, then explore what they
            can find.
          </p>
        </div>
        <div
          className={styles.knowledgeSummary}
          aria-label="Knowledge summary"
          role="status"
        >
          <BookOpen size={18} aria-hidden />
          {dataStatsQuery.isError ? (
            <button
              type="button"
              onClick={() => void dataStatsQuery.refetch()}
              disabled={dataStatsQuery.isFetching}
            >
              Counts unavailable · Retry
            </button>
          ) : dataStatsQuery.data ? (
            <span>
              <strong>{formatCount(dataStatsQuery.data.document_rows)}</strong>{" "}
              documents <span aria-hidden>·</span>{" "}
              <strong>{formatCount(dataStatsQuery.data.embedding_rows)}</strong>{" "}
              passages
            </span>
          ) : (
            <span>Loading knowledge…</span>
          )}
        </div>
      </header>

      <div className={styles.commandBar}>
        <span>Shared knowledge for your co-workers</span>
        <div className={styles.headerActions}>
          <button
            type="button"
            className={styles.secondaryButton}
            aria-expanded={manageOpen}
            aria-controls="rag-management"
            onClick={() => setManageOpen(!manageOpen)}
          >
            <Settings2 size={16} /> Manage
          </button>
          <button
            type="button"
            className={styles.primaryButton}
            onClick={() => setSourceOpen(true)}
            disabled={deleteDataMutation.isPending}
          >
            <Plus size={17} /> Add source
          </button>
        </div>
      </div>

      <div className={styles.workspace}>
        {sourceOpen && (
          <RagDialog
            pending={embedMutation.isPending}
            onCancel={() => setSourceOpen(false)}
          >
            <div className={styles.drawerBackdrop}>
              <section
                className={styles.sourceDrawer}
                role="dialog"
                aria-modal="true"
                aria-labelledby="rag-embedding-heading"
              >
                <div className={styles.drawerTop}>
                  <span>KNOWLEDGE / ADD SOURCE</span>
                  <button
                    type="button"
                    className={styles.iconButton}
                    aria-label="Close add source"
                    disabled={embedMutation.isPending}
                    onClick={() => setSourceOpen(false)}
                  >
                    <X size={19} />
                  </button>
                </div>
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
                  onSearchKnowledge={() => {
                    setSourceOpen(false);
                    requestAnimationFrame(() =>
                      document.getElementById("rag-query")?.focus()
                    );
                  }}
                  onSubmit={submitEmbed}
                />
              </section>
            </div>
          </RagDialog>
        )}
        <SearchPanel
          emptyKnowledge={dataStatsQuery.data?.embedding_rows === 0}
          onAddSource={() => setSourceOpen(true)}
          query={query}
          topKInput={topKInput}
          topKIsValid={topK !== null}
          isPending={searchMutation.isPending}
          operationsBlocked={deleteDataMutation.isPending}
          apiError={searchMutation.error}
          results={searchMutation.data?.results ?? null}
          timing={searchMutation.data?.timing_ms ?? null}
          searchedQuery={searchMutation.variables?.query}
          onQueryChange={setQuery}
          onTopKChange={setTopKInput}
          onSubmit={submitSearch}
        />
      </div>

      <div
        id="rag-management"
        hidden={!manageOpen}
        className={styles.management}
      >
        <RagDataPanel
          operationsPending={
            embedMutation.isPending || searchMutation.isPending
          }
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
      </div>
    </section>
  );
}

export function RagDataPanel({
  operationsPending = false,
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
  operationsPending?: boolean;
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
  const canDelete =
    isDeleteConfirmationValid(confirmation) &&
    !deletePending &&
    !operationsPending;

  return (
    <section className={styles.dataPanel} aria-labelledby="rag-data-heading">
      <div className={styles.dataPanelHeading}>
        <div>
          <h2 id="rag-data-heading">RAG data</h2>
          <p>
            Review indexed data and remove all knowledge when it is no longer
            needed.
          </p>
        </div>
        <button
          className={styles.emptyDataButton}
          type="button"
          onClick={onOpenConfirmation}
          disabled={
            stats === null || statsPending || deletePending || operationsPending
          }
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
          RAG database emptied successfully. Removed{" "}
          {formatCount(deleteResult.deleted_embedding_rows)} embedding chunks
          and {formatCount(deleteResult.deleted_document_rows)} documents.
        </p>
      )}
      {deleteErrorMessage && !isConfirmationOpen && (
        <p className={styles.error} role="alert">
          <AlertCircle size={17} />
          {deleteErrorMessage}
        </p>
      )}

      {isConfirmationOpen && (
        <RagDialog pending={deletePending} onCancel={onCancel}>
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
                  Documents: {formatCount(stats.document_rows)} · Embedding
                  chunks: {formatCount(stats.embedding_rows)}
                </p>
              )}
              {deleteErrorMessage && (
                <p className={styles.error} role="alert">
                  {deleteErrorMessage}
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
                <button
                  type="button"
                  onClick={onCancel}
                  disabled={deletePending}
                >
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
        </RagDialog>
      )}
    </section>
  );
}

export function isDeleteConfirmationValid(value: string) {
  return value === "DELETE";
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
  onSearchKnowledge,
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
  onSearchKnowledge?: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const [dragging, setDragging] = useState(false);
  const [dropError, setDropError] = useState<string | null>(null);
  const error = dropError ?? fileError ?? errorMessage(apiError);
  const hasSource =
    inputMode === "file" ? selectedFile !== null : directText.trim().length > 0;

  return (
    <section
      id="rag-embedding-panel"
      className={styles.panel}
      aria-labelledby="rag-embedding-heading"
    >
      <div className={styles.panelHeading}>
        <h2 id="rag-embedding-heading">Add to your knowledge</h2>
        <p>Upload a document or paste text to make it searchable.</p>
      </div>

      <form
        className={styles.form}
        onSubmit={(event) => {
          if (dropError) {
            event.preventDefault();
            return;
          }
          onSubmit(event);
        }}
      >
        <div className={styles.inputMode} aria-label="Embedding input method">
          <button
            className={
              inputMode === "file" ? styles.inputModeActive : undefined
            }
            type="button"
            aria-pressed={inputMode === "file"}
            onClick={() => {
              setDropError(null);
              onInputModeChange("file");
            }}
            disabled={isPending}
          >
            <FileText size={16} />
            File upload
          </button>
          <button
            className={
              inputMode === "text" ? styles.inputModeActive : undefined
            }
            type="button"
            aria-pressed={inputMode === "text"}
            onClick={() => {
              setDropError(null);
              onInputModeChange("text");
            }}
            disabled={isPending}
          >
            <TextCursorInput size={16} />
            Paste text
          </button>
        </div>

        {inputMode === "file" ? (
          <>
            <input
              ref={fileInputRef}
              className={styles.fileInput}
              type="file"
              accept={RAG_FILE_ACCEPT}
              disabled={isPending}
              onChange={(event) => {
                setDropError(null);
                onFileChange(event.target.files?.[0] ?? null);
                event.target.value = "";
              }}
            />

            <div
              className={`${styles.dropZone} ${dragging ? styles.dropZoneActive : ""}`}
              onDragOver={(event) => {
                if (Array.from(event.dataTransfer.types).includes("Files")) {
                  event.preventDefault();
                  if (!isPending) setDragging(true);
                }
              }}
              onDragLeave={(event) => {
                if (
                  !event.currentTarget.contains(
                    event.relatedTarget instanceof Node
                      ? event.relatedTarget
                      : null
                  )
                )
                  setDragging(false);
              }}
              onDrop={(event) => {
                event.preventDefault();
                setDragging(false);
                if (isPending) return;
                const files = Array.from(event.dataTransfer.files);
                if (files.length !== 1) {
                  setDropError("Add one document at a time.");
                  return;
                }
                setDropError(null);
                onFileChange(files[0]);
              }}
            >
              {selectedFile ? (
                <div className={styles.selectedFile}>
                  <FileText size={23} aria-hidden />
                  <span>
                    <strong>{selectedFile.name}</strong>
                    <small>
                      {formatBytes(selectedFile.size)} · Ready to add
                    </small>
                  </span>
                  <button
                    type="button"
                    aria-label="Remove file"
                    title="Remove file"
                    disabled={isPending}
                    onClick={() => {
                      setDropError(null);
                      onFileChange(null);
                    }}
                  >
                    <X size={17} />
                  </button>
                </div>
              ) : (
                <>
                  <Upload size={27} aria-hidden />
                  <strong>Drop a document here</strong>
                  <span>PDF, DOCX, TXT or Markdown</span>
                </>
              )}
              <button
                className={styles.filePicker}
                type="button"
                onClick={onChooseFile}
                disabled={isPending}
              >
                {selectedFile ? "Choose another file" : "Choose a source file"}
              </button>
            </div>
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
                onChange={(event) =>
                  onDirectTextTitleChange(event.target.value)
                }
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

        <details className={styles.advancedOptions}>
          <summary>Indexing options</summary>
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
        </details>
        <p className={styles.note}>
          Adding the same source again can create duplicates.
        </p>

        <button
          className={styles.primaryButton}
          type="submit"
          disabled={
            !hasSource ||
            !maxChunkTokensIsValid ||
            isPending ||
            Boolean(fileError || dropError)
          }
        >
          <Upload size={17} />
          {isPending ? "Adding to knowledge…" : "Add to knowledge"}
        </button>
      </form>

      {isPending && (
        <p className={styles.note} role="status">
          Reading and indexing your source. This may take a moment.
        </p>
      )}
      {result && !isPending && !error && (
        <p className={styles.success} role="status">
          <CheckCircle2 size={17} />
          Source added to knowledge
        </p>
      )}
      {error && (
        <p className={styles.error} role="alert">
          <AlertCircle size={17} />
          {error}
        </p>
      )}

      {result && !isPending && !error && (
        <>
          <EmbedResult result={result} />
          {onSearchKnowledge && (
            <button
              className={styles.linkButton}
              type="button"
              onClick={onSearchKnowledge}
            >
              Search your knowledge
              <ArrowRight size={16} aria-hidden />
            </button>
          )}
        </>
      )}
    </section>
  );
}

export function EmbedResult({ result }: { result: RagEmbedResponse }) {
  return (
    <section className={styles.embedResult} aria-label="Embedding result">
      <div className={styles.indexedSummary}>
        <FileText size={21} aria-hidden />
        <div>
          <strong>{result.source.source_name}</strong>
          <p>{result.chunking.chunk_count} searchable passages added</p>
        </div>
      </div>
      <details className={styles.processingDetails}>
        <summary>Processing details</summary>
        <div className={styles.resultSectionHeading}>
          <h3>Processing summary</h3>
          <span>
            Maximum {result.chunking.max_chunk_tokens} tokens per chunk
          </span>
        </div>

        <dl className={styles.metricsGrid}>
          <Metric label="Source" value={result.source.source_name} />
          <Metric
            label="Type"
            value={sourceTypeLabel(result.source.source_type)}
          />
          {result.source.filename && (
            <Metric label="Filename" value={result.source.filename} />
          )}
          <Metric
            label="Source size"
            value={formatBytes(result.source.size_bytes)}
          />
          <Metric
            label="Document tokens"
            value={String(result.source.token_count)}
          />
          <Metric label="Chunks" value={String(result.chunking.chunk_count)} />
          <Metric
            label="Chunking"
            value={formatMilliseconds(result.timing_ms.chunking)}
          />
          <Metric
            label="Embedding"
            value={formatMilliseconds(result.timing_ms.embedding)}
          />
          <Metric
            label="Total"
            value={formatMilliseconds(result.timing_ms.total)}
          />
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
                  Source characters [{chunk.source_start_character},{" "}
                  {chunk.source_end_character})
                </span>
                <span>
                  Overlap with previous: {chunk.overlap_with_previous_tokens}{" "}
                  tokens
                </span>
              </header>
              <p>{chunk.context}</p>
            </article>
          ))}
        </div>
      </details>
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
  emptyKnowledge = false,
  onAddSource,
  operationsBlocked = false,
  query,
  topKInput,
  topKIsValid,
  isPending,
  apiError,
  results,
  timing,
  searchedQuery,
  onQueryChange,
  onTopKChange,
  onSubmit
}: {
  emptyKnowledge?: boolean;
  onAddSource?: () => void;
  operationsBlocked?: boolean;
  query: string;
  topKInput: string;
  topKIsValid: boolean;
  isPending: boolean;
  apiError: unknown;
  results: RagSearchResult[] | null;
  timing: RagSearchTiming | null;
  searchedQuery?: string;
  onQueryChange: (value: string) => void;
  onTopKChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const error = errorMessage(apiError);

  return (
    <section
      id="rag-search-panel"
      className={styles.panel}
      aria-labelledby="rag-search-heading"
    >
      <div className={styles.panelHeading}>
        <h2 id="rag-search-heading">Find useful passages</h2>
        <p>Find the source material behind your team’s work.</p>
      </div>

      <form className={styles.searchForm} onSubmit={onSubmit}>
        <label className={styles.queryField}>
          <span>What are you looking for?</span>
          <input
            id="rag-query"
            type="search"
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="Ask a question or describe a topic"
            disabled={isPending}
          />
        </label>

        <label className={styles.topKField}>
          <span>Passage limit</span>
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
          {topKIsValid
            ? "Choose 1–20. Default: 5."
            : "Enter a whole number from 1 to 20."}
        </small>

        <button
          className={styles.primaryButton}
          type="submit"
          disabled={
            !query.trim() || !topKIsValid || isPending || operationsBlocked
          }
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

      {isPending && (
        <p className={styles.searchStatus} role="status">
          Searching your knowledge…
        </p>
      )}
      {results === null && !isPending && !error && (
        <div className={styles.empty}>
          <Search size={25} aria-hidden />
          <strong>
            {emptyKnowledge
              ? "Build your team’s knowledge"
              : "Find a passage worth using"}
          </strong>
          <p>
            {emptyKnowledge
              ? "Add a document or paste notes to give your co-workers a shared source of knowledge."
              : "Enter a question or topic to explore passages from your sources."}
          </p>
          {emptyKnowledge && onAddSource && (
            <button
              type="button"
              className={styles.primaryButton}
              onClick={onAddSource}
              disabled={operationsBlocked}
            >
              <Plus size={16} /> Add your first source
            </button>
          )}
          <small>
            Search retrieves source passages. Answers are available in Chat.
          </small>
        </div>
      )}
      {results !== null && !isPending && !error && (
        <div className={styles.results}>
          <div className={styles.resultsHeading} role="status">
            <h3>
              {results.length} matching passage{results.length === 1 ? "" : "s"}
            </h3>
            {searchedQuery && <p>Results for “{searchedQuery}”</p>}
          </div>
          {timing && <SearchTimingSummary timing={timing} />}
          {results.length === 0 ? (
            <div className={styles.empty}>
              <BookOpen size={25} aria-hidden />
              <strong>No matching passages</strong>
              <p>Try different words or add a source that covers this topic.</p>
            </div>
          ) : (
            <PassageWorkspace key={searchedQuery} results={results} />
          )}
        </div>
      )}
    </section>
  );
}

export function PassageWorkspace({ results }: { results: RagSearchResult[] }) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [reading, setReading] = useState(false);
  const selected = results[selectedIndex] ?? results[0];
  const rowRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const readerRef = useRef<HTMLElement>(null);
  if (!selected) return null;
  return (
    <div
      className={`${styles.passageWorkspace} ${reading ? styles.reading : ""}`}
    >
      <ol className={styles.passageList} aria-label="Matching passages">
        {results.map((result, index) => (
          <li key={`${result.id}-${index}`}>
            <button
              type="button"
              ref={(node) => {
                rowRefs.current[index] = node;
              }}
              className={`${styles.passageRow} ${index === selectedIndex ? styles.selectedPassage : ""}`}
              aria-pressed={index === selectedIndex}
              aria-controls="rag-passage-reader"
              onClick={() => {
                setSelectedIndex(index);
                setReading(true);
                requestAnimationFrame(() => {
                  readerRef.current?.focus({ preventScroll: true });
                  if (readerRef.current) readerRef.current.scrollTop = 0;
                });
              }}
            >
              <span className={styles.passageRank}>
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className={styles.passageExcerpt}>
                <strong>{result.source_name || "Source unavailable"}</strong>
                <span>{result.context}</span>
                <small>
                  {sourceTypeLabel(result.source_type)}
                  {result.chunk_index !== null
                    ? ` · Passage ${result.chunk_index}`
                    : " · Source details unavailable"}
                </small>
              </span>
              <ArrowRight size={15} aria-hidden />
            </button>
          </li>
        ))}
      </ol>
      <section
        id="rag-passage-reader"
        ref={readerRef}
        tabIndex={-1}
        className={styles.passageReader}
        aria-label="Selected passage"
      >
        <button
          type="button"
          className={styles.backToResults}
          onClick={() => {
            setReading(false);
            requestAnimationFrame(() =>
              rowRefs.current[selectedIndex]?.focus()
            );
          }}
        >
          <ArrowLeft size={16} /> Back to results
        </button>
        <div className={styles.readerEyebrow}>
          <FileText size={16} /> SOURCE PASSAGE · {selectedIndex + 1} OF{" "}
          {results.length}
        </div>
        <h3>{selected.source_name || "Source unavailable"}</h3>
        <p className={styles.readerSubtitle}>
          {sourceTypeLabel(selected.source_type)}
          {selected.chunk_index !== null
            ? ` · Passage ${selected.chunk_index}`
            : ""}
        </p>
        <p className={styles.readerContext}>{selected.context}</p>
        <details className={styles.matchDetails}>
          <summary>Source details</summary>
          <dl className={styles.sourceDetails}>
            <Metric
              label="Cosine similarity"
              value={String(selected.similarity)}
            />
            <Metric
              label="Document ID"
              value={
                selected.document_id === null
                  ? "Unavailable — legacy row"
                  : String(selected.document_id)
              }
            />
            <Metric
              label="Passage"
              value={
                selected.chunk_index === null
                  ? "Unavailable"
                  : String(selected.chunk_index)
              }
            />
            <Metric
              label="Tokens"
              value={
                selected.token_count === null
                  ? "Unavailable"
                  : String(selected.token_count)
              }
            />
            <Metric
              label="Source characters"
              value={
                selected.source_start_character === null ||
                selected.source_end_character === null
                  ? "Unavailable"
                  : `[${selected.source_start_character}, ${selected.source_end_character})`
              }
            />
          </dl>
        </details>
      </section>
    </div>
  );
}

export function SearchTimingSummary({ timing }: { timing: RagSearchTiming }) {
  return (
    <details className={styles.searchTiming}>
      <summary>Search timing · {formatMilliseconds(timing.total)}</summary>
      <div>
        <strong>Server processing time</strong>
        <span>
          Query embedding: {formatMilliseconds(timing.query_embedding)}
        </span>
        <span>DB search: {formatMilliseconds(timing.database_search)}</span>
        <span>Total: {formatMilliseconds(timing.total)}</span>
      </div>
    </details>
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
