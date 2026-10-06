import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Folder, LoaderCircle, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useAccount } from "../accounts/accountContext";
import { fileStorageClient, type StorageEntry, type StorageLimits } from "../../shared/api/fileStorageClient";
import { locale, t } from "../../shared/i18n";
import { storageSize, uploadProblem, validStorageName } from "./helpers";
import styles from "./FileStoragePage.module.css";

export type DialogKind = "folder" | "rename" | "move" | "copy" | "trash" | "restore" | "purge" | "upload" | "details";
export interface StorageDialogState { kind: DialogKind; items: StorageEntry[]; files?: File[]; paths?: string[]; directories?: string[]; initialValues?: DialogValues }
export interface DialogValues { name: string; parent: string | null; original: boolean; files: File[]; paths?: string[]; directories: string[] }
const titles: Record<DialogKind, string> = {
  folder: "New folder", rename: "Rename", move: "Move to", copy: "Copy to", trash: "Move to trash",
  restore: "Restore", purge: "Delete permanently", upload: "Upload files", details: "File details"
};
export function Modal({ title, busy, close, children }: { title: string; busy: boolean; close: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { ref.current?.showModal(); }, []);
  return <dialog ref={ref} className={styles.dialog} aria-labelledby="storage-dialog-title"
    onCancel={event => { event.preventDefault(); if (!busy) close(); }}>
    <header className={styles.dialogHeader}><h2 id="storage-dialog-title">{title}</h2>
      <button type="button" className={styles.iconButton} disabled={busy} onClick={close} aria-label={t("Close")}><X size={18} /></button></header>
    {children}
  </dialog>;
}

export function FolderPicker({ value, onChange, blocked, onReady }: {
  value: string | null; onChange: (id: string | null) => void; blocked: string[]; onReady: (ready: boolean) => void;
}) {
  const account = useAccount();
  const [offset, setOffset] = useState(0);
  const listing = useQuery({ queryKey: ["file-storage", account.id, "picker", value, offset],
    queryFn: ({ signal }) => fileStorageClient.list({ parent: value, offset, limit: 50 }, signal), retry: false });
  const location = useQuery({ queryKey: ["file-storage", account.id, "detail", value],
    queryFn: ({ signal }) => fileStorageClient.detail(value!, signal), enabled: Boolean(value), retry: false });
  const blockedLocation = Boolean(value && (blocked.includes(value) || location.data?.breadcrumbs.some(item => blocked.includes(item.id))));
  const ready = listing.isSuccess && (!value || location.isSuccess) && !blockedLocation;
  useEffect(() => { onReady(ready); }, [ready, onReady, value]);
  function open(id: string | null) { setOffset(0); onChange(id); }
  const folders = listing.data?.items.filter(item => item.kind === "folder") ?? [];
  const hasNext = listing.data && listing.data.total > offset + 50 && listing.data.items.every(item => item.kind === "folder");
  return <div className={styles.picker}>
    <nav className={styles.breadcrumbs} aria-label={t("Destination folder")}>
      <button type="button" onClick={() => open(null)}>{t("My files")}</button>
      {location.data && [...location.data.breadcrumbs, location.data].map(item => <span key={item.id}>
        <ChevronRight size={14} aria-hidden /><button type="button" onClick={() => open(item.id)}>{item.name}</button>
      </span>)}
    </nav>
    {listing.isPending ? <p role="status">{t("Loading folders…")}</p> : listing.isError || location.isError ?
      <p role="alert">{t("Folders could not be loaded.")} <button type="button" onClick={() => { void listing.refetch(); if (value) void location.refetch(); }}>{t("Try again")}</button></p> :
      <div className={styles.pickerFolders}>
        {!folders.length && <p>{t("No subfolders here. You can use this folder.")}</p>}
        {folders.map(folder => <button type="button" key={folder.id} disabled={blocked.includes(folder.id)}
          title={blocked.includes(folder.id) ? t("Choose a folder outside the items you selected.") : folder.name}
          onClick={() => open(folder.id)}><Folder size={18} aria-hidden /><span>{folder.name}</span><ChevronRight size={15} aria-hidden /></button>)}
      </div>}
    {(offset > 0 || hasNext) && <div className={styles.pager}>
      <button type="button" disabled={offset === 0 || listing.isFetching} onClick={() => setOffset(value => value - 50)}>{t("Previous")}</button>
      <button type="button" disabled={!hasNext || listing.isFetching} onClick={() => setOffset(value => value + 50)}>{t("Next")}</button>
    </div>}
    <p className={styles.hint}>{t("Selected folder:")} <strong>{location.data?.name ?? (value ? t("Loading…") : t("My files"))}</strong></p>
  </div>;
}

export function StorageDialog({ state, busy, error, notice, limits, close, submit, download, openParent }: {
  state: StorageDialogState; busy: boolean; error: string; notice: string; limits?: StorageLimits;
  close: () => void; submit: (values: DialogValues) => void;
  download: (item: StorageEntry) => void; openParent: (id: string | null) => void;
}) {
  const account = useAccount();
  const single = state.items.length === 1 ? state.items[0] : undefined;
  const [name, setName] = useState(state.initialValues ? state.initialValues.name || single?.name || "" : state.kind === "copy" && single ? t("Copy of {name}", { name: single.name }) : single?.name ?? "");
  const [parent, setParent] = useState<string | null>(state.initialValues?.parent ?? null);
  const [destinationReady, setDestinationReady] = useState(false);
  const [original, setOriginal] = useState(state.initialValues?.original ?? true);
  const [uploads, setUploads] = useState((state.files ?? []).map((file, index) => ({ file, path: state.paths?.[index] ?? file.name })));
  const files = uploads.map(upload => upload.file);
  const paths = state.paths ? uploads.map(upload => upload.path) : undefined;
  const directories = state.directories ?? [];
  const detail = useQuery({ queryKey: ["file-storage", account.id, "detail", single?.id],
    queryFn: ({ signal }) => fileStorageClient.detail(single!.id, signal), enabled: state.kind === "details" && Boolean(single), retry: false });
  const showName = state.kind === "folder" || (Boolean(single) && ["rename", "move", "copy", "restore"].includes(state.kind));
  const choosingFolder = ["move", "copy"].includes(state.kind) || (state.kind === "restore" && !original);
  const uploadError = state.kind === "upload" && limits ? uploadProblem(files, limits, paths, directories) : null;
  const invalid = (choosingFolder && !destinationReady) || (showName && !validStorageName(name)) || (state.kind === "upload" && (!limits || Boolean(uploadError)));
  const destructive = state.kind === "purge" || state.kind === "trash";
  return <Modal title={t(titles[state.kind])} busy={busy} close={close}>
    {state.kind === "details" ? <div className={styles.dialogBody}>
      {detail.isPending ? <p role="status">{t("Loading…")}</p> : detail.isError ?
        <p role="alert">{t("This item or folder is no longer available. Choose another location.")}</p> : <>
          <strong className={styles.detailName}>{detail.data.name}</strong>
          <dl className={styles.metadata}>
            <dt>{t("Type")}</dt><dd>{detail.data.kind === "folder" ? t("Folder") : detail.data.content_type ?? t("File")}</dd>
            {detail.data.kind === "file" && <><dt>{t("Size")}</dt><dd>{storageSize(detail.data.size)}</dd></>}
            <dt>{t("Location")}</dt><dd>{[t("My files"), ...detail.data.breadcrumbs.map(item => item.name)].join(" / ")}</dd>
            <dt>{t("Created")}</dt><dd>{new Date(detail.data.created_at).toLocaleString(locale())}</dd>
            <dt>{t("Modified")}</dt><dd>{new Date(detail.data.updated_at).toLocaleString(locale())}</dd>
          </dl>
          {error && <p role="alert" className={styles.error}>{t(error)}</p>}
          <div className={styles.dialogActions}>
            <button type="button" disabled={busy} onClick={() => openParent(detail.data.parent_id)}>{t("Open containing folder")}</button>
            {single?.kind === "file" && <button type="button" className={styles.primary} disabled={busy} onClick={() => download(single)}>{busy ? t("Downloading…") : t("Download")}</button>}
          </div>
        </>}
    </div> : <form className={styles.dialogBody} onSubmit={event => {
      event.preventDefault(); if (!busy && !invalid) submit({ name: name.normalize("NFC").trim(), parent, original, files, paths, directories });
    }}>
      {destructive && <p>{state.kind === "purge" ? t("Permanently delete {count} selected item(s)? This cannot be undone.", { count: state.items.length }) :
        t("Move {count} selected item(s) to trash? You can restore them later.", { count: state.items.length })}</p>}
      {state.items.length > 0 && <ul className={styles.itemSummary}>{state.items.slice(0, 4).map(item => <li key={item.id}>{item.name}</li>)}
        {state.items.length > 4 && <li>{t("And {count} more", { count: state.items.length - 4 })}</li>}</ul>}
      <fieldset disabled={busy} className={styles.fields}>
        {showName && <label>{t("Name")}<input autoFocus value={name} onChange={event => setName(event.target.value)} required maxLength={255} />
          {name && !validStorageName(name) && <small className={styles.error}>{t("Use a name without slashes or control characters, up to 255 UTF-8 bytes.")}</small>}</label>}
        {state.kind === "restore" && <label className={styles.checkLabel}><input type="checkbox" checked={!original} onChange={event => setOriginal(!event.target.checked)} />{t("Restore to a different folder")}</label>}
        {choosingFolder && <><span className={styles.fieldTitle}>{t("Destination folder")}</span>
          <FolderPicker value={parent} onChange={id => { if (id !== parent) { setDestinationReady(false); setParent(id); } }} onReady={setDestinationReady} blocked={state.items.filter(item => item.kind === "folder").map(item => item.id)} /></>}
        {state.kind === "restore" && original && <p className={styles.hint}>{t("Items return to their original folders. Choose a different folder if that location is unavailable.")}</p>}
        {state.kind === "upload" && <>
          {paths && <p className={styles.hint}>{t("Folder structure will be preserved. Existing folders are kept separately with numbered names.")}</p>}
          {directories.length > 0 && <p className={styles.hint}>{t("{count} folders included (including empty folders).", { count: directories.length })}</p>}
          {directories.length > 0 && <ul className={styles.itemSummary}>{directories.slice(0, 4).map(path => <li key={path}>{path}/</li>)}
            {directories.length > 4 && <li>{t("And {count} more", { count: directories.length - 4 })}</li>}</ul>}
          <ul className={styles.uploadList}>{files.map((file, index) => <li key={`${index}-${file.name}`}>
            <span>{paths?.[index] ?? file.name}<small>{storageSize(file.size)}</small></span>
            <button type="button" className={styles.iconButton} aria-label={t("Remove {name}", { name: file.name })} onClick={() => setUploads(values => values.filter((_, i) => i !== index))}><X size={16} /></button>
          </li>)}</ul>
          {limits && <p className={styles.hint}>{t("Up to {count} files · {fileSize} per file · {totalSize} per upload", {
            count: limits.max_files, fileSize: storageSize(limits.max_file_bytes), totalSize: storageSize(limits.max_batch_bytes)
          })}</p>}
          {uploadError && <p role="alert" className={styles.error}>{t(uploadError)}</p>}
        </>}
        {(showName || choosingFolder || state.kind === "upload" || state.kind === "restore") && <p className={styles.hint}>{t("Duplicate names get a number automatically, for example file(1).pdf. Existing files are never overwritten.")}</p>}
      </fieldset>
      {notice && <p role="status" className={styles.notice}>{notice}</p>}
      {error && <p role="alert" className={styles.error}>{t(error)}</p>}
      <div className={styles.dialogActions}>
        <button type="button" disabled={busy} autoFocus={destructive} onClick={close}>{t("Cancel")}</button>
        <button type="submit" disabled={busy || invalid} className={destructive ? styles.danger : styles.primary}>
          {busy && <LoaderCircle className={styles.spinner} size={16} aria-hidden />}{busy ? t("Working…") : t(titles[state.kind])}
        </button>
      </div>
    </form>}
  </Modal>;
}
