import type { StorageLimits } from "../../shared/api/fileStorageClient";
import { validStorageName } from "./helpers";

export interface UploadSelection { files: File[]; paths: string[]; directories: string[] }
export const invalidTreeMessage = "The folder could not be read or contains invalid paths. Choose it again.";

export function pickedFolder(files: File[]): UploadSelection {
  return { files, paths: files.map(file => file.webkitRelativePath || file.name), directories: [] };
}

// Snapshot browser entries synchronously while the drop event still owns access.
export async function droppedFiles(transfer: DataTransfer, limits: StorageLimits, signal: AbortSignal): Promise<UploadSelection> {
  const items = Array.from(transfer.items).filter(item => item.kind === "file");
  const roots = items.map(item => ({ entry: item.webkitGetAsEntry?.(), file: item.getAsFile() }));
  const fallback = Array.from(transfer.files);
  const selection: UploadSelection = { files: [], paths: [], directories: [] };
  let bytes = 0;
  function check(path: string) {
    signal.throwIfAborted();
    const parts = path.split("/");
    if (parts.length > (limits.max_upload_depth ?? 32) || parts.some(part => !validStorageName(part))) throw new Error(invalidTreeMessage);
  }
  function add(file: File, path: string) {
    check(path); bytes += file.size;
    if (selection.files.length >= limits.max_files) throw new Error("Too many files selected. Upload a smaller batch.");
    if (file.size > limits.max_file_bytes || bytes > limits.max_batch_bytes) throw new Error("The selected files exceed the upload limits.");
    selection.files.push(file); selection.paths.push(path);
  }
  async function visit(entry: FileSystemEntry, parent = "") {
    const path = parent + entry.name;
    check(path);
    if (entry.isFile) {
      const file = await new Promise<File>((resolve, reject) => (entry as FileSystemFileEntry).file(resolve, reject));
      add(file, path);
    } else if (entry.isDirectory) {
      selection.directories.push(path);
      if (selection.directories.length > (limits.max_upload_folders ?? 1000)) throw new Error(invalidTreeMessage);
      const reader = (entry as FileSystemDirectoryEntry).createReader();
      // Chromium returns directory entries in batches; drain until it returns [].
      while (true) {
        signal.throwIfAborted();
        const children = await new Promise<FileSystemEntry[]>((resolve, reject) => reader.readEntries(resolve, reject));
        if (!children.length) break;
        for (const child of children) await visit(child, path + "/");
      }
    } else throw new Error(invalidTreeMessage);
  }
  if (!roots.length) for (const file of fallback) add(file, file.name);
  for (const root of roots) {
    if (root.entry) await visit(root.entry);
    else if (root.file) add(root.file, root.file.name);
    else throw new Error(invalidTreeMessage);
  }
  return selection;
}
