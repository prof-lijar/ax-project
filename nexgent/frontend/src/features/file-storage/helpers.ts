import type { StorageLimits } from "../../shared/api/fileStorageClient";

export function validStorageName(name: string) {
  const normalized = name.normalize("NFC").trim();
  return Boolean(normalized && ![".", ".."].includes(normalized) &&
    new TextEncoder().encode(normalized).length <= 255 && !/[\/\\\p{C}]/u.test(normalized));
}
export function uploadProblem(files: File[], limits: StorageLimits, paths?: string[], directories: string[] = []): string | null {
  if (!files.length && !directories.length) return "Choose at least one file.";
  if (files.length > limits.max_files) return "Too many files selected. Upload a smaller batch.";
  if (paths) {
    const folders = new Set<string>();
    if (paths.length !== files.length) return "The folder could not be read or contains invalid paths. Choose it again.";
    for (const path of [...paths, ...directories]) {
      const parts = path.split("/");
      if (parts.length > (limits.max_upload_depth ?? 32) || parts.some(part => !validStorageName(part))) return "The folder could not be read or contains invalid paths. Choose it again.";
      for (let i = 1; i < parts.length; i++) folders.add(parts.slice(0, i).join("/"));
    }
    directories.forEach(path => folders.add(path));
    if (folders.size > (limits.max_upload_folders ?? 1000)) return "The folder could not be read or contains invalid paths. Choose it again.";
  }
  if (files.some(file => !validStorageName(file.name))) return "Use a name without slashes or control characters, up to 255 UTF-8 bytes.";
  if (files.some(file => file.size > limits.max_file_bytes) ||
      files.reduce((sum, file) => sum + file.size, 0) > limits.max_batch_bytes) return "The selected files exceed the upload limits.";
  return null;
}
export function storageSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024, unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
  return `${value.toFixed(1)} ${units[unit]}`;
}
