import {
  AlertCircle,
  CheckCircle2,
  Database,
  FileText,
  Search,
  Upload
} from "lucide-react";
import {
  type FormEvent,
  type RefObject,
  useRef,
  useState
} from "react";

import { useRagEmbed, useRagSearch } from "../../shared/api/queries";
import {
  DEFAULT_RAG_TOP_K,
  MAX_RAG_TOP_K,
  MIN_RAG_TOP_K,
  type RagSearchResult
} from "../../shared/api/ragClient";
import styles from "./RagPage.module.css";

export type RagTab = "embedding" | "search";

export const RAG_FILE_ACCEPT = ".txt,.md,.pdf";

export function RagPage() {
  const [activeTab, setActiveTab] = useState<RagTab>("embedding");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [topKInput, setTopKInput] = useState(String(DEFAULT_RAG_TOP_K));
  const fileInputRef = useRef<HTMLInputElement>(null);
  const embedMutation = useRagEmbed();
  const searchMutation = useRagSearch();
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
      setFileError("Choose a TXT, MD, or PDF file.");
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
    if (selectedFile && !embedMutation.isPending) {
      embedMutation.mutate(selectedFile);
    }
  }

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (query.trim() && topK !== null && !searchMutation.isPending) {
      searchMutation.mutate({ query, topK });
    }
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
            selectedFile={selectedFile}
            fileInputRef={fileInputRef}
            fileError={fileError}
            isPending={embedMutation.isPending}
            isSuccess={embedMutation.isSuccess}
            apiError={embedMutation.error}
            onChooseFile={() => fileInputRef.current?.click()}
            onFileChange={selectFile}
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
            onQueryChange={setQuery}
            onTopKChange={setTopKInput}
            onSubmit={submitSearch}
          />
        )}
      </div>
    </section>
  );
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
  selectedFile,
  fileInputRef,
  fileError,
  isPending,
  isSuccess,
  apiError,
  onChooseFile,
  onFileChange,
  onSubmit
}: {
  selectedFile: File | null;
  fileInputRef?: RefObject<HTMLInputElement>;
  fileError: string | null;
  isPending: boolean;
  isSuccess: boolean;
  apiError: unknown;
  onChooseFile: () => void;
  onFileChange: (file: File | null) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const error = fileError ?? errorMessage(apiError);

  return (
    <section
      id="rag-embedding-panel"
      className={styles.panel}
      role="tabpanel"
      aria-labelledby="rag-embedding-tab"
    >
      <div className={styles.panelHeading}>
        <h2>Embed a source file</h2>
        <p>Supported: UTF-8 TXT, UTF-8 MD, and text-based PDF.</p>
      </div>

      <form className={styles.form} onSubmit={onSubmit}>
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
          <span>{selectedFile ? selectedFile.name : "Choose a source file"}</span>
        </button>

        <p className={styles.note}>
          Scanned/image-only PDFs are not supported. Uploading the same source
          again can create duplicate rows.
        </p>

        <button
          className={styles.primaryButton}
          type="submit"
          disabled={!selectedFile || isPending}
        >
          <Upload size={17} />
          {isPending ? "Embedding document…" : "Embed document"}
        </button>
      </form>

      {isSuccess && !isPending && (
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
    </section>
  );
}

export function SearchPanel({
  query,
  topKInput,
  topKIsValid,
  isPending,
  apiError,
  results,
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
          <small id="rag-top-k-help">
            {topKIsValid ? "Choose 1–20. Default: 5." : "Enter a whole number from 1 to 20."}
          </small>
        </label>

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
          {results.length === 0 ? (
            <p className={styles.empty}>No matching context found.</p>
          ) : (
            results.map((result, index) => (
              <article className={styles.result} key={`${result.id}-${index}`}>
                <header className={styles.resultHeader}>
                  <strong>Rank {index + 1}</strong>
                  <span>Cosine similarity: {result.similarity}</span>
                </header>
                <p className={styles.context}>{result.context}</p>
              </article>
            ))
          )}
        </div>
      )}
    </section>
  );
}

export function isSupportedRagFile(file: Pick<File, "name">) {
  return /\.(txt|md|pdf)$/i.test(file.name);
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

function errorMessage(error: unknown) {
  if (!error) {
    return null;
  }
  return error instanceof Error ? error.message : "The RAG request failed.";
}
