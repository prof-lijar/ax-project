import { authenticatedFetch } from "./authenticatedFetch";

export interface StorageEntry {
  id: string;
  parent_id: string | null;
  name: string;
  kind: "file" | "folder";
  size: number;
  content_type: string | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}
export interface StorageDetail extends StorageEntry {
  breadcrumbs: { id: string; name: string }[];
}
export type StoragePreview = { kind: "pdf" | "image"; blob: Blob; filename: string; contentType: string } | { kind: "text"; text: string; filename: string; contentType: string };
export interface StoragePage { items: StorageEntry[]; total: number; limit: number; offset: number }
export interface StorageLimits { max_file_bytes: number; max_batch_bytes: number; max_files: number; max_upload_folders?: number; max_upload_depth?: number }
export type StorageDestination = { parent_id?: string | null; name?: string };

const messages: Record<string, string> = {
  invalid_upload_tree: "The folder could not be read or contains invalid paths. Choose it again.",
  preview_unsupported: "Preview unavailable. Download this file instead.",
  preview_converter_unavailable: "Office preview is unavailable on this server. Download the original file instead.",
  preview_timeout: "The preview took too long. Try again or download the original file.",
  preview_failed: "The preview could not be opened. Try again or download the original file.",
  name_conflict: "An item with this name already exists. Choose another name.",
  name_or_reference_conflict: "The folder changed or the name is already in use. Refresh and try again.",
  folder_cycle: "Choose a folder outside the items you selected.",
  parent_is_not_folder: "Choose a folder as the destination.",
  restore_trash_root_first: "Restore the containing folder first.",
  purge_trash_root_first: "Delete the containing trash item first.",
  folder_operation_too_large: "This folder is too large for one operation. Work with smaller subfolders.",
  invalid_filename: "Use a name without slashes or control characters, up to 255 UTF-8 bytes.",
  upload_too_large: "The selected files exceed the upload limits.",
  too_many_files: "Too many files selected. Upload a smaller batch.",
  upload_expired: "This upload expired. Refresh your files before trying again.",
  file_storage_upstream_error: "File storage could not be reached. Refresh your files before trying again.",
  file_storage_unavailable: "File storage is unavailable. Please try again later."
};
export class StorageError extends Error {
  constructor(public status: number, public code: string) {
    super(messages[code] ?? ({
      401: "Please sign in again.",
      403: "Your session changed. Refresh the page and try again.",
      404: "This item or folder is no longer available. Choose another location.",
      409: "The folder changed or the name is already in use. Refresh and try again.",
      413: "The selected files exceed the upload limits.",
      422: "Check the name and destination, then try again.",
      503: "File storage is unavailable. Please try again later."
    } as Record<number, string>)[status] ?? "The request could not be completed. Refresh your files before trying again.");
  }
}
async function response(path: string, init?: RequestInit) {
  let result: Response;
  try { result = await authenticatedFetch(`/api/file-storage${path}`, init); }
  catch (error) { if (init?.signal?.aborted) throw error; throw new StorageError(0, "network_error"); }
  if (!result.ok) {
    const body = await result.json().catch(() => null) as { error?: { code?: string } } | null;
    throw new StorageError(result.status, body?.error?.code ?? "request_failed");
  }
  return result;
}
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const result = await response(path, init);
  return result.status === 204 ? undefined as T : result.json() as Promise<T>;
}
const entryPath = (id: string) => `/entries/${encodeURIComponent(id)}`;
const json = (method: string, body: unknown, signal?: AbortSignal): RequestInit => ({
  method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal
});
export const fileStorageClient = {
  limits: (signal?: AbortSignal) => request<StorageLimits>("/capabilities", { signal }),
  list(options: { parent?: string | null; q?: string; trash?: boolean; offset?: number; limit?: number } = {}, signal?: AbortSignal) {
    const params = new URLSearchParams({ limit: String(options.limit ?? 50), offset: String(options.offset ?? 0) });
    if (options.parent) params.set("parent_id", options.parent);
    if (options.q) params.set("q", options.q);
    return request<StoragePage>(`${options.trash ? "/trash" : "/entries"}?${params}`, { signal });
  },
  detail: (id: string, signal?: AbortSignal) => request<StorageDetail>(entryPath(id), { signal }),
  folder: (name: string, parent_id: string | null, signal?: AbortSignal) => request<StorageEntry>("/folders", json("POST", { name, parent_id }, signal)),
  rename: (id: string, name: string, signal?: AbortSignal) => request<StorageEntry>(entryPath(id), json("PATCH", { name }, signal)),
  move: (id: string, target: StorageDestination, signal?: AbortSignal) => request<StorageEntry>(`${entryPath(id)}/move`, json("POST", target, signal)),
  copy: (id: string, target: StorageDestination, signal?: AbortSignal) => request<StorageEntry>(`${entryPath(id)}/copy`, json("POST", target, signal)),
  trash: (id: string, signal?: AbortSignal) => request<void>(entryPath(id), { method: "DELETE", signal }),
  restore: (id: string, target: StorageDestination, signal?: AbortSignal) => request<StorageEntry>(`/trash/${encodeURIComponent(id)}/restore`, json("POST", target, signal)),
  purge: (id: string, signal?: AbortSignal) => request<void>(`/trash/${encodeURIComponent(id)}`, { method: "DELETE", signal }),
  upload(files: File[], parent: string | null, signal?: AbortSignal) {
    const body = new FormData();
    for (const file of files) body.append("files", file, file.name);
    if (parent) body.append("parent_id", parent);
    return request<{ items: StorageEntry[] }>("/files", { method: "POST", body, signal });
  },
  uploadTree(files: File[], paths: string[], directories: string[], parent: string | null, signal?: AbortSignal) {
    const body = new FormData();
    for (const file of files) body.append("files", file, file.name);
    body.append("tree", JSON.stringify({ paths, directories }));
    if (parent) body.append("parent_id", parent);
    return request<{ items: StorageEntry[] }>("/files", { method: "POST", body, signal });
  },
  async preview(item: StorageEntry, signal?: AbortSignal): Promise<StoragePreview> {
    const result = await response(`${entryPath(item.id)}/preview`, { signal });
    const kind = result.headers.get("x-preview-kind");
    const contentType = result.headers.get("content-type") ?? "";
    if (kind === "text") return { kind, text: await result.text(), filename: item.name, contentType };
    if (kind === "image" || kind === "pdf") return { kind, blob: await result.blob(), filename: item.name, contentType };
    throw new StorageError(502, "preview_failed");
  },
  async download(item: StorageEntry, signal?: AbortSignal) {
    const result = await response(`${entryPath(item.id)}/download`, { signal });
    const blob = await result.blob();
    const header = result.headers.get("content-disposition") ?? "";
    let name = item.name;
    const encoded = header.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
    if (encoded) { try { name = decodeURIComponent(encoded); } catch { /* Keep the known logical name. */ } }
    return { blob, name };
  }
};

export function saveStorageDownload(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url; anchor.download = name;
  document.body.append(anchor); anchor.click(); anchor.remove();
  // Give the browser time to begin consuming the object URL.
  window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
}
