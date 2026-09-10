import { describe, expect, it } from "vitest";
import { deduplicateFiles, validateSelectedFiles } from "./chatAttachments";
import { isNearBottom } from "./ChatTranscript";

function file(name: string, size: number, lastModified = 1) {
  return { name, size, lastModified, type: "text/plain" } as File;
}
describe("attachment validation", () => {
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
      validateSelectedFiles([file("big.pdf", 10 * 1024 * 1024 + 1)])
    ).toContain("10 MB");
    expect(
      validateSelectedFiles(
        Array.from({ length: 6 }, (_, i) => file(`${i}.txt`, 1))
      )
    ).toContain("no more than 5");
    expect(
      validateSelectedFiles(
        Array.from({ length: 3 }, (_, i) => file(`${i}.pdf`, 9 * 1024 * 1024))
      )
    ).toContain("25 MB total");
  });
});
describe("transcript follow threshold", () => {
  it("follows at the bottom but leaves earlier messages readable", () => {
    expect(isNearBottom(420, 1000, 500)).toBe(true);
    expect(isNearBottom(419, 1000, 500)).toBe(false);
    expect(isNearBottom(0, 200, 500)).toBe(true);
  });
});
