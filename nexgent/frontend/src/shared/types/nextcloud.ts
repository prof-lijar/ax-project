export interface NextcloudStatus {
  ok: boolean;
  backendUrl: string;
  detail: string | null;
  capabilitiesAvailable: boolean;
}

export interface NextcloudFileItem {
  path: string;
  name: string;
  isDirectory: boolean;
  contentType: string | null;
  size: number | null;
  etag: string | null;
  lastModified: string | null;
}

export interface NextcloudListFilesResponse {
  path: string;
  depth: number;
  items: NextcloudFileItem[];
}

export interface NextcloudTextFileResponse {
  path: string;
  content: string;
  contentType: string | null;
}

export type NextcloudViewerKind = "pdf" | "image" | "text";

export interface NextcloudPreviewResponse {
  path: string;
  filename: string;
  contentType: string;
  viewerKind: NextcloudViewerKind;
  objectUrl?: string;
  text?: string;
}

export interface NextcloudDownloadResponse {
  path: string;
  filename: string;
  savedPath: string;
  bytesWritten: number;
}
