import { authenticatedFetch } from "./authenticatedFetch";
import type {
  NextcloudFileItem,
  NextcloudDownloadResponse,
  NextcloudListFilesResponse,
  NextcloudPreviewResponse,
  NextcloudStatus,
  NextcloudTextFileResponse,
  NextcloudViewerKind
} from "../types/nextcloud";

const BACKEND_URL = "";

export function backendUrl(path: string) {
  return `${BACKEND_URL}${path}`;
}

interface BackendNextcloudFileItem {
  path: string;
  name: string;
  is_directory?: boolean;
  isDirectory?: boolean;
  content_type?: string | null;
  contentType?: string | null;
  size: number | null;
  etag: string | null;
  last_modified?: string | null;
  lastModified?: string | null;
}

interface BackendNextcloudListFilesResponse {
  path: string;
  depth: number;
  items: BackendNextcloudFileItem[];
}

interface BackendNextcloudTextFileResponse {
  path: string;
  content: string;
  content_type?: string | null;
  contentType?: string | null;
}

export async function getBrowserNextcloudStatus(): Promise<NextcloudStatus> {
  try {
    const response = await authenticatedFetch(backendUrl("/api/nextcloud/capabilities"));
    if (!response.ok) {
      return {
        ok: false,
        backendUrl: BACKEND_URL,
        detail: await errorDetail(response),
        capabilitiesAvailable: false
      };
    }

    return {
      ok: true,
      backendUrl: BACKEND_URL,
      detail: null,
      capabilitiesAvailable: true
    };
  } catch {
    return {
      ok: false,
      backendUrl: BACKEND_URL,
      detail: "The Nextcloud service could not be reached.",
      capabilitiesAvailable: false
    };
  }
}

export async function listBrowserNextcloudFiles(
  path: string
): Promise<NextcloudListFilesResponse> {
  const url = new URL(`${BACKEND_URL}/api/nextcloud/files`, window.location.origin);
  url.searchParams.set("path", path);
  url.searchParams.set("depth", "1");
  return normalizeListFilesResponse(
    await requestJson<BackendNextcloudListFilesResponse>(url)
  );
}

export async function readBrowserNextcloudTextFile(
  path: string
): Promise<NextcloudTextFileResponse> {
  const url = new URL(`${BACKEND_URL}/api/nextcloud/files/content`, window.location.origin);
  url.searchParams.set("path", path);
  return normalizeTextFileResponse(
    await requestJson<BackendNextcloudTextFileResponse>(url)
  );
}

export async function previewBrowserNextcloudFile(
  path: string
): Promise<NextcloudPreviewResponse> {
  const url = new URL(`${BACKEND_URL}/api/nextcloud/files/preview`, window.location.origin);
  url.searchParams.set("path", path);
  const response = await authenticatedFetch(url);
  if (!response.ok) {
    throw new Error(await errorDetail(response));
  }

  const contentType =
    response.headers.get("content-type") ?? "application/octet-stream";
  const viewerKind = normalizeViewerKind(
    response.headers.get("x-preview-kind"),
    contentType
  );
  const filename = filenameFromResponse(response, path);

  if (viewerKind === "text") {
    return {
      path,
      filename,
      contentType,
      viewerKind,
      text: await response.text()
    };
  }

  const blob = await response.blob();
  return {
    path,
    filename,
    contentType,
    viewerKind,
    objectUrl: URL.createObjectURL(blob)
  };
}

export async function downloadBrowserNextcloudFile(
  path: string
): Promise<NextcloudDownloadResponse> {
  const url = new URL(`${BACKEND_URL}/api/nextcloud/files/download`, window.location.origin);
  url.searchParams.set("path", path);
  const response = await authenticatedFetch(url);
  if (!response.ok) {
    throw new Error(await errorDetail(response));
  }

  const blob = await response.blob();
  const filename = filenameFromResponse(response, path);
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(objectUrl);

  return {
    path,
    filename,
    savedPath: `Browser downloads/${filename}`,
    bytesWritten: blob.size
  };
}

async function requestJson<T>(url: URL): Promise<T> {
  const response = await authenticatedFetch(url);
  if (!response.ok) {
    throw new Error(await errorDetail(response));
  }

  return response.json() as Promise<T>;
}

function normalizeListFilesResponse(
  response: BackendNextcloudListFilesResponse
): NextcloudListFilesResponse {
  return {
    path: response.path,
    depth: response.depth,
    items: response.items.map(normalizeFileItem)
  };
}

function normalizeFileItem(item: BackendNextcloudFileItem): NextcloudFileItem {
  return {
    path: item.path,
    name: item.name,
    isDirectory: item.isDirectory ?? item.is_directory ?? false,
    contentType: item.contentType ?? item.content_type ?? null,
    size: item.size,
    etag: item.etag,
    lastModified: item.lastModified ?? item.last_modified ?? null
  };
}

function normalizeTextFileResponse(
  response: BackendNextcloudTextFileResponse
): NextcloudTextFileResponse {
  return {
    path: response.path,
    content: response.content,
    contentType: response.contentType ?? response.content_type ?? null
  };
}

function normalizeViewerKind(
  value: string | null,
  contentType: string
): NextcloudViewerKind {
  if (value === "pdf" || value === "image" || value === "text") {
    return value;
  }

  const normalized = contentType.split(";", 1)[0]?.trim().toLowerCase();
  if (normalized === "application/pdf") {
    return "pdf";
  }
  if (normalized?.startsWith("image/")) {
    return "image";
  }
  return "text";
}

async function errorDetail(response: Response) {
  try {
    const body = (await response.json()) as { detail?: string };
    return body.detail ?? `Backend returned HTTP ${response.status}.`;
  } catch {
    return `Backend returned HTTP ${response.status}.`;
  }
}

function filenameFromResponse(response: Response, path: string) {
  const disposition = response.headers.get("content-disposition") ?? "";
  const filenameMatch = disposition.match(/filename="?([^"]+)"?/i);
  return filenameMatch?.[1] ?? path.split("/").pop() ?? "download";
}
