import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { NextcloudFileItem } from "../../shared/types/nextcloud";
import {
  fileTypeLabel,
  formatSize,
  NextcloudToolbar,
  pathParts,
  sortItems
} from "./NextcloudPage";

function file(
  name: string,
  options: Partial<NextcloudFileItem> = {}
): NextcloudFileItem {
  return {
    path: name,
    name,
    isDirectory: false,
    contentType: null,
    size: null,
    etag: null,
    lastModified: null,
    ...options
  };
}

describe("NextcloudPage", () => {
  it("renders a clear root location and selected list layout", () => {
    const markup = renderToStaticMarkup(
      <NextcloudToolbar
        currentPath=""
        onOpenFolder={() => undefined}
        onViewModeChange={() => undefined}
        viewMode="list"
      />
    );

    expect(markup).toContain("NextCloud");
    expect(markup).toContain("Nexgent");
    expect(markup).not.toContain("All files");
    expect(markup).not.toContain("Back one folder");
    expect(markup).toContain('aria-label="List view"');
    expect(markup).toContain('aria-pressed="true"');
  });

  it("renders each folder in the current breadcrumb path", () => {
    const markup = renderToStaticMarkup(
      <NextcloudToolbar
        currentPath="Team/Reports"
        onOpenFolder={() => undefined}
        onViewModeChange={() => undefined}
        viewMode="card"
      />
    );

    expect(pathParts("Team/Reports")).toEqual([
      { name: "Team", path: "Team" },
      { name: "Reports", path: "Team/Reports" }
    ]);
    expect(markup).toContain("Back one folder");
    expect(markup).toContain("Team");
    expect(markup).toContain("Reports");
  });

  it("sorts folders first and derives concise existing-file metadata", () => {
    const items = [
      file("zeta.pdf", { contentType: "application/pdf", size: 2048 }),
      file("Beta", { isDirectory: true }),
      file("Alpha", { isDirectory: true }),
      file("notes.md", { contentType: "text/markdown" })
    ];

    expect(sortItems(items).map((item) => item.name)).toEqual([
      "Alpha",
      "Beta",
      "notes.md",
      "zeta.pdf"
    ]);
    expect(fileTypeLabel(items[0])).toBe("PDF");
    expect(fileTypeLabel(items[3])).toBe("Markdown");
    expect(formatSize(2048)).toBe("2.0 KB");
    expect(formatSize(null)).toBe("-");
  });
});
