import { t } from "../../shared/i18n";
import type { ChatAttachmentSummary } from "../../shared/state/useChatStore";

const MAX_ATTACHMENT_COUNT = 5;
const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;
const MAX_TOTAL_ATTACHMENT_BYTES = 25 * 1024 * 1024;
const ACCEPTED_ATTACHMENT_EXTENSIONS = new Set([
  "csv",
  "docx",
  "jpeg",
  "jpg",
  "md",
  "pdf",
  "png",
  "txt",
  "webp"
]);
export const ATTACHMENT_ACCEPT =
  ".pdf,.txt,.md,.csv,.docx,.png,.jpg,.jpeg,.webp," +
  "application/pdf,text/plain,text/markdown,text/csv," +
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document," +
  "image/png,image/jpeg,image/webp";

export function validateSelectedFiles(files: File[]) {
  if (files.length > MAX_ATTACHMENT_COUNT) {
    return t("Attach no more than {count} files.", { count: MAX_ATTACHMENT_COUNT });
  }
  for (const file of files) {
    const extension = file.name.split(".").pop()?.toLocaleLowerCase() ?? "";
    if (!ACCEPTED_ATTACHMENT_EXTENSIONS.has(extension)) {
      return t("{name} is not a supported attachment type.", { name: file.name });
    }
    if (file.size === 0) {
      return t("{name} is empty.", { name: file.name });
    }
    if (file.size > MAX_ATTACHMENT_BYTES) {
      return t("{name} exceeds the 10 MB per-file limit.", { name: file.name });
    }
  }
  const totalBytes = files.reduce((total, file) => total + file.size, 0);
  if (totalBytes > MAX_TOTAL_ATTACHMENT_BYTES) {
    return t("Attachments exceed the 25 MB total limit.");
  }
  return null;
}

export function deduplicateFiles(files: File[]) {
  return Array.from(
    new Map(files.map((file) => [attachmentKey(file), file])).values()
  );
}

export function attachmentKey(file: File) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

export function toAttachmentSummary(file: File): ChatAttachmentSummary {
  return { name: file.name, size: file.size, type: file.type };
}

export function formatFileSize(bytes: number) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${Math.ceil(bytes / 1024)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
