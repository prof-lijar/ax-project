import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AccountSettings, SignIn } from "./AccountApp";
import { AuthGate } from "./AuthGate";
import { AccountContext } from "./accountContext";
afterEach(() => vi.unstubAllGlobals());
const account = (admin: boolean) => ({ id: "user-id", username: "user", name: "User", email: "",
  roles: [], permissions: [], is_admin: admin, csrf_token: "csrf" });
describe("integrated account UI", () => {
  it("provides local login and administrator-only creation guidance", () => {
    const markup = renderToStaticMarkup(<SignIn onSignedIn={async () => {}} />);
    expect(markup).toContain('name="username"');
    expect(markup).toContain('type="password"');
    expect(markup).toContain("Contact your administrator");
    expect(markup).not.toContain("SSO");
  });
  it("does not allow the native shell to bypass login", () => {
    vi.stubGlobal("window", { __TAURI_INTERNALS__: {} });
    const markup = renderToStaticMarkup(<AuthGate><p>Private app</p></AuthGate>);
    expect(markup).toContain("Open Nexgent in your browser");
    expect(markup).not.toContain("Private app");
  });
  it.each([true, false])("shows admin management inside Settings only for admins: %s", isAdmin => {
    const client = new QueryClient();
    client.setQueryData(["access", "user-id"], { users: [], groups: [], roles: [], permissions: [] });
    const markup = renderToStaticMarkup(<QueryClientProvider client={client}><AccountContext.Provider value={account(isAdmin)}>
      <AccountSettings /></AccountContext.Provider></QueryClientProvider>);
    expect(markup.includes("Manage access")).toBe(isAdmin);
    expect(markup.includes("Create account")).toBe(isAdmin);
    expect(markup).toContain("Sign out all devices");
  });
  it.each([true, false])("gates every feature before rendering: signed in %s", signedIn => {
    const client = new QueryClient();
    client.setQueryData(["account"], signedIn ? account(false) : null);
    const markup = renderToStaticMarkup(<QueryClientProvider client={client}><AuthGate><p>Private app</p></AuthGate></QueryClientProvider>);
    expect(markup.includes("Private app")).toBe(signedIn);
    expect(markup.includes('name="password"')).toBe(!signedIn);
  });
});
