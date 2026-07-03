import {
  AlertTriangle,
  ChevronRight,
  Download,
  File,
  FileText,
  Folder,
  RefreshCw
} from "lucide-react";
import { useMemo, useState } from "react";

import {
  useNextcloudDownloadFile,
  useNextcloudFiles,
  useNextcloudStatus
} from "../../shared/api/queries";
import type { NextcloudFileItem } from "../../shared/types/nextcloud";
import styles from "./NextcloudPage.module.css";

export function NextcloudPage() {
  const [currentPath, setCurrentPath] = useState("");
  const statusQuery = useNextcloudStatus();
  const status = statusQuery.data;
  const canLoadFiles = status?.ok ?? false;
  const filesQuery = useNextcloudFiles(currentPath, canLoadFiles);
  const items = useMemo(
    () => sortItems(filesQuery.data?.items ?? []),
    [filesQuery.data?.items]
  );
  const downloadMutation = useNextcloudDownloadFile();
  const downloadingPath = downloadMutation.isPending
    ? downloadMutation.variables
    : null;

  function openFolder(path: string) {
    setCurrentPath(path);
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
              <FileRow
                downloadError={
                  downloadMutation.isError && downloadMutation.variables === item.path
                }
                downloading={downloadingPath === item.path}
                downloadResult={
                  downloadMutation.data?.path === item.path
                    ? downloadMutation.data
                    : undefined
                }
                item={item}
                key={item.path}
                onDownload={() => downloadMutation.mutate(item.path)}
                onOpenFolder={() => openFolder(item.path)}
              />
            ))
          )}
        </section>
      </div>
    </section>
  );
}

function FileRow({
  downloadError,
  downloading,
  downloadResult,
  item,
  onDownload,
  onOpenFolder
}: {
  downloadError: boolean;
  downloading: boolean;
  downloadResult?: { bytesWritten: number };
  item: NextcloudFileItem;
  onDownload: () => void;
  onOpenFolder: () => void;
}) {
  if (item.isDirectory) {
    return (
      <button className={styles.fileItem} onClick={onOpenFolder} type="button">
        <span className={styles.fileIcon}>
          <Folder size={19} />
        </span>
        <span className={styles.fileCopy}>
          <strong>{item.name}</strong>
          <small>{itemSubtitle(item)}</small>
        </span>
        <span className={styles.fileMeta}>Folder</span>
      </button>
    );
  }

  return (
    <div className={styles.fileItem}>
      <span className={styles.fileIcon}>
        {iconForFile(item)}
      </span>
      <span className={styles.fileCopy}>
        <strong>{item.name}</strong>
        <small>
          {downloadError
            ? "Download failed"
            : downloadResult
              ? `Downloaded ${formatSize(downloadResult.bytesWritten)}`
              : itemSubtitle(item)}
        </small>
      </span>
      <span className={styles.fileMeta}>{formatSize(item.size)}</span>
      <button
        className={styles.rowDownloadButton}
        disabled={downloading}
        onClick={onDownload}
        type="button"
        title={`Download ${item.name}`}
      >
        <Download size={16} />
        <span>{downloading ? "Downloading" : "Download"}</span>
      </button>
    </div>
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
