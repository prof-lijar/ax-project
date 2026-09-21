import { setCsrfToken } from "./authenticatedFetch";
export interface Account {
  id: string; username: string; name: string; email: string;
  roles: string[]; permissions: string[]; is_admin: boolean; csrf_token: string;
}
export interface AccessUser {
  id: string; username: string; name: string; email: string; is_active: boolean;
  password_set: boolean; role_ids: string[]; group_ids: string[]; permissions: string[];
}
export interface AccessGroup { id: string; name: string; description: string; role_ids: string[] }
export interface AccessRole { id: string; name: string; description: string; permission_ids: string[]; is_system: boolean }
export interface AccessPermission { id: string; key: string; description: string; is_system: boolean }
export interface AccessCatalog {
  users: AccessUser[]; groups: AccessGroup[]; roles: AccessRole[]; permissions: AccessPermission[];
}
export type AccessKind = "groups" | "roles" | "permissions";
const messages: Record<string, string> = {
  invalid_credentials: "The username or password is incorrect.",
  last_admin_required: "Keep at least one active administrator with a password.",
  duplicate_or_invalid_reference: "That username, name, or permission key already exists, or an assignment is invalid.",
  unknown_assignment: "An assignment no longer exists. Refresh and try again.",
  invalid_input: "Check the form values. Passwords must contain 4–12 characters.",
  system_definition_read_only: "Built-in access definitions cannot be changed.",
  permission_denied: "You no longer have permission to manage access."
};
export class AccountError extends Error {
  constructor(readonly status: number, readonly code = "") {
    super(messages[code] ?? (status === 401 ? "Your login has ended. Sign in again."
      : status === 429 ? "Too many attempts. Wait a minute and try again." : "The request failed. Please try again."));
  }
}
async function request(path: string, init: RequestInit = {}) {
  const response = await fetch(path, { ...init, credentials: "same-origin", cache: "no-store" });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new AccountError(response.status, body?.error?.code);
  }
  return response.json();
}
function write(path: string, method: string, csrf?: string, body?: object) {
  return request(path, { method, headers: { "Content-Type": "application/json", ...(csrf ? { "X-CSRF-Token": csrf } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}) });
}
export const accountClient = {
  async me(signal?: AbortSignal): Promise<Account | null> {
    try { const account = await request("/api/me", { signal }); setCsrfToken(account.csrf_token); return account; }
    catch (error) { if (error instanceof AccountError && error.status === 401) { setCsrfToken(null); return null; } throw error; }
  },
  async login(username: string, password: string): Promise<void> { await write("/auth/login", "POST", undefined, { username, password }); },
  async logout(csrf: string): Promise<void> { await write("/auth/logout", "POST", csrf); },
  async catalog(signal?: AbortSignal): Promise<AccessCatalog> { return request("/api/admin/access", { signal }); },
  async saveUser(id: string | null, values: object, csrf: string): Promise<void> {
    await write(id ? `/api/admin/users/${encodeURIComponent(id)}` : "/api/admin/users", id ? "PUT" : "POST", csrf, values);
  },
  async resetPassword(id: string, password: string, csrf: string): Promise<void> {
    await write(`/api/admin/users/${encodeURIComponent(id)}/password`, "PUT", csrf, { password });
  },
  async save(kind: AccessKind, id: string | null, values: object, csrf: string): Promise<void> {
    await write(`/api/admin/${kind}${id ? "/" + encodeURIComponent(id) : ""}`, id ? "PUT" : "POST", csrf, values);
  },
  async remove(kind: AccessKind, id: string, csrf: string): Promise<void> {
    await write(`/api/admin/${kind}/${encodeURIComponent(id)}`, "DELETE", csrf);
  }
};
