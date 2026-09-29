import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { AppShell } from "../../app/shell/AppShell";
import { agentCatalogClient } from "../../shared/api/agentCatalogClient";
import type { Account } from "../../shared/api/accountClient";
import { useLanguage } from "../../shared/i18n";
import { AgentsPageView } from "../agents/AgentsPage";
import { AccountContext } from "./accountContext";
import { AdminOnly } from "./AdminOnly";

const account = (is_admin: boolean): Account => ({
  id: "member", name: "Member", username: "member", email: "", roles: [],
  permissions: is_admin ? ["access.manage"] : [], is_admin, csrf_token: "test-only"
});

describe("administrator-only pages", () => {
  it("does not mount protected children for a member", () => {
    const Protected = vi.fn(() => <p>Protected operations</p>);
    const markup = renderToStaticMarkup(<AccountContext.Provider value={account(false)}>
      <AdminOnly><Protected /></AdminOnly>
    </AccountContext.Provider>);
    expect(Protected).not.toHaveBeenCalled();
    expect(markup).toContain("Only administrators can access this page.");
    expect(markup).not.toContain("Protected operations");
  });

  it("allows administrators and denies access again after a role change", () => {
    const Protected = vi.fn(() => <p>Protected operations</p>);
    const render = (admin: boolean) => renderToStaticMarkup(<AccountContext.Provider value={account(admin)}>
      <AdminOnly><Protected /></AdminOnly>
    </AccountContext.Provider>);
    expect(render(true)).toContain("Protected operations");
    expect(Protected).toHaveBeenCalledTimes(1);
    useLanguage.setState({ language: "ko" });
    expect(render(false)).toContain("관리자만 이 페이지에 접근할 수 있습니다.");
    expect(Protected).toHaveBeenCalledTimes(1);
  });

  it.each([false, true])("shows Knowledge as disabled only for non-admins (admin: %s)", admin => {
    const client = new QueryClient();
    const markup = renderToStaticMarkup(<QueryClientProvider client={client}>
      <AccountContext.Provider value={account(admin)}><AppShell><p>Workspace</p></AppShell></AccountContext.Provider>
    </QueryClientProvider>);
    expect(markup.includes('href="/rag"')).toBe(admin);
    expect(markup.includes('aria-label="Knowledge — Admin only"')).toBe(!admin);
    if (!admin) expect(markup).toMatch(/<button[^>]*disabled=""[^>]*aria-label="Knowledge — Admin only"/);
    expect(markup).toContain('href="/agents"');
    expect(markup).toContain('href="/chat"');
  });

  it("disables every member detail/workspace entry while retaining Chat", async () => {
    const agents = await agentCatalogClient.listAgents();
    const markup = renderToStaticMarkup(<AgentsPageView agents={agents} search="" />);
    expect(markup).toContain("Agent details and workspaces are available to administrators only.");
    expect(markup).not.toContain('href="/agents/');
    expect(markup).toMatch(/<button[^>]*disabled=""[^>]*>Open workspace<\/button>/);
    expect(markup).toMatch(/<button[^>]*disabled=""[^>]*>View details<\/button>/);
    expect(markup).toMatch(/<button(?![^>]*disabled)[^>]*aria-label="Start chat with RAG Agent"/);
  });
});
