import { t, useLanguage, locale } from "../../shared/i18n";
import {
  ArrowLeft,
  ChevronRight,
  CloudOff,
  Download,
  EllipsisVertical,
  File,
  FileText,
  Folder,
  Image as ImageIcon,
  LayoutGrid,
  List,
  RefreshCw
} from "lucide-react";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";

import {
  useNextcloudDownloadFile,
  useNextcloudFiles,
  useNextcloudPreviewFile,
  useNextcloudStatus
} from "../../shared/api/queries";
import type {
  NextcloudFileItem,
  NextcloudPreviewResponse
} from "../../shared/types/nextcloud";
import styles from "./NextcloudPage.module.css";

export function NextcloudPage() {
  useLanguage((state) => state.language);
  const [currentPath, setCurrentPath] = useState("");
  const [viewerItem, setViewerItem] = useState<NextcloudFileItem | null>(null);
  const [viewMode, setViewMode] = useState<"list" | "card">("list");
  const previewObjectUrlRef = useRef<string | null>(null);
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
  const previewQuery = useNextcloudPreviewFile(
    viewerItem?.path ?? "",
    Boolean(viewerItem)
  );

  useEffect(() => {
    const currentObjectUrl = previewQuery.data?.objectUrl ?? null;
    const previousObjectUrl = previewObjectUrlRef.current;
    if (previousObjectUrl && previousObjectUrl !== currentObjectUrl) {
      URL.revokeObjectURL(previousObjectUrl);
    }
    previewObjectUrlRef.current = currentObjectUrl;
  }, [previewQuery.data?.objectUrl]);

  function revokePreviewObjectUrl() {
    if (previewObjectUrlRef.current) {
      URL.revokeObjectURL(previewObjectUrlRef.current);
      previewObjectUrlRef.current = null;
    }
  }

  function openFolder(path: string) {
    revokePreviewObjectUrl();
    setViewerItem(null);
    setCurrentPath(path);
  }

  function openViewer(item: NextcloudFileItem) {
    revokePreviewObjectUrl();
    setViewerItem(item);
  }

  function closeViewer() {
    revokePreviewObjectUrl();
    setViewerItem(null);
  }

  if (statusQuery.isError) {
    return (
      <OfflineState
        backendUrl="/api/nextcloud"
        detail={t("Unable to check local backend status.")}
        loading={statusQuery.isFetching}
        onRetry={() => void statusQuery.refetch()}
      />
    );
  }

  if (status && !status.ok) {
    return (
      <OfflineState
        backendUrl={status.backendUrl}
        detail={status.detail}
        loading={statusQuery.isFetching}
        onRetry={() => void statusQuery.refetch()}
      />
    );
  }

  return (
    <section className={styles.page}>
      <NextcloudToolbar
        currentPath={currentPath}
        onOpenFolder={openFolder}
        onViewModeChange={setViewMode}
        viewMode={viewMode}
      />

      <div className={styles.workspace}>
        {viewerItem ? (
          <FileViewer
            downloadError={
              downloadMutation.isError &&
              downloadMutation.variables === viewerItem.path
            }
            downloading={downloadingPath === viewerItem.path}
            downloadResult={
              downloadMutation.data?.path === viewerItem.path
                ? downloadMutation.data
                : undefined
            }
            item={viewerItem}
            onBack={closeViewer}
            onDownload={() => downloadMutation.mutate(viewerItem.path)}
            preview={previewQuery.data}
            previewError={previewQuery.isError}
            previewErrorMessage={errorMessage(previewQuery.error)}
            previewLoading={previewQuery.isLoading}
          />
        ) : (
          <section
            className={`${styles.fileList} ${
              viewMode === "card" ? styles.fileListCards : ""
            }`}
            aria-label={t("NextCloud files")}
          >
            {statusQuery.isLoading || filesQuery.isLoading ? (
              <LoadingState />
            ) : filesQuery.isError ? (
              <FilesUnavailableState
                loading={filesQuery.isFetching}
                onRetry={() => void filesQuery.refetch()}
              />
            ) : items.length === 0 ? (
              <EmptyState />
            ) : (
              <>
                {viewMode === "list" ? <FileListHeader /> : null}
                {items.map((item) => (
                  <FileRow
                    downloadError={
                      downloadMutation.isError &&
                      downloadMutation.variables === item.path
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
                    onOpen={() => openViewer(item)}
                    viewMode={viewMode}
                    viewable={isViewable(item)}
                  />
                ))}
              </>
            )}
          </section>
        )}
      </div>
    </section>
  );
}

export function NextcloudToolbar({
  currentPath,
  onOpenFolder,
  onViewModeChange,
  viewMode
}: {
  currentPath: string;
  onOpenFolder: (path: string) => void;
  onViewModeChange: (viewMode: "list" | "card") => void;
  viewMode: "list" | "card";
}) {
  useLanguage((state) => state.language);
  return (
    <header className={styles.toolbar}>
      <h1>NextCloud</h1>
      <div className={styles.locationRow}>
        <nav className={styles.breadcrumbs} aria-label={t("NextCloud path")}>
          {currentPath ? (
            <>
              <button
                className={styles.breadcrumbBack}
                aria-label={t("Back one folder")}
                title={t("Back")}
                type="button"
                onClick={() => onOpenFolder(parentPath(currentPath))}
              >
                <ArrowLeft size={16} aria-hidden />
              </button>
              <button type="button" onClick={() => onOpenFolder("")}>
                Nexgent
              </button>
              {pathParts(currentPath).map((part) => (
                <span key={part.path}>
                  <ChevronRight size={13} aria-hidden />
                  <button
                    type="button"
                    onClick={() => onOpenFolder(part.path)}
                  >
                    {part.name}
                  </button>
                </span>
              ))}
            </>
          ) : (
            <span className={styles.currentLocation}>Nexgent</span>
          )}
        </nav>

        <div
          className={styles.viewSwitch}
          role="group"
          aria-label={t("File layout")}
        >
          <button
            aria-label={t("List view")}
            aria-pressed={viewMode === "list"}
            className={styles.viewSwitchButton}
            onClick={() => onViewModeChange("list")}
            title={t("List view")}
            type="button"
          >
            <List size={17} aria-hidden />
          </button>
          <button
            aria-label={t("Card view")}
            aria-pressed={viewMode === "card"}
            className={styles.viewSwitchButton}
            onClick={() => onViewModeChange("card")}
            title={t("Card view")}
            type="button"
          >
            <LayoutGrid size={17} aria-hidden />
          </button>
        </div>
      </div>
    </header>
  );
}

function FileListHeader() {
  useLanguage((state) => state.language);
  return (
    <div className={styles.fileListHeader} aria-hidden>
      <span className={styles.listHeaderName}>{t("Name")}</span>
      <span className={styles.listHeaderType}>{t("Type")}</span>
      <span className={styles.listHeaderModified}>{t("Modified")}</span>
      <span className={styles.listHeaderSize}>{t("Size")}</span>
      <span />
    </div>
  );
}

function FileRow({
  downloadError,
  downloading,
  downloadResult,
  item,
  onDownload,
  onOpenFolder,
  onOpen,
  viewMode,
  viewable
}: {
  downloadError: boolean;
  downloading: boolean;
  downloadResult?: { bytesWritten: number };
  item: NextcloudFileItem;
  onDownload: () => void;
  onOpenFolder: () => void;
  onOpen: () => void;
  viewMode: "list" | "card";
  viewable: boolean;
}) {
  useLanguage((state) => state.language);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLSpanElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const downloadButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!menuOpen) {
      return;
    }

    if (!downloading) {
      downloadButtonRef.current?.focus();
    }

    function closeMenuOnOutsideClick(event: PointerEvent) {
      if (
        event.target instanceof Node &&
        !menuRef.current?.contains(event.target)
      ) {
        setMenuOpen(false);
      }
    }

    function closeMenuOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMenuOpen(false);
        menuButtonRef.current?.focus();
      }
    }

    document.addEventListener("pointerdown", closeMenuOnOutsideClick);
    document.addEventListener("keydown", closeMenuOnEscape);

    return () => {
      document.removeEventListener("pointerdown", closeMenuOnOutsideClick);
      document.removeEventListener("keydown", closeMenuOnEscape);
    };
  }, [downloading, menuOpen]);

  if (item.isDirectory) {
    return (
      <button
        className={`${styles.fileItem} ${styles.folderRow} ${
          viewMode === "card" ? styles.folderCard : ""
        }`}
        onClick={onOpenFolder}
        type="button"
      >
        <span className={styles.fileIcon}>
          <Folder size={19} />
        </span>
        <span className={styles.fileCopy}>
          <strong>{item.name}</strong>
          <small className={styles.compactMetadata}>{itemSubtitle(item)}</small>
        </span>
        <span className={styles.fileMetadata}>
          <span className={styles.fileType}>{t("Folder")}</span>
          <span className={styles.fileModified}>
            {formatModified(item.lastModified)}
          </span>
          <span className={styles.fileSize}>—</span>
        </span>
        <span className={styles.rowActionSpacer} aria-hidden />
      </button>
    );
  }

  const fileDetails = (
    <>
      <span className={styles.fileIcon}>
        {iconForFile(item, 19)}
      </span>
      <span className={styles.fileCopy}>
        <strong>{item.name}</strong>
        <small className={styles.compactMetadata}>
          {downloadError
            ? t("Download failed")
            : downloadResult
              ? t("Downloaded {0}", { 0: formatSize(downloadResult.bytesWritten) })
              : itemSubtitle(item)}
        </small>
      </span>
      <span className={styles.fileMetadata}>
        <span className={styles.fileType}>
          {downloadError
            ? t("Download failed")
            : downloadResult
              ? t("Downloaded {0}", { 0: formatSize(downloadResult.bytesWritten) })
              : fileTypeLabel(item)}
        </span>
        <span className={styles.fileModified}>
          {formatModified(item.lastModified)}
        </span>
        <span className={styles.fileSize}>{formatSize(item.size)}</span>
      </span>
    </>
  );

  return (
    <div
      className={`${styles.fileItem} ${styles.fileRow} ${
        viewMode === "card" ? styles.fileCard : ""
      }`}
    >
      {viewable ? (
        <button
          className={styles.fileOpenButton}
          onClick={onOpen}
          type="button"
          title={t("Open {0}", { 0: item.name })}
        >
          {fileDetails}
        </button>
      ) : (
        <div className={styles.fileDetails}>{fileDetails}</div>
      )}
      <span className={styles.rowActions} ref={menuRef}>
        <button
          aria-expanded={menuOpen}
          aria-haspopup="menu"
          aria-label={t("Actions for {0}", { 0: item.name })}
          className={styles.actionMenuButton}
          onClick={() => setMenuOpen((open) => !open)}
          ref={menuButtonRef}
          type="button"
        >
          <EllipsisVertical size={19} />
        </button>
        {menuOpen ? (
          <span className={styles.actionMenu} role="menu">
            <button
              className={styles.actionMenuItem}
              disabled={downloading}
              onClick={() => {
                setMenuOpen(false);
                onDownload();
              }}
              ref={downloadButtonRef}
              role="menuitem"
              type="button"
            >
              <Download size={16} />
              <span>{downloading ? t("Downloading") : t("Download")}</span>
            </button>
          </span>
        ) : null}
      </span>
    </div>
  );
}

function FileViewer({
  downloadError,
  downloading,
  downloadResult,
  item,
  onBack,
  onDownload,
  preview,
  previewError,
  previewErrorMessage,
  previewLoading
}: {
  downloadError: boolean;
  downloading: boolean;
  downloadResult?: { bytesWritten: number };
  item: NextcloudFileItem;
  onBack: () => void;
  onDownload: () => void;
  preview?: NextcloudPreviewResponse;
  previewError: boolean;
  previewErrorMessage: string;
  previewLoading: boolean;
}) {
  useLanguage((state) => state.language);
  return (
    <section className={styles.viewer} aria-label={t("Viewer for {0}", { 0: item.name })}>
      <header className={styles.viewerHeader}>
        <button className={styles.backButton} onClick={onBack} type="button">
          <ArrowLeft size={16} />
          {t("Back")}</button>
        <div>
          <h2>{item.name}</h2>
          <p>{itemSubtitle(item)}</p>
        </div>
        <button
          className={styles.viewerDownloadButton}
          disabled={downloading}
          onClick={onDownload}
          type="button"
        >
          <Download size={16} />
          {downloading ? t("Downloading") : t("Download")}
        </button>
      </header>

      {downloadResult ? (
        <p className={styles.viewerStatus}>
          {t("Downloaded")} {formatSize(downloadResult.bytesWritten)}
        </p>
      ) : null}
      {downloadError ? (
        <p className={styles.viewerError}>{t("Download failed. Try again.")}</p>
      ) : null}

      <div className={styles.viewerBody}>
        {previewLoading ? <LoadingState /> : null}
        {previewError ? (
          <ErrorState
            message={
              previewErrorMessage ||
              t("Preview unavailable. Download this file instead.")
            }
          />
        ) : null}
        {!previewLoading && !previewError && preview ? (
          <PreviewSurface preview={preview} />
        ) : null}
      </div>
    </section>
  );
}

function PreviewSurface({ preview }: { preview: NextcloudPreviewResponse }) {
  useLanguage((state) => state.language);
  if (preview.viewerKind === "pdf" && preview.objectUrl) {
    return (
      <iframe
        className={styles.pdfViewer}
        src={preview.objectUrl}
        title={preview.filename}
      />
    );
  }

  if (preview.viewerKind === "image" && preview.objectUrl) {
    return (
      <div className={styles.imageViewer}>
        <img alt={preview.filename} src={preview.objectUrl} />
      </div>
    );
  }

  if (preview.viewerKind === "text") {
    if (isMarkdownPreview(preview)) {
      return <MarkdownViewer content={preview.text ?? ""} />;
    }

    return <pre className={styles.textViewer}>{preview.text ?? ""}</pre>;
  }

  return <ErrorState message={t("Preview unavailable. Download this file instead.")} />;
}

function OfflineState({
  backendUrl,
  detail,
  loading,
  onRetry
}: {
  backendUrl: string;
  detail: string | null;
  loading: boolean;
  onRetry: () => void;
}) {
  useLanguage((state) => state.language);
  return (
    <section className={styles.offline}>
      <span className={styles.offlineIcon}>
        <CloudOff size={28} />
      </span>
      <div>
        <h1>{t("NextCloud is not connected")}</h1>
        <p>{detail ?? t("Connect the service to browse shared files.")}</p>
        <small>{backendUrl}</small>
        <button
          className={styles.retryButton}
          disabled={loading}
          onClick={onRetry}
          type="button"
        >
          <RefreshCw size={16} />
          {loading ? t("Checking") : t("Try again")}
        </button>
      </div>
    </section>
  );
}

function FilesUnavailableState({
  loading,
  onRetry
}: {
  loading: boolean;
  onRetry: () => void;
}) {
  useLanguage((state) => state.language);
  return (
    <div className={styles.filesUnavailable}>
      <CloudOff size={28} />
      <strong>{t("Files are unavailable")}</strong>
      <p>{t("We couldn’t fetch this NextCloud folder.")}</p>
      <button
        className={styles.retryButton}
        disabled={loading}
        onClick={onRetry}
        type="button"
      >
        <RefreshCw size={16} />
        {loading ? t("Loading") : t("Try again")}
      </button>
    </div>
  );
}

function LoadingState() {
  useLanguage((state) => state.language);
  return <div className={styles.state}>{t("Loading files...")}</div>;
}

function ErrorState({ message }: { message: string }) {
  useLanguage((state) => state.language);
  return <div className={styles.state}>{message}</div>;
}

function MarkdownViewer({ content }: { content: string }) {
  useLanguage((state) => state.language);
  return (
    <article className={styles.markdownViewer}>{renderMarkdown(content)}</article>
  );
}

function renderMarkdown(content: string) {
  const lines = markdownLines(content);
  const blocks: ReactNode[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();

    if (!trimmed) {
      index += 1;
      continue;
    }

    if (/^#{1,6}\s*$/.test(trimmed)) {
      index += 1;
      continue;
    }

    if (/^<details\b/i.test(trimmed)) {
      const details = renderDetailsBlock(lines, index);
      blocks.push(details.node);
      index = details.nextIndex;
      continue;
    }

    if (trimmed.startsWith("```")) {
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        codeLines.push(lines[index]);
        index += 1;
      }
      index += index < lines.length ? 1 : 0;
      blocks.push(
        <pre className={styles.markdownCode} key={`code-${index}`}>
          <code>{codeLines.join("\n")}</code>
        </pre>
      );
      continue;
    }

    const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      blocks.push(renderHeading(heading[1].length, heading[2], index));
      index += 1;
      continue;
    }

    if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      blocks.push(<hr key={`hr-${index}`} />);
      index += 1;
      continue;
    }

    if (trimmed.startsWith(">")) {
      const quoteLines: string[] = [];
      while (index < lines.length && lines[index].trim().startsWith(">")) {
        quoteLines.push(lines[index].trim().replace(/^>\s?/, ""));
        index += 1;
      }
      blocks.push(
        <blockquote key={`quote-${index}`}>
          <p>{renderInline(quoteLines.join(" "))}</p>
        </blockquote>
      );
      continue;
    }

    const listMatch = trimmed.match(/^((?:[-*+])|\d+[.)])\s+(.+)$/);
    if (listMatch) {
      const ordered = /^\d/.test(listMatch[1]);
      const items: string[] = [];
      while (index < lines.length) {
        const match = lines[index].trim().match(/^((?:[-*+])|\d+[.)])\s+(.+)$/);
        if (!match || /^\d/.test(match[1]) !== ordered) {
          break;
        }
        items.push(match[2]);
        index += 1;
      }
      const children = items.map((item, itemIndex) => (
        <li key={`${index}-${itemIndex}`}>{renderInline(item)}</li>
      ));
      blocks.push(
        ordered ? (
          <ol key={`list-${index}`}>{children}</ol>
        ) : (
          <ul key={`list-${index}`}>{children}</ul>
        )
      );
      continue;
    }

    const paragraphLines = [trimmed];
    index += 1;
    while (index < lines.length && !isMarkdownBlockStart(lines[index])) {
      paragraphLines.push(lines[index].trim());
      index += 1;
    }
    blocks.push(
      <p key={`p-${index}`}>{renderInline(paragraphLines.join(" "))}</p>
    );
  }

  return blocks;
}

function markdownLines(content: string) {
  return content
    .replace(/\r\n?/g, "\n")
    .replace(/<\/details>\s*<details\b/gi, "</details>\n<details")
    .replace(
      /<details\b([^>]*)>\s*<summary>(.*?)<\/summary>\s*/gi,
      "<details$1>\n<summary>$2</summary>\n"
    )
    .replace(/\s*<\/details>/gi, "\n</details>")
    .split("\n");
}

function renderDetailsBlock(lines: string[], startIndex: number) {
  const openingLine = lines[startIndex].trim();
  const open = /\sopen(?:\s|>|$)/i.test(openingLine);
  let index = startIndex + 1;
  let summary = t("Details");

  const summaryMatch = lines[index]
    ?.trim()
    .match(/^<summary>(.*?)<\/summary>$/i);
  if (summaryMatch) {
    summary = summaryMatch[1].trim() || summary;
    index += 1;
  }

  const bodyLines: string[] = [];
  while (index < lines.length && !/^<\/details>$/i.test(lines[index].trim())) {
    bodyLines.push(lines[index]);
    index += 1;
  }

  if (index < lines.length) {
    index += 1;
  }

  return {
    nextIndex: index,
    node: (
      <details className={styles.markdownDetails} key={`details-${startIndex}`} open={open}>
        <summary>{renderInline(summary)}</summary>
        <div>{renderMarkdown(bodyLines.join("\n"))}</div>
      </details>
    )
  };
}

function renderHeading(level: number, text: string, key: number) {
  const content = renderInline(text);
  if (level === 1) {
    return <h1 key={`h-${key}`}>{content}</h1>;
  }
  if (level === 2) {
    return <h2 key={`h-${key}`}>{content}</h2>;
  }
  if (level === 3) {
    return <h3 key={`h-${key}`}>{content}</h3>;
  }
  if (level === 4) {
    return <h4 key={`h-${key}`}>{content}</h4>;
  }
  if (level === 5) {
    return <h5 key={`h-${key}`}>{content}</h5>;
  }
  return <h6 key={`h-${key}`}>{content}</h6>;
}

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let cursor = 0;

  while (cursor < text.length) {
    const next = nextInlineToken(text, cursor);
    if (!next) {
      nodes.push(text.slice(cursor));
      break;
    }

    if (next.start > cursor) {
      nodes.push(text.slice(cursor, next.start));
    }

    nodes.push(next.node);
    cursor = next.end;
  }

  return nodes;
}

function nextInlineToken(
  text: string,
  cursor: number
): { start: number; end: number; node: ReactNode } | null {
  const candidates = [
    inlineCodeToken(text, cursor),
    inlineLinkToken(text, cursor),
    inlineAutoLinkToken(text, cursor),
    inlineWrappedToken(text, cursor, "**", "strong"),
    inlineWrappedToken(text, cursor, "__", "strong"),
    inlineWrappedToken(text, cursor, "*", "em"),
    inlineWrappedToken(text, cursor, "_", "em")
  ].filter(Boolean) as Array<{ start: number; end: number; node: ReactNode }>;

  return candidates.sort((a, b) => a.start - b.start)[0] ?? null;
}

function inlineCodeToken(text: string, cursor: number) {
  const start = text.indexOf("`", cursor);
  if (start === -1) {
    return null;
  }
  const endMarker = text.indexOf("`", start + 1);
  if (endMarker === -1) {
    return null;
  }
  return {
    start,
    end: endMarker + 1,
    node: <code key={`code-${start}`}>{text.slice(start + 1, endMarker)}</code>
  };
}

function inlineAutoLinkToken(text: string, cursor: number) {
  const start = text.indexOf("<", cursor);
  if (start === -1) {
    return null;
  }
  const match = text.slice(start).match(/^<(https?:\/\/[^>\s]+|mailto:[^>\s]+)>/i);
  const href = match ? safeMarkdownHref(match[1]) : null;
  if (!match || !href) {
    return null;
  }
  return {
    start,
    end: start + match[0].length,
    node: (
      <a href={href} key={`autolink-${start}`} rel="noreferrer" target="_blank">
        {match[1]}
      </a>
    )
  };
}

function inlineLinkToken(text: string, cursor: number) {
  const start = text.indexOf("[", cursor);
  if (start === -1) {
    return null;
  }
  const match = text.slice(start).match(/^\[([^\]]+)]\(([^)\s]+)\)/);
  const href = match ? safeMarkdownHref(match[2]) : null;
  if (!match || !href) {
    return null;
  }
  return {
    start,
    end: start + match[0].length,
    node: (
      <a href={href} key={`link-${start}`} rel="noreferrer" target="_blank">
        {match[1]}
      </a>
    )
  };
}

function inlineWrappedToken(
  text: string,
  cursor: number,
  marker: string,
  tag: "strong" | "em"
) {
  const start = text.indexOf(marker, cursor);
  if (start === -1) {
    return null;
  }
  const endMarker = text.indexOf(marker, start + marker.length);
  if (endMarker === -1 || endMarker === start + marker.length) {
    return null;
  }
  const content = renderInline(text.slice(start + marker.length, endMarker));
  return {
    start,
    end: endMarker + marker.length,
    node:
      tag === "strong" ? (
        <strong key={`strong-${start}`}>{content}</strong>
      ) : (
        <em key={`em-${start}`}>{content}</em>
      )
  };
}

function safeMarkdownHref(value: string) {
  try {
    const url = new URL(value);
    return ["http:", "https:", "mailto:"].includes(url.protocol) ? value : null;
  } catch {
    return null;
  }
}

function isMarkdownBlockStart(line: string) {
  const trimmed = line.trim();
  return (
    !trimmed ||
    trimmed.startsWith("```") ||
    trimmed.startsWith(">") ||
    /^<details\b/i.test(trimmed) ||
    /^<\/details>$/i.test(trimmed) ||
    /^(#{1,6})\s+/.test(trimmed) ||
    /^((?:[-*+])|\d+[.)])\s+/.test(trimmed) ||
    /^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)
  );
}

function EmptyState() {
  useLanguage((state) => state.language);
  return <div className={styles.state}>{t("This folder is empty.")}</div>;
}

function iconForFile(item: NextcloudFileItem, size = 19) {
  if (item.isDirectory) {
    return <Folder size={size} />;
  }

  if (isImagePreviewable(item)) {
    return <ImageIcon size={size} />;
  }

  return isTextPreviewable(item) ? <FileText size={size} /> : <File size={size} />;
}

function itemSubtitle(item: NextcloudFileItem) {
  if (item.isDirectory) {
    return formatModified(item.lastModified);
  }

  return `${item.contentType ?? t("File")} · ${formatModified(item.lastModified)}`;
}

export function fileTypeLabel(item: NextcloudFileItem) {
  if (item.isDirectory) {
    return t("Folder");
  }

  const extension = extensionFor(item);
  const labels: Record<string, string> = {
    csv: "CSV",
    docx: t("Word document"),
    gif: t("GIF image"),
    jpeg: t("JPEG image"),
    jpg: t("JPEG image"),
    json: "JSON",
    md: "Markdown",
    markdown: "Markdown",
    pdf: "PDF",
    png: t("PNG image"),
    pptx: t("Presentation"),
    txt: t("Text document"),
    webp: t("WebP image"),
    xlsx: t("Spreadsheet")
  };

  if (labels[extension]) {
    return labels[extension];
  }
  if (extension) {
    return extension.toLocaleUpperCase();
  }
  return item.contentType?.split(";", 1)[0] ?? t("File");
}

export function sortItems(items: NextcloudFileItem[]) {
  return [...items].sort((a, b) => {
    if (a.isDirectory !== b.isDirectory) {
      return a.isDirectory ? -1 : 1;
    }

    return a.name.localeCompare(b.name);
  });
}

export function pathParts(path: string) {
  if (!path) {
    return [];
  }

  const parts = path.split("/");
  return parts.map((name, index) => ({
    name,
    path: parts.slice(0, index + 1).join("/")
  }));
}

function parentPath(path: string) {
  return path.split("/").slice(0, -1).join("/");
}

export function formatSize(size: number | null) {
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
    return t("Modified time unknown");
  }

  return new Intl.DateTimeFormat(locale(), {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

function errorMessage(error: unknown) {
  if (typeof error === "object" && error && "message" in error) {
    return String((error as { message?: unknown }).message ?? "");
  }
  return "";
}

function extensionFor(item: NextcloudFileItem) {
  const name = item.name.toLowerCase();
  return name.includes(".") ? name.split(".").pop() ?? "" : "";
}

function isMarkdownPreview(preview: NextcloudPreviewResponse) {
  const contentType = preview.contentType.toLowerCase().split(";", 1)[0] ?? "";
  const filename = preview.filename.toLowerCase();
  const extension = filename.includes(".") ? filename.split(".").pop() ?? "" : "";

  return contentType === "text/markdown" || ["md", "markdown"].includes(extension);
}

function isViewable(item: NextcloudFileItem) {
  return (
    !item.isDirectory &&
    (isPdfPreviewable(item) ||
      isImagePreviewable(item) ||
      isTextPreviewable(item) ||
      isOfficePreviewable(item))
  );
}

function isPdfPreviewable(item: NextcloudFileItem) {
  return (
    item.contentType?.toLowerCase().split(";", 1)[0] === "application/pdf" ||
    extensionFor(item) === "pdf"
  );
}

function isImagePreviewable(item: NextcloudFileItem) {
  const contentType = item.contentType?.toLowerCase().split(";", 1)[0] ?? "";
  return (
    ["image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"].includes(
      contentType
    ) ||
    ["png", "jpg", "jpeg", "gif", "webp", "bmp"].includes(extensionFor(item))
  );
}

function isOfficePreviewable(item: NextcloudFileItem) {
  const contentType = item.contentType?.toLowerCase().split(";", 1)[0] ?? "";
  return (
    [
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "application/vnd.openxmlformats-officedocument.presentationml.presentation",
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ].includes(contentType) || ["docx", "pptx", "xlsx"].includes(extensionFor(item))
  );
}

function isTextPreviewable(item: NextcloudFileItem) {
  const contentType = item.contentType?.toLowerCase() ?? "";
  const extension = extensionFor(item);
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
