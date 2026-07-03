import {
  nextcloudDownloadFile,
  nextcloudFiles,
  nextcloudStatus,
  nextcloudTextFile
} from "./nextcloudMockData";
import type {
  NextcloudFileItem,
  NextcloudDownloadResponse,
  NextcloudListFilesResponse,
  NextcloudStatus,
  NextcloudTextFileResponse
} from "../types/nextcloud";

const BACKEND_URL =
  import.meta.env.VITE_BACKEND_URL?.replace(/\/$/, "") ?? defaultBackendUrl();

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

function defaultBackendUrl() {
  if (typeof window === "undefined") {
    return "http://127.0.0.1:8000";
  }

  const hostname = window.location.hostname;
  if (hostname && hostname !== "localhost" && hostname !== "127.0.0.1") {
    return `${window.location.protocol}//${hostname}:8000`;
  }

  return "http://127.0.0.1:8000";
}

export async function getBrowserNextcloudStatus(): Promise<NextcloudStatus> {
  try {
    const response = await fetch(`${BACKEND_URL}/api/nextcloud/capabilities`);
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
    return nextcloudStatus;
  }
}

export async function listBrowserNextcloudFiles(
  path: string
): Promise<NextcloudListFilesResponse> {
  try {
    const url = new URL(`${BACKEND_URL}/api/nextcloud/files`);
    url.searchParams.set("path", path);
    url.searchParams.set("depth", "1");
    return normalizeListFilesResponse(
      await requestJson<BackendNextcloudListFilesResponse>(url)
    );
  } catch {
    return nextcloudFiles(path);
  }
}

export async function readBrowserNextcloudTextFile(
  path: string
): Promise<NextcloudTextFileResponse> {
  try {
    const url = new URL(`${BACKEND_URL}/api/nextcloud/files/content`);
    url.searchParams.set("path", path);
    return normalizeTextFileResponse(
      await requestJson<BackendNextcloudTextFileResponse>(url)
    );
  } catch {
    return nextcloudTextFile(path);
  }
}

export async function downloadBrowserNextcloudFile(
  path: string
): Promise<NextcloudDownloadResponse> {
  try {
    const url = new URL(`${BACKEND_URL}/api/nextcloud/files/download`);
    url.searchParams.set("path", path);
    const response = await fetch(url);
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
  } catch {
    return nextcloudDownloadFile(path);
  }
}

async function requestJson<T>(url: URL): Promise<T> {
  const response = await fetch(url);
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
