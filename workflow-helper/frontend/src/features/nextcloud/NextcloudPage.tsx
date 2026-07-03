import {
  AlertTriangle,
  ChevronRight,
  Cloud,
  Download,
  File,
  FileText,
  Folder,
  RefreshCw
} from "lucide-react";
import { useMemo, useState } from "react";

import {
  useNextcloudDownloadUrl,
  useNextcloudFiles,
  useNextcloudStatus,
  useNextcloudTextFile
} from "../../shared/api/queries";
import type { NextcloudFileItem } from "../../shared/types/nextcloud";
import styles from "./NextcloudPage.module.css";

export function NextcloudPage() {
  const [currentPath, setCurrentPath] = useState("");
  const [selected, setSelected] = useState<NextcloudFileItem | null>(null);
  const statusQuery = useNextcloudStatus();
  const status = statusQuery.data;
  const canLoadFiles = status?.ok ?? false;
  const filesQuery = useNextcloudFiles(currentPath, canLoadFiles);
  const items = useMemo(
    () => sortItems(filesQuery.data?.items ?? []),
    [filesQuery.data?.items]
  );
  const selectedIsText = selected ? isTextPreviewable(selected) : false;
  const textQuery = useNextcloudTextFile(
    selected?.path ?? "",
    Boolean(selected && !selected.isDirectory && selectedIsText)
  );
  const downloadUrlQuery = useNextcloudDownloadUrl(
    selected?.path ?? "",
    Boolean(selected && !selected.isDirectory)
  );

  function openFolder(path: string) {
    setCurrentPath(path);
    setSelected(null);
  }

  if (statusQuery.isError) {
    return (
      <OfflineState
        backendUrl="http://127.0.0.1:8000"
        detail="Unable to check local backend status."
      />
    );
  }

  if (status && !status.ok) {
    return <OfflineState backendUrl={status.backendUrl} detail={status.detail} />;
  }

  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <div>
          <span className={styles.eyebrow}>Drive</span>
          <h1>NextCloud</h1>
          <p>Browse shared work files without turning this into a file manager.</p>
        </div>
        <button
          className={styles.refreshButton}
          onClick={() => {
            void statusQuery.refetch();
            void filesQuery.refetch();
          }}
          type="button"
        >
          <RefreshCw size={16} />
          Refresh
        </button>
      </header>

      <nav className={styles.breadcrumbs} aria-label="NextCloud path">
        <button type="button" onClick={() => openFolder("")}>
          Files
        </button>
        {pathParts(currentPath).map((part) => (
          <span key={part.path}>
            <ChevronRight size={14} />
            <button type="button" onClick={() => openFolder(part.path)}>
              {part.name}
            </button>
          </span>
        ))}
      </nav>

      <div className={styles.workspace}>
        <section className={styles.fileList} aria-label="NextCloud files">
          {statusQuery.isLoading || filesQuery.isLoading ? (
            <LoadingState />
          ) : filesQuery.isError ? (
            <ErrorState message="Could not load this folder. Check backend and Nextcloud configuration." />
          ) : items.length === 0 ? (
            <EmptyState />
          ) : (
            items.map((item) => (
              <button
                className={
                  selected?.path === item.path ? styles.fileItemActive : styles.fileItem
                }
                key={item.path}
                onClick={() =>
                  item.isDirectory ? openFolder(item.path) : setSelected(item)
                }
                type="button"
              >
                <span className={styles.fileIcon}>
                  {item.isDirectory ? <Folder size={19} /> : iconForFile(item)}
                </span>
                <span className={styles.fileCopy}>
                  <strong>{item.name}</strong>
                  <small>{itemSubtitle(item)}</small>
                </span>
                <span className={styles.fileMeta}>
                  {item.isDirectory ? "Folder" : formatSize(item.size)}
                </span>
              </button>
            ))
          )}
        </section>

        <aside className={styles.details}>
          {selected ? (
            <FileDetails
              downloadUrl={downloadUrlQuery.data}
              item={selected}
              previewError={textQuery.isError}
              previewText={textQuery.data?.content}
              previewLoading={textQuery.isLoading}
              textPreviewable={selectedIsText}
            />
          ) : (
            <NoSelection />
          )}
        </aside>
      </div>
    </section>
  );
}

function OfflineState({
  backendUrl,
  detail
}: {
  backendUrl: string;
  detail: string | null;
}) {
  return (
    <section className={styles.offline}>
      <AlertTriangle size={24} />
      <div>
        <h1>NextCloud is not connected</h1>
        <p>{detail ?? "The local backend is not reachable."}</p>
        <code>{backendUrl}</code>
        <div className={styles.setup}>
          <strong>Expected backend setup</strong>
          <span>Run FastAPI from `backend/` and configure `NC_URL`, `NC_USER`, and `NC_PASS`.</span>
        </div>
      </div>
    </section>
  );
}

function LoadingState() {
  return <div className={styles.state}>Loading files...</div>;
}

function ErrorState({ message }: { message: string }) {
  return <div className={styles.state}>{message}</div>;
}

function EmptyState() {
  return <div className={styles.state}>This folder is empty.</div>;
}

function NoSelection() {
  return (
    <div className={styles.noSelection}>
      <Cloud size={24} />
      <strong>Select a file</strong>
      <span>Metadata and text preview will appear here.</span>
    </div>
  );
}

function FileDetails({
  downloadUrl,
  item,
  previewError,
  previewLoading,
  previewText,
  textPreviewable
}: {
  downloadUrl?: string;
  item: NextcloudFileItem;
  previewError: boolean;
  previewLoading: boolean;
  previewText?: string;
  textPreviewable: boolean;
}) {
  return (
    <div className={styles.fileDetails}>
      <header>
        <span className={styles.largeIcon}>{iconForFile(item)}</span>
        <div>
          <h2>{item.name}</h2>
          <p>{item.contentType ?? "Unknown file type"}</p>
        </div>
      </header>

      <dl>
        <div>
          <dt>Path</dt>
          <dd>{item.path}</dd>
        </div>
        <div>
          <dt>Size</dt>
          <dd>{formatSize(item.size)}</dd>
        </div>
        <div>
          <dt>Modified</dt>
          <dd>{formatModified(item.lastModified)}</dd>
        </div>
      </dl>

      {downloadUrl ? (
        <a className={styles.downloadButton} download href={downloadUrl}>
          <Download size={16} />
          Download
        </a>
      ) : null}

      <section className={styles.preview}>
        <h3>Preview</h3>
        {previewLoading ? <p>Loading preview...</p> : null}
        {!textPreviewable ? <p>Preview unavailable for this file type.</p> : null}
        {previewError ? <p>Preview unavailable. Use download instead.</p> : null}
        {previewText ? <pre>{previewText}</pre> : null}
      </section>
    </div>
  );
}

function iconForFile(item: NextcloudFileItem) {
  if (item.isDirectory) {
    return <Folder size={19} />;
  }

  return isTextPreviewable(item) ? <FileText size={19} /> : <File size={19} />;
}

function itemSubtitle(item: NextcloudFileItem) {
  if (item.isDirectory) {
    return formatModified(item.lastModified);
  }

  return `${item.contentType ?? "File"} · ${formatModified(item.lastModified)}`;
}

function sortItems(items: NextcloudFileItem[]) {
  return [...items].sort((a, b) => {
    if (a.isDirectory !== b.isDirectory) {
      return a.isDirectory ? -1 : 1;
    }

    return a.name.localeCompare(b.name);
  });
}

function pathParts(path: string) {
  if (!path) {
    return [];
  }

  const parts = path.split("/");
  return parts.map((name, index) => ({
    name,
    path: parts.slice(0, index + 1).join("/")
  }));
}

function formatSize(size: number | null) {
  if (size === null) {
    return "-";
  }

  if (size < 1024) {
    return `${size} B`;
  }

  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }

  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function formatModified(value: string | null) {
  if (!value) {
    return "Modified time unknown";
  }

  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

function isTextPreviewable(item: NextcloudFileItem) {
  const contentType = item.contentType?.toLowerCase() ?? "";
  const name = item.name.toLowerCase();
  const extension = name.includes(".") ? name.split(".").pop() ?? "" : "";
  const textExtensions = new Set([
    "csv",
    "env",
    "json",
    "log",
    "md",
    "py",
    "rs",
    "toml",
    "ts",
    "tsx",
    "txt",
    "xml",
    "yaml",
    "yml"
  ]);

  return (
    contentType.startsWith("text/") ||
    contentType.includes("json") ||
    contentType.includes("xml") ||
    textExtensions.has(extension)
  );
}
