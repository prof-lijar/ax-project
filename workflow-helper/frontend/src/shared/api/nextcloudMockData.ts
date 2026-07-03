import type {
  NextcloudFileItem,
  NextcloudListFilesResponse,
  NextcloudStatus,
  NextcloudTextFileResponse
} from "../types/nextcloud";

export const nextcloudStatus: NextcloudStatus = {
  ok: true,
  backendUrl: "http://127.0.0.1:8000",
  detail: null,
  capabilitiesAvailable: true
};

const rootItems: NextcloudFileItem[] = [
  {
    path: "AX Project",
    name: "AX Project",
    isDirectory: true,
    contentType: null,
    size: null,
    etag: "\"folder-ax\"",
    lastModified: "Fri, 03 Jul 2026 00:30:00 GMT"
  },
  {
    path: "Briefing.md",
    name: "Briefing.md",
    isDirectory: false,
    contentType: "text/markdown",
    size: 1480,
    etag: "\"briefing\"",
    lastModified: "Fri, 03 Jul 2026 00:20:00 GMT"
  },
  {
    path: "handoff.pdf",
    name: "handoff.pdf",
    isDirectory: false,
    contentType: "application/pdf",
    size: 488_120,
    etag: "\"handoff\"",
    lastModified: "Thu, 02 Jul 2026 22:14:00 GMT"
  }
];

const axProjectItems: NextcloudFileItem[] = [
  {
    path: "AX Project/agent-output.md",
    name: "agent-output.md",
    isDirectory: false,
    contentType: "text/markdown",
    size: 2120,
    etag: "\"agent-output\"",
    lastModified: "Fri, 03 Jul 2026 00:40:00 GMT"
  },
  {
    path: "AX Project/Research",
    name: "Research",
    isDirectory: true,
    contentType: null,
    size: null,
    etag: "\"research\"",
    lastModified: "Fri, 03 Jul 2026 00:10:00 GMT"
  }
];

const textFiles: Record<string, NextcloudTextFileResponse> = {
  "Briefing.md": {
    path: "Briefing.md",
    content:
      "# Briefing\n\nThis is a local preview sample for the NextCloud Drive surface.\n\nThe desktop app reads real files through the FastAPI backend when running inside Tauri.",
    contentType: "text/markdown"
  },
  "AX Project/agent-output.md": {
    path: "AX Project/agent-output.md",
    content:
      "# Agent output\n\nPlanner prepared the simplified co-worker workspace and left this file as sample Drive content.",
    contentType: "text/markdown"
  }
};

export function nextcloudFiles(path: string): NextcloudListFilesResponse {
  return {
    path,
    depth: 1,
    items: path === "AX Project" ? axProjectItems : rootItems
  };
}

export function nextcloudTextFile(path: string): NextcloudTextFileResponse {
  const textFile = textFiles[path];
  if (!textFile) {
    throw {
      code: "unsupported_media_type",
      message: "Preview unavailable for this file type.",
      recoveryAction: "Use download instead."
    };
  }

  return textFile;
}
