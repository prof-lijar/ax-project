import { afterEach, describe, expect, it, vi } from "vitest";
import { AccountError, accountClient } from "./accountClient";
afterEach(() => vi.unstubAllGlobals());
describe("account boundary client", () => {
  it("distinguishes an ended login from unavailable service", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response("", { status: 401 }))
      .mockResolvedValueOnce(new Response("", { status: 503 })));
    expect(await accountClient.me()).toBeNull();
    await expect(accountClient.me()).rejects.toBeInstanceOf(AccountError);
  });
  it("submits login credentials in a JSON body with same-origin cookies", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response("{}")); vi.stubGlobal("fetch", fetch);
    await accountClient.login("admin", "test-password");
    expect(fetch).toHaveBeenCalledWith("/auth/login", expect.objectContaining({
      method: "POST", credentials: "same-origin", cache: "no-store",
      body: JSON.stringify({ username: "admin", password: "test-password" })
    }));
  });
  it("sends CSRF on logout", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response("{}")); vi.stubGlobal("fetch", fetch);
    await accountClient.logout("csrf-value");
    expect(fetch).toHaveBeenCalledWith("/auth/logout", expect.objectContaining({
      method: "POST", headers: expect.objectContaining({ "X-CSRF-Token": "csrf-value" })
    }));
  });
  it("does not retry a denied admin mutation", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{"error":{"code":"last_admin_required"}}', { status: 409 }));
    vi.stubGlobal("fetch", fetch);
    await expect(accountClient.remove("groups", "group/id", "csrf")).rejects.toThrow("Keep at least one active administrator");
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][0]).toBe("/api/admin/groups/group%2Fid");
  });
  it("uses full updates for users and includes CSRF", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response("{}")); vi.stubGlobal("fetch", fetch);
    await accountClient.saveUser("user-id", { role_ids: [] }, "csrf");
    expect(fetch).toHaveBeenCalledWith("/api/admin/users/user-id", expect.objectContaining({
      method: "PUT", body: '{"role_ids":[]}', headers: expect.objectContaining({ "X-CSRF-Token": "csrf" })
    }));
  });
});
