import { afterEach, expect, it, vi } from "vitest";
import { authenticatedFetch, setCsrfToken } from "./authenticatedFetch";
afterEach(() => { setCsrfToken(null); vi.unstubAllGlobals(); });
it("adds cookie credentials and CSRF to feature mutations without changing the body", async () => {
  const fetch = vi.fn().mockResolvedValue(new Response("{}")); vi.stubGlobal("fetch", fetch);
  setCsrfToken("csrf");
  const body = new FormData(); body.append("prompt", "hello");
  await authenticatedFetch("/api/chat/stream", { method: "POST", body });
  expect(fetch).toHaveBeenCalledWith("/api/chat/stream", expect.objectContaining({
    body, credentials: "same-origin", headers: { "x-csrf-token": "csrf" }
  }));
});
it("refuses cross-origin requests before sending credentials", async () => {
  const fetch = vi.fn(); vi.stubGlobal("fetch", fetch); setCsrfToken("csrf");
  await expect(authenticatedFetch("http://other.test/api", { method: "POST" })).rejects.toThrow("Nexgent origin");
  expect(fetch).not.toHaveBeenCalled();
});
it("notifies the login gate when a feature request loses authentication", async () => {
  const dispatchEvent = vi.fn();
  vi.stubGlobal("window", { location: { origin: "https://nexgent.test" }, dispatchEvent });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 401 })));
  await authenticatedFetch("/rag-api/rag/v1/search");
  expect(dispatchEvent).toHaveBeenCalledWith(expect.objectContaining({ type: "nexgent-auth-expired" }));
});
