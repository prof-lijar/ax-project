import { authenticatedFetch } from "./authenticatedFetch";
import type { ChatMessage, ChatAttachmentSummary } from "../state/useChatStore";

export interface Page<T> { items: T[]; next_cursor: string | null }
export interface SavedConversation {
  id: string; title: string; created_at: string; updated_at: string; active_run_id: string | null;
}
export interface Submission {
  conversation_id: string; user_message_id: string; assistant_message_id: string; run_id: string;
}
export interface RunSnapshot extends Submission {
  status: "queued" | "running" | "completed" | "stopped" | "failed" | "interrupted";
  revision: number; cancel_requested: boolean; error_code: string | null; message: ChatMessage;
}
export class HistoryError extends Error {
  constructor(message: string, public status: number) { super(message); }
}
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await authenticatedFetch(`/api/chat${path}`, init);
  if (!response.ok) {
    const messages: Record<number, string> = {
      401: "Please sign in again.", 404: "This conversation or file is unavailable.",
      409: "This chat is already responding, or this submission was changed. Refresh and try again.",
      413: "The selected files exceed the attachment limits.",
      503: "Chat storage is unavailable. Your message has not been confirmed saved."
    };
    throw new HistoryError(messages[response.status] ?? "Couldn't save or load this chat. Please try again.", response.status);
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}
const paging = (cursor?: string | null) => cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
export const chatHistoryClient = {
  list: (cursor?: string | null, signal?: AbortSignal) => request<Page<SavedConversation>>(`/conversations${paging(cursor)}`, { signal }),
  get: (id: string, signal?: AbortSignal) => request<SavedConversation>(`/conversations/${id}`, { signal }),
  messages: (id: string, cursor?: string | null, signal?: AbortSignal) => request<Page<ChatMessage>>(`/conversations/${id}/messages${paging(cursor)}`, { signal }),
  files: (id: string, cursor?: string | null, signal?: AbortSignal) => request<Page<ChatAttachmentSummary>>(`/conversations/${id}/attachments${paging(cursor)}`, { signal }),
  rename: (id: string, title: string) => request<SavedConversation>(`/conversations/${id}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title })
  }),
  remove: (id: string) => request<void>(`/conversations/${id}`, { method: "DELETE" }),
  async submit(id: string | undefined, prompt: string, files: File[], selected: string[], key: string, signal?: AbortSignal) {
    const body = new FormData();
    body.append("prompt", prompt);
    for (const file of files) body.append("files", file, file.name);
    for (const file of selected) body.append("attachment_ids", file);
    return request<Submission>(id ? `/conversations/${id}/messages` : "/conversations", {
      method: "POST", body, headers: { "Idempotency-Key": key }, signal
    });
  },
  run: (id: string, signal?: AbortSignal) => request<RunSnapshot>(`/runs/${id}`, { signal }),
  cancel: (id: string) => request(`/runs/${id}/cancel`, { method: "POST" }),
  async observe(id: string, signal: AbortSignal, update: (value: RunSnapshot) => void) {
    const response = await authenticatedFetch(`/api/chat/runs/${id}/events`, { signal });
    if (!response.ok || !response.body) throw new HistoryError("Couldn't reconnect to this reply.", response.status);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
        if (buffer.length > 4_000_000) throw new Error("Invalid chat stream.");
        let end: number;
        while ((end = buffer.indexOf("\n\n")) >= 0) {
          const frame = buffer.slice(0, end); buffer = buffer.slice(end + 2);
          const lines = frame.split("\n");
          const event = lines.find(line => line.startsWith("event:"))?.slice(6).trim();
          const data = lines.filter(line => line.startsWith("data:")).map(line => line.slice(5).trimStart()).join("\n");
          if (event === "error") throw new Error("This chat is no longer available. Refresh to reconnect.");
          if (event === "snapshot" && data) update(JSON.parse(data) as RunSnapshot);
        }
      }
    } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
  }
};
