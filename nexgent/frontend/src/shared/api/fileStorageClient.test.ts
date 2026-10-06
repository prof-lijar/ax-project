import { afterEach, describe, expect, it, vi } from "vitest";
import { fileStorageClient, StorageError, type StorageEntry } from "./fileStorageClient";
import { setCsrfToken } from "./authenticatedFetch";

afterEach(() => { vi.unstubAllGlobals(); setCsrfToken(null); });
const mock = (data: unknown = {}, status = 200) => {
  const fetch = vi.fn().mockImplementation(async () => new Response(status === 204 ? null : JSON.stringify(data), { status }));
  vi.stubGlobal("fetch", fetch); return fetch;
};
describe("file storage API", () => {
  it("uses the authenticated same-origin boundary and sends multipart without a JSON content type", async () => {
    const fetch = mock({ items: [] }, 201); setCsrfToken("session-csrf");
    await fileStorageClient.upload([new File(["hello"], "보고서.txt", { type: "text/plain" }), new File(["other"], "other.txt")], "folder-id");
    expect(fetch.mock.calls[0][0]).toBe("/api/file-storage/files");
    const init = fetch.mock.calls[0][1];
    expect(init.credentials).toBe("same-origin");
    expect(init.headers["x-csrf-token"]).toBe("session-csrf");
    expect(init.headers["content-type"]).toBeUndefined();
    expect(init.body.get("parent_id")).toBe("folder-id");
    expect(init.body.getAll("files").map((file: File) => file.name)).toEqual(["보고서.txt", "other.txt"]);
  });
  it("encodes literal search and paginates both views", async () => {
    const fetch = mock({ items: [], total: 0, offset: 50, limit: 50 });
    await fileStorageClient.list({ q: "100% & 보고", offset: 50 });
    const params = new URL(fetch.mock.calls[0][0], "http://nexgent.test").searchParams;
    expect(params.get("q")).toBe("100% & 보고"); expect(params.get("offset")).toBe("50");
    await fileStorageClient.list({ trash: true }); expect(fetch.mock.calls[1][0]).toContain("/trash?");
  });
  it("preserves omitted restore parent versus explicit root and accepts 204", async () => {
    const fetch = mock(); await fileStorageClient.restore("item", {});
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({});
    await fileStorageClient.restore("item", { parent_id: null, name: "New name" });
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ parent_id: null, name: "New name" });
    mock(null, 204); await expect(fileStorageClient.purge("item")).resolves.toBeUndefined();
  });
  it("turns backend conflict codes into recoverable messages without reflecting upstream text", async () => {
    mock({ error: { code: "name_conflict" }, detail: "secret upstream data" }, 409);
    await expect(fileStorageClient.rename("item", "name")).rejects.toThrow("Choose another name");
    mock({ detail: "secret upstream data" }, 502);
    await expect(fileStorageClient.detail("item")).rejects.toBeInstanceOf(StorageError);
  });
  it("uses UTF-8 download filenames and returns the original bytes", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("original", { headers: {
      "Content-Disposition": "attachment; filename*=UTF-8''%EB%B3%B4%EA%B3%A0%EC%84%9C.txt"
    } })));
    const result = await fileStorageClient.download({ id: "item", name: "old.txt" } as StorageEntry);
    expect(result.name).toBe("보고서.txt"); expect(await result.blob.text()).toBe("original");
  });
});

describe("file storage previews", () => {
  const item = { id: "private-item", name: "보고서.md" } as StorageEntry;
  it("loads text using the authenticated endpoint and preserves the logical filename", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response("# Notes", { headers: { "X-Preview-Kind": "text", "Content-Type": "text/markdown" } }));
    vi.stubGlobal("fetch", fetch);
    const controller = new AbortController();
    expect(await fileStorageClient.preview(item, controller.signal)).toEqual({ kind: "text", text: "# Notes", filename: item.name, contentType: "text/markdown" });
    expect(fetch.mock.calls[0][0]).toBe("/api/file-storage/entries/private-item/preview");
    expect(fetch.mock.calls[0][1]).toMatchObject({ credentials: "same-origin", signal: controller.signal });
  });
  it.each(["image", "pdf"])("returns %s bytes for the browser viewer", async kind => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("preview bytes", { headers: { "X-Preview-Kind": kind } })));
    const result = await fileStorageClient.preview(item);
    expect(result.kind).toBe(kind);
    if (result.kind !== "text") expect(await result.blob.text()).toBe("preview bytes");
  });
  it("rejects an invalid viewer kind and reports conversion failures without upstream details", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<script>bad</script>", { headers: { "X-Preview-Kind": "html" } })));
    await expect(fileStorageClient.preview(item)).rejects.toThrow("could not be opened");
    mock({ error: { code: "preview_converter_unavailable" }, detail: "private server path" }, 501);
    await expect(fileStorageClient.preview(item)).rejects.toThrow("Office preview is unavailable");
  });
});

describe("folder upload API", () => {
  it("sends files with an ordered path manifest and preserves empty directories", async () => {
    const fetch = mock({items:[]}, 201); setCsrfToken("session-csrf");
    await fileStorageClient.uploadTree([new File(["a"], "a.txt")], ["Project/Sub/a.txt"], ["Project/Empty"], "parent");
    const body = fetch.mock.calls[0][1].body as FormData;
    expect(JSON.parse(body.get("tree") as string)).toEqual({paths:["Project/Sub/a.txt"], directories:["Project/Empty"]});
    expect(body.get("parent_id")).toBe("parent");
    expect((body.get("files") as File).name).toBe("a.txt");
    expect(fetch.mock.calls[0][1].headers["x-csrf-token"]).toBe("session-csrf");
    expect(fetch.mock.calls[0][1].headers["content-type"]).toBeUndefined();
  });
});
