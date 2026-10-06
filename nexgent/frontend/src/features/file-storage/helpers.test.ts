import { describe, expect, it } from "vitest";
import { uploadProblem, validStorageName } from "./helpers";
import { getStorageLocation, resolveSectionLocation } from "../../shared/navigation/sections";
import { navItems } from "../../app/routes";
import { t, useLanguage } from "../../shared/i18n";

describe("storage interaction contracts", () => {
  it("resolves direct folder links and trash to the sidebar section", () => {
    const id = "12345678-1234-1234-1234-123456789012";
    expect(resolveSectionLocation(`/file-storage/folders/${id}`)?.section).toBe("file-storage");
    expect(getStorageLocation(`/file-storage/folders/${id}`)).toEqual({ parent: id, trash: false });
    expect(getStorageLocation("/file-storage/trash")).toEqual({ parent: null, trash: true });
    expect(navItems.find(item => item.id === "file-storage")?.path).toBe("/file-storage");
    expect(resolveSectionLocation("/file-storage/folders/invalid")).toBeNull();
  });
  it("matches server filename rules including byte limits and normalization", () => {
    expect(validStorageName("보고서.txt")).toBe(true);
    for (const name of ["", "..", "dir/file", "dir\\file", "a\nb", "가".repeat(86)]) expect(validStorageName(name)).toBe(false);
    const files = [new File(["a"], "é.txt"), new File(["b"], "e\u0301.txt")];
    expect(uploadProblem(files, { max_files: 2, max_file_bytes: 10, max_batch_bytes: 10 })).toBeNull();
  });
  it("checks file count, individual bytes and total before submitting", () => {
    const file = new File(["1234"], "data.txt");
    const other = new File(["1234"], "other.txt");
    expect(uploadProblem([file], { max_files: 2, max_file_bytes: 4, max_batch_bytes: 4 })).toBeNull();
    expect(uploadProblem([file], { max_files: 2, max_file_bytes: 3, max_batch_bytes: 10 })).toContain("limits");
    expect(uploadProblem([file, other], { max_files: 2, max_file_bytes: 4, max_batch_bytes: 6 })).toContain("limits");
    expect(uploadProblem([file, other], { max_files: 1, max_file_bytes: 4, max_batch_bytes: 10 })).toContain("Too many");
  });
  it("localizes navigation and recovery actions", () => {
    useLanguage.setState({ language: "ko" });
    expect(t("File Storage")).toBe("파일 보관함"); expect(t("Restore")).toBe("복원");
    expect(t("{count} selected", { count: 2 })).toBe("2개 선택됨");
  });
});
