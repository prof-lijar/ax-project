let csrfToken: string | null = null;
export const AUTH_EXPIRED_EVENT = "nexgent-auth-expired";
export function setCsrfToken(value: string | null) { csrfToken = value; }

export async function authenticatedFetch(input: string | URL, init: RequestInit = {}) {
  const raw = String(input);
  const origin = typeof window !== "undefined" && window.location?.origin || "http://nexgent.test";
  const url = new URL(raw, origin);
  if (url.origin !== origin) throw new Error("Feature requests must use the Nexgent origin.");
  const headers = new Headers(init.headers);
  const mutating = !["GET", "HEAD", "OPTIONS"].includes((init.method ?? "GET").toUpperCase());
  if (mutating && csrfToken) headers.set("X-CSRF-Token", csrfToken);
  const response = await fetch(input, { ...init, headers: Object.fromEntries(headers.entries()),
    credentials: "same-origin", cache: "no-store" });
  if (response.status === 401 && url.pathname !== "/auth/login") {
    csrfToken = null;
    if (typeof window !== "undefined") window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
  }
  return response;
}
