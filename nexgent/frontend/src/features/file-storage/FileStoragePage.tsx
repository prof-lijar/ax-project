import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, ChevronRight, Copy, Download, Ellipsis, Eye, File, FileText, Folder, FolderInput, FolderPlus, HardDrive, Image, Info, LoaderCircle, RefreshCw, Search, Trash2, Undo2, Upload, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useAccount } from "../accounts/accountContext";
import { fileStorageClient, saveStorageDownload, type StorageEntry } from "../../shared/api/fileStorageClient";
import { locale, t, useLanguage } from "../../shared/i18n";
import { getStorageLocation, navigateToStorage } from "../../shared/navigation/sections";
import { useUiStore } from "../../shared/state/useUiStore";
import { droppedFiles, pickedFolder } from "./folderUpload";
import { storageSize } from "./helpers";
import { FileStorageViewer } from "./FileStorageViewer";
import { StorageDialog, type DialogKind, type DialogValues, type StorageDialogState } from "./StorageDialog";
import styles from "./FileStoragePage.module.css";

const PAGE_SIZE = 50;
const errorMessage = (error: unknown) => error instanceof Error ? error.message : "The request could not be completed. Refresh your files before trying again.";

export function FileStoragePage() {
  useLanguage(state => state.language);
  const account = useAccount();
  const activePath = useUiStore(state => state.activePath);
  const { parent, trash } = getStorageLocation(activePath);
  const cache = useQueryClient();
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string[]>([]);
  const [dialog, setDialog] = useState<StorageDialogState | null>(null);
  const [viewer, setViewer] = useState<StorageEntry | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState<{ message: string; values?: Record<string, string | number> } | null>(null);
  const [dragging, setDragging] = useState(false);
  const picker = useRef<HTMLInputElement>(null);
  const folderPicker = useRef<HTMLInputElement | null>(null);
  const currentPath = useRef(activePath); currentPath.current = activePath;
  const operation = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const dragDepth = useRef(0);
  const queryPrefix = ["file-storage", account.id];
  const limits = useQuery({ queryKey: [...queryPrefix, "limits"], queryFn: ({ signal }) => fileStorageClient.limits(signal), retry: false });
  const folder = useQuery({ queryKey: [...queryPrefix, "detail", parent], enabled: Boolean(parent) && !trash,
    queryFn: ({ signal }) => fileStorageClient.detail(parent!, signal), retry: false, staleTime: 0, refetchOnWindowFocus: true });
  const listing = useQuery({ queryKey: [...queryPrefix, "list", parent, trash, query, offset],
    queryFn: ({ signal }) => fileStorageClient.list({ parent, trash, q: query || undefined, offset, limit: PAGE_SIZE }, signal),
    enabled: !parent || trash || folder.isSuccess, retry: false, staleTime: 0, refetchOnWindowFocus: true });
  const items = listing.data?.items ?? [];
  const chosen = items.filter(item => selected.includes(item.id));
  const canUpload = !trash && !query && !busy && Boolean(limits.data) && !folder.isError;
  const crumbs = folder.data ? [...folder.data.breadcrumbs, folder.data] : [];
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; operation.current?.abort(); }; }, []);
  useEffect(() => { setSearch(""); setQuery(""); setOffset(0); setSelected([]); setDialog(null); setViewer(null); setError(""); setNotice(null); }, [activePath]);
  useEffect(() => { setSelected([]); }, [query, offset]);
  useEffect(() => {
    if (listing.data && listing.data.total <= offset && offset > 0) setOffset(Math.max(0, Math.ceil(listing.data.total / PAGE_SIZE) * PAGE_SIZE - PAGE_SIZE));
  }, [listing.data, offset]);

  function open(kind: DialogKind, targets: StorageEntry[] = []) {
    if (operation.current) return;
    setError(""); setNotice(null); setDialog({ kind, items: targets });
  }
  function stageUpload(files: File[], paths?: string[], directories: string[] = []) {
    if (!canUpload || (!files.length && !directories.length)) return;
    setError(""); setNotice(null); setDialog({ kind: "upload", items: [], files, paths, directories });
  }
  async function refresh() { await cache.invalidateQueries({ queryKey: queryPrefix }); }
  async function download(item: StorageEntry) {
    if (operation.current) return;
    const controller = new AbortController(); operation.current = controller;
    setBusy(true); setError(""); setNotice(null);
    try {
      const result = await fileStorageClient.download(item, controller.signal);
      if (mounted.current) { saveStorageDownload(result.blob, result.name); setNotice({ message: "Download started." }); }
    } catch (cause) { if (mounted.current) setError(errorMessage(cause)); }
    finally { operation.current = null; if (mounted.current) setBusy(false); }
  }
  async function submit(values: DialogValues) {
    if (!dialog || operation.current) return;
    const current = dialog;
    const controller = new AbortController(); operation.current = controller;
    setBusy(true); setError(""); setNotice(null);
    let completed = 0;
    try {
      if (current.kind === "folder") await fileStorageClient.folder(values.name, parent, controller.signal);
      else if (current.kind === "upload") {
        if (values.paths) await fileStorageClient.uploadTree(values.files, values.paths, values.directories, parent, controller.signal);
        else await fileStorageClient.upload(values.files, parent, controller.signal);
      }
      else {
        for (const item of current.items) {
          const destination = { ...(current.kind === "restore" && values.original ? {} : { parent_id: values.parent }),
            ...(current.items.length === 1 ? { name: values.name } : {}) };
          switch (current.kind) {
            case "rename": await fileStorageClient.rename(item.id, values.name, controller.signal); break;
            case "move": await fileStorageClient.move(item.id, destination, controller.signal); break;
            case "copy": await fileStorageClient.copy(item.id, destination, controller.signal); break;
            case "trash": await fileStorageClient.trash(item.id, controller.signal); break;
            case "restore": await fileStorageClient.restore(item.id, destination, controller.signal); break;
            case "purge": await fileStorageClient.purge(item.id, controller.signal); break;
          }
          completed += 1;
        }
      }
      if (mounted.current) {
        setDialog(null); setSelected([]);
        setNotice({ message: current.kind === "upload" ? "Files uploaded." : current.kind === "trash" ? "Moved to trash." : current.kind === "restore" ? "Items restored." : current.kind === "purge" ? "Items permanently deleted." : "Changes saved." });
      }
    } catch (cause) {
      if (mounted.current) {
        setError(errorMessage(cause));
        if (completed > 0) {
          const remaining = current.items.slice(completed);
          setDialog({ ...current, items: remaining, initialValues: values }); setSelected(remaining.map(item => item.id));
          setNotice({ message: "{count} completed. Only the remaining items will be retried.", values: { count: completed } });
        }
      }
    } finally {
      // An upstream timeout can happen after commit; always refresh before retry.
      operation.current = null;
      if (mounted.current) { setBusy(false); void refresh(); }
    }
  }

  const dialogElement = dialog && <StorageDialog key={dialog.kind + dialog.items.map(item => item.id).join("|")} state={dialog} busy={busy} error={error} notice={notice ? t(notice.message, notice.values) : ""} limits={limits.data}
      close={() => { if (!busy) { setDialog(null); setError(""); } }} submit={values => void submit(values)} download={item => void download(item)}
      openParent={id => { setDialog(null); setViewer(null); setSearch(""); setQuery(""); setOffset(0); navigateToStorage(id); }} />;
  if (viewer) return <><FileStorageViewer key={viewer.id} item={viewer} busy={busy} error={error}
    back={() => { setViewer(null); setError(""); }} details={() => open("details", [viewer])}
    download={() => void download(viewer)} />{dialogElement}</>;

  const failed = listing.isError || folder.isError;
  const loading = listing.isPending || (Boolean(parent) && folder.isPending);
  const allSelected = items.length > 0 && chosen.length === items.length;
  return <section className={`${styles.page} ${dragging ? styles.dragging : ""}`} aria-labelledby="storage-title"
    onDragEnter={event => { if (event.dataTransfer.types.includes("Files")) { event.preventDefault(); dragDepth.current += 1; if (canUpload) setDragging(true); } }}
    onDragOver={event => { if (event.dataTransfer.types.includes("Files")) { event.preventDefault(); event.dataTransfer.dropEffect = canUpload ? "copy" : "none"; } }}
    onDragLeave={event => { event.preventDefault(); dragDepth.current = Math.max(0, dragDepth.current - 1); if (!dragDepth.current) setDragging(false); }}
    onDrop={event => {
      event.preventDefault(); dragDepth.current = 0; setDragging(false);
      if (!canUpload || !limits.data || operation.current) return;
      const controller = new AbortController(); operation.current = controller;
      setBusy(true); setError(""); setNotice({ message: "Reading folder contents…" });
      void droppedFiles(event.dataTransfer, limits.data, controller.signal).then(selection => {
        if (mounted.current && currentPath.current === activePath) stageUpload(selection.files, selection.paths, selection.directories);
      }).catch(cause => {
        if (mounted.current && currentPath.current === activePath) setError(errorMessage(cause));
      }).finally(() => { operation.current = null; if (mounted.current) { setBusy(false); setNotice(null); } });
    }}>
    <header className={styles.header}>
      <div><h1 id="storage-title"><HardDrive size={24} aria-hidden />{t("File Storage")}</h1><p>{t("Private files and folders, in one place.")}</p></div>
      <div className={styles.headerActions}>
        <button disabled={busy || trash || Boolean(query) || folder.isError} onClick={() => open("folder")}><FolderPlus size={16} aria-hidden />{t("New folder")}</button>
        <button disabled={!canUpload} onClick={() => folderPicker.current?.click()}><FolderInput size={16} aria-hidden />{t("Upload folder")}</button>
        <button className={styles.primary} disabled={!canUpload} onClick={() => picker.current?.click()}><Upload size={16} aria-hidden />{t("Upload files")}</button>
        <input ref={node => { folderPicker.current = node; node?.setAttribute("webkitdirectory", ""); }} className={styles.srOnly} type="file" multiple
          aria-label={t("Choose folder to upload")} tabIndex={-1} onChange={event => {
            const selected = pickedFolder(Array.from(event.target.files ?? []));
            if (!selected.files.length) setError("The selected folder contains no files. Drag it here to include empty folders.");
            else stageUpload(selected.files, selected.paths, selected.directories);
            event.target.value = "";
          }} />
        <input ref={picker} className={styles.srOnly} type="file" multiple aria-label={t("Choose files to upload")} tabIndex={-1}
          onChange={event => { stageUpload(Array.from(event.target.files ?? [])); event.target.value = ""; }} />
      </div>
    </header>
    <div className={styles.tools}>
      <nav className={styles.sections} aria-label={t("File storage views")}>
        <button disabled={busy} aria-current={!trash ? "page" : undefined} onClick={() => navigateToStorage(null)}><Folder size={16} aria-hidden />{t("My files")}</button>
        <button disabled={busy} aria-current={trash ? "page" : undefined} onClick={() => navigateToStorage(null, true)}><Trash2 size={16} aria-hidden />{t("Trash")}</button>
      </nav>
      {!trash && <form role="search" className={styles.search} onSubmit={event => { event.preventDefault(); setOffset(0); setQuery(search.trim()); }}>
        <Search size={16} aria-hidden /><input aria-label={t("Search all files")} placeholder={t("Search all files")} maxLength={255} value={search} disabled={busy} onChange={event => {
          setSearch(event.target.value); if (!event.target.value) { setQuery(""); setOffset(0); }
        }} />
        {search && <button type="button" className={styles.iconButton} aria-label={t("Clear search")} onClick={() => { setSearch(""); setQuery(""); setOffset(0); }}><X size={15} /></button>}
        <button type="submit" disabled={busy}>{t("Search")}</button>
      </form>}
      <button className={styles.iconButton} disabled={busy || listing.isFetching} title={t("Refresh")} aria-label={t("Refresh files")} onClick={() => void refresh()}><RefreshCw size={17} className={listing.isFetching ? styles.spinner : undefined} /></button>
    </div>
    <div className={styles.location}>
      {trash ? <p>{t("Restore files you need, or delete them permanently.")}</p> : query ?
        <span>{t("Search results for “{query}”", { query })}</span> : <nav className={styles.breadcrumbs} aria-label={t("Current folder")}>
          {parent && <button className={styles.iconButton} disabled={busy || !folder.data} aria-label={t("Back one folder")} onClick={() => navigateToStorage(folder.data?.parent_id ?? null)}><ArrowLeft size={16} /></button>}
          <button disabled={busy} onClick={() => navigateToStorage(null)} aria-current={!parent ? "page" : undefined}>{t("My files")}</button>
          {crumbs.map(item => <span key={item.id}><ChevronRight size={14} aria-hidden /><button disabled={busy} aria-current={item.id === parent ? "page" : undefined} onClick={() => navigateToStorage(item.id)}>{item.name}</button></span>)}
        </nav>}
      {!loading && !failed && <span className={styles.count}>{t("{count} items", { count: listing.data?.total ?? 0 })}</span>}
    </div>
    {limits.isError && !trash && <p role="alert" className={styles.error}>{t("Upload limits could not be loaded.")} <button onClick={() => void limits.refetch()}>{t("Try again")}</button></p>}
    {notice && <p role="status" className={styles.notice}><Check size={16} aria-hidden />{t(notice.message, notice.values)}<button className={styles.iconButton} aria-label={t("Dismiss")} onClick={() => setNotice(null)}><X size={14} /></button></p>}
    {error && !dialog && <p role="alert" className={styles.error}>{t(error)}</p>}
    {chosen.length > 0 && <div className={styles.selectionBar} role="group" aria-label={t("Selected file actions")}>
      <strong>{t("{count} selected", { count: chosen.length })}</strong>
      {trash ? <>
        <button disabled={busy} onClick={() => open("restore", chosen)}><Undo2 size={15} />{t("Restore")}</button>
        <button disabled={busy} className={styles.dangerText} onClick={() => open("purge", chosen)}><Trash2 size={15} />{t("Delete permanently")}</button>
      </> : <>
        {chosen.length === 1 && chosen[0].kind === "file" && <button disabled={busy} onClick={() => void download(chosen[0])}><Download size={15} />{t("Download")}</button>}
        <button disabled={busy} onClick={() => open("move", chosen)}><FolderInput size={15} />{t("Move")}</button>
        <button disabled={busy} onClick={() => open("copy", chosen)}><Copy size={15} />{t("Copy")}</button>
        <button disabled={busy} onClick={() => open("trash", chosen)}><Trash2 size={15} />{t("Move to trash")}</button>
      </>}
      <button disabled={busy} className={styles.iconButton} aria-label={t("Clear selection")} onClick={() => setSelected([])}><X size={16} /></button>
    </div>}
    <div className={styles.workspace} aria-busy={busy || loading}>
      {failed ? <div className={styles.empty} role="alert"><HardDrive size={32} /><h2>{t("Files could not be loaded.")}</h2><p>{t(errorMessage(folder.error ?? listing.error))}</p>
        <div className={styles.headerActions}><button onClick={() => void refresh()}>{t("Try again")}</button>{parent && <button onClick={() => navigateToStorage(null)}>{t("Go to My files")}</button>}</div></div> :
        loading ? <div className={styles.empty} role="status"><LoaderCircle size={26} className={styles.spinner} /><p>{t("Loading files…")}</p></div> :
        !items.length ? <div className={styles.empty}><Folder size={40} strokeWidth={1.3} aria-hidden />
          <h2>{t(trash ? "Trash is empty" : query ? "No matching files" : "This folder is empty")}</h2>
          <p>{t(trash ? "Items you delete will appear here." : query ? "Try another name or clear your search." : "Drop files here, or create a folder to get started.")}</p>
          {!trash && !query && <button className={styles.primary} disabled={!canUpload} onClick={() => picker.current?.click()}><Upload size={16} />{t("Upload files")}</button>}
        </div> : <table className={styles.table}>
          <thead><tr><th className={styles.checkboxCell}><input type="checkbox" aria-label={t("Select all items on this page")} checked={allSelected} disabled={busy}
            ref={node => { if (node) node.indeterminate = chosen.length > 0 && !allSelected; }} onChange={event => setSelected(event.target.checked ? items.map(item => item.id) : [])} /></th>
            <th>{t("Name")}</th><th className={styles.typeColumn}>{t("Type")}</th><th className={styles.sizeColumn}>{t("Size")}</th><th className={styles.dateColumn}>{t(trash ? "Deleted" : "Modified")}</th><th><span className={styles.srOnly}>{t("Actions")}</span></th></tr></thead>
          <tbody>{items.map(item => <tr key={item.id} data-selected={selected.includes(item.id) || undefined}>
            <td className={styles.checkboxCell}><input type="checkbox" aria-label={t("Select {name}", { name: item.name })} checked={selected.includes(item.id)} disabled={busy}
              onChange={event => setSelected(values => event.target.checked ? [...values, item.id] : values.filter(id => id !== item.id))} /></td>
            <td><div className={styles.fileName}><EntryIcon item={item} />{trash ? <span title={item.name}>{item.name}</span> :
              <button disabled={busy} title={item.name} onClick={() => item.kind === "folder" ? navigateToStorage(item.id) : (setError(""), setViewer(item))}>{item.name}</button>}</div></td>
            <td className={styles.typeColumn}>{item.kind === "folder" ? t("Folder") : item.name.split(".").length > 1 ? item.name.split(".").pop()?.toUpperCase().slice(0, 10) : t("File")}</td>
            <td className={styles.sizeColumn}>{item.kind === "folder" ? "—" : storageSize(item.size)}</td>
            <td className={styles.dateColumn}>{new Intl.DateTimeFormat(locale(), { year: "numeric", month: "short", day: "numeric" }).format(new Date((trash ? item.deleted_at : item.updated_at) ?? item.updated_at))}</td>
            <td className={styles.actionCell}><EntryActions item={item} trash={trash} busy={busy} act={kind => open(kind, [item])} preview={() => { setError(""); setViewer(item); }} download={() => void download(item)} /></td>
          </tr>)}</tbody>
        </table>}
      {dragging && <div className={styles.dropOverlay}><Upload size={32} /><strong>{t("Drop files to upload")}</strong></div>}
    </div>
    {!failed && !loading && (listing.data?.total ?? 0) > 0 && <footer className={styles.footer}>
      <span>{t("{start}–{end} of {total}", { start: offset + 1, end: offset + items.length, total: listing.data?.total ?? 0 })}</span>
      <div className={styles.pager}><button disabled={busy || offset === 0} onClick={() => setOffset(value => value - PAGE_SIZE)}>{t("Previous")}</button>
        <button disabled={busy || offset + PAGE_SIZE >= (listing.data?.total ?? 0)} onClick={() => setOffset(value => value + PAGE_SIZE)}>{t("Next")}</button></div>
    </footer>}
    {dialogElement}
  </section>;
}

function EntryIcon({ item }: { item: StorageEntry }) {
  const Icon = item.kind === "folder" ? Folder : item.content_type?.startsWith("image/") ? Image : /pdf|text|document/.test(item.content_type ?? "") ? FileText : File;
  return <span className={item.kind === "folder" ? styles.folderIcon : styles.fileIcon}><Icon size={20} strokeWidth={1.7} aria-hidden /></span>;
}
function EntryActions({ item, trash, busy, act, preview, download }: {
  item: StorageEntry; trash: boolean; busy: boolean; act: (kind: DialogKind) => void; preview: () => void; download: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => { if (!ref.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") { setOpen(false); trigger.current?.focus(); } };
    document.addEventListener("pointerdown", outside); document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", escape); };
  }, [open]);
  return <div className={styles.rowActions} ref={ref} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}>
    <button ref={trigger} className={styles.iconButton} disabled={busy} aria-expanded={open} aria-label={t("Actions for {name}", { name: item.name })} onClick={() => setOpen(value => !value)}><Ellipsis size={19} /></button>
    {open && <div className={styles.actionMenu} role="group" aria-label={t("File actions")}>
      {trash ? <><button onClick={() => { setOpen(false); trigger.current?.focus(); act("restore"); }}><Undo2 size={15} />{t("Restore")}</button><button className={styles.dangerText} onClick={() => { setOpen(false); trigger.current?.focus(); act("purge"); }}><Trash2 size={15} />{t("Delete permanently")}</button></> : <>
        {item.kind === "file" && <button onClick={() => { setOpen(false); trigger.current?.focus(); preview(); }}><Eye size={15} />{t("Preview")}</button>}
        {item.kind === "file" && <button onClick={() => { setOpen(false); download(); }}><Download size={15} />{t("Download")}</button>}
        {(["rename", "move", "copy", "details", "trash"] as const).map(kind => <button key={kind} onClick={() => { setOpen(false); trigger.current?.focus(); act(kind); }}>
          {kind === "move" ? <FolderInput size={15} /> : kind === "copy" ? <Copy size={15} /> : kind === "trash" ? <Trash2 size={15} /> : <Info size={15} />}
          {t(({ rename: "Rename", move: "Move to", copy: "Copy to", details: "File details", trash: "Move to trash" })[kind])}</button>)}
      </>}
    </div>}
  </div>;
}
