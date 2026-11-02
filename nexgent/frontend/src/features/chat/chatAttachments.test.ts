import { describe, expect, it } from "vitest";
import { deduplicateFiles, validateSelectedFiles } from "./chatAttachments";
import { isNearBottom } from "./ChatTranscript";

function file(name: string, size: number, lastModified = 1) {
  return { name, size, lastModified, type: "text/plain" } as File;
}
describe("attachment validation", () => {
  it("accepts exactly 50 MiB per file and combined, but rejects one extra byte", () => {
    expect(validateSelectedFiles([file("large.pdf", 50 * 1024 * 1024)])).toBeNull();
    expect(validateSelectedFiles([file("a.pdf", 25 * 1024 * 1024), file("b.pdf", 25 * 1024 * 1024)])).toBeNull();
    expect(validateSelectedFiles([file("a.pdf", 50 * 1024 * 1024), file("b.pdf", 1)])).toContain("50 MB total");
  });
  it("accepts existing supported formats and removes duplicate selections", () => {
    const attachment = file("notes.txt", 50);
    expect(deduplicateFiles([attachment, attachment])).toEqual([attachment]);
    expect(
      validateSelectedFiles([attachment, file("photo.PNG", 100)])
    ).toBeNull();
  });
  it("rejects unsupported, empty, oversized and excessive files", () => {
    expect(validateSelectedFiles([file("program.exe", 100)])).toContain(
      "not a supported"
    );
    expect(validateSelectedFiles([file("empty.txt", 0)])).toContain("empty");
    expect(
      validateSelectedFiles([file("big.pdf", 50 * 1024 * 1024 + 1)])
    ).toContain("50 MB");
    expect(
      validateSelectedFiles(
        Array.from({ length: 6 }, (_, i) => file(`${i}.txt`, 1))
      )
    ).toContain("no more than 5");
    expect(
      validateSelectedFiles(
        Array.from({ length: 3 }, (_, i) => file(`${i}.pdf`, 20 * 1024 * 1024))
      )
    ).toContain("50 MB total");
  });
});
describe("transcript follow threshold", () => {
  it("follows at the bottom but leaves earlier messages readable", () => {
    expect(isNearBottom(420, 1000, 500)).toBe(true);
    expect(isNearBottom(419, 1000, 500)).toBe(false);
    expect(isNearBottom(0, 200, 500)).toBe(true);
  });
});
