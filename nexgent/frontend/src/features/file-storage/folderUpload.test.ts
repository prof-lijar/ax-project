import { describe, expect, it } from "vitest";
import { droppedFiles, pickedFolder } from "./folderUpload";
import { uploadProblem } from "./helpers";

const limits = { max_files: 20, max_file_bytes: 100, max_batch_bytes: 1000 };
function fileEntry(name: string, bytes = "content") {
  return { name, isFile: true, isDirectory: false, file: (done: (file: File) => void) => done(new File([bytes], name)) };
}
function directory(name: string, batches: unknown[][]): unknown {
  return { name, isFile: false, isDirectory: true, createReader: () => {
    let index = 0;
    return { readEntries: (done: (entries: unknown[]) => void) => done(batches[index++] ?? []) };
  } };
}
function drop(entry: unknown) {
  return { items: [{ kind: "file", webkitGetAsEntry: () => entry, getAsFile: () => null }], files: [] } as unknown as DataTransfer;
}
describe("folder upload selection", () => {
  it("drains multiple directory batches and keeps empty folders and relative paths", async () => {
    const entry = directory("Project", [[fileEntry("a.txt")], [directory("Nested", [[fileEntry("b.txt")]]), directory("Empty", [])]]);
    const result = await droppedFiles(drop(entry), limits, new AbortController().signal);
    expect(result.paths).toEqual(["Project/a.txt", "Project/Nested/b.txt"]);
    expect(result.directories).toEqual(["Project", "Project/Nested", "Project/Empty"]);
    expect(await result.files[1].text()).toBe("content");
  });
  it("stops traversal at file count, byte and directory bounds", async () => {
    const entry = directory("Project", [[fileEntry("a"), fileEntry("b")]]);
    await expect(droppedFiles(drop(entry), {...limits, max_files:1}, new AbortController().signal)).rejects.toThrow("Too many");
    await expect(droppedFiles(drop(entry), {...limits, max_file_bytes:1}, new AbortController().signal)).rejects.toThrow("limits");
    await expect(droppedFiles(drop(directory("Root", [[directory("Child", [])]])), {...limits, max_upload_folders:1}, new AbortController().signal)).rejects.toThrow("invalid paths");
  });
  it("supports cancellation and rejects invalid path segments", async () => {
    const controller = new AbortController(); controller.abort();
    await expect(droppedFiles(drop(directory("Root", [])), limits, controller.signal)).rejects.toThrow();
    await expect(droppedFiles(drop(directory("..", [])), limits, new AbortController().signal)).rejects.toThrow("invalid paths");
  });
  it("preserves picker relative paths and validates empty directory uploads", () => {
    const file = new File(["a"], "a.txt");
    Object.defineProperty(file, "webkitRelativePath", {value:"Project/Sub/a.txt"});
    const result = pickedFolder([file]);
    expect(result.paths).toEqual(["Project/Sub/a.txt"]);
    expect(uploadProblem(result.files, limits, result.paths)).toBeNull();
    expect(uploadProblem([], limits, [], ["Empty/Child"])).toBeNull();
    expect(uploadProblem([file], limits, ["../a.txt"])).toContain("invalid paths");
    expect(uploadProblem([file], {...limits, max_upload_depth:2}, result.paths)).toContain("invalid paths");
  });
});
