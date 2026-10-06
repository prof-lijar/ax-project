import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Download, FileWarning, Info, LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { useAccount } from "../accounts/accountContext";
import { PreviewSurface } from "../nextcloud/NextcloudPage";
import { fileStorageClient, StorageError, type StorageEntry } from "../../shared/api/fileStorageClient";
import { t, useLanguage } from "../../shared/i18n";
import type { NextcloudPreviewResponse } from "../../shared/types/nextcloud";
import { storageSize } from "./helpers";
import styles from "./FileStoragePage.module.css";

export function FileStorageViewer({ item, busy, error, back, details, download }: {
  item: StorageEntry; busy: boolean; error: string;
  back: () => void; details: () => void; download: () => void;
}) {
  useLanguage(state => state.language);
  const account = useAccount();
  const preview = useQuery({ queryKey: ["file-storage", account.id, "preview", item.id, item.name, item.updated_at],
    queryFn: ({ signal }) => fileStorageClient.preview(item, signal), retry: false,
    gcTime: 0, staleTime: 0, refetchOnWindowFocus: false });
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!preview.data || preview.data.kind === "text") { setObjectUrl(null); return; }
    const url = URL.createObjectURL(preview.data.blob);
    setObjectUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [preview.data]);
  const rendered: NextcloudPreviewResponse | undefined = preview.data ? {
    path: item.id, filename: preview.data.filename, contentType: preview.data.contentType,
    viewerKind: preview.data.kind,
    ...(preview.data.kind === "text" ? { text: preview.data.text } : { objectUrl: objectUrl ?? undefined })
  } : undefined;
  const unsupported = preview.error instanceof StorageError && preview.error.code === "preview_unsupported";
  return <section className={`${styles.page} ${styles.previewPage}`} aria-label={t("Viewer for {0}", { 0: item.name })}>
    <header className={styles.previewHeader}>
      <button disabled={busy} onClick={back}><ArrowLeft size={16} aria-hidden />{t("Back to files")}</button>
      <div className={styles.previewTitle}><h1 title={item.name}>{item.name}</h1><p>{storageSize(item.size)} · {t("Read-only preview")}</p></div>
      <div className={styles.headerActions}>
        <button disabled={busy} onClick={details}><Info size={16} aria-hidden />{t("File details")}</button>
        <button className={styles.primary} disabled={busy} onClick={download}><Download size={16} aria-hidden />{t(busy ? "Downloading…" : "Download")}</button>
      </div>
    </header>
    {error && <p role="alert" className={styles.error}>{t(error)}</p>}
    <div className={styles.previewBody} aria-busy={preview.isFetching}>
      {preview.isPending ? <div className={styles.empty} role="status"><LoaderCircle className={styles.spinner} size={26} aria-hidden />
        <p>{t("Preparing preview… Office files may take a moment.")}</p></div> : preview.isError ?
        <div className={styles.empty} role="alert"><FileWarning size={32} aria-hidden /><h2>{t("Preview unavailable")}</h2>
          <p>{t(preview.error instanceof StorageError ? preview.error.message : "The preview could not be opened. Try again or download the original file.")}</p>
          {!unsupported && <button disabled={preview.isFetching} onClick={() => void preview.refetch()}>{t("Try again")}</button>}
        </div> : rendered && (rendered.viewerKind === "text" || objectUrl) ? <PreviewSurface preview={rendered} /> : null}
    </div>
  </section>;
}
