import type { ChatConversation, ChatMessage } from "../../shared/state/useChatStore";

function finished(message: ChatMessage) {
  return message.status === "complete" || message.status === "stopped" || message.status === "failed";
}

// History requests and live snapshots arrive independently. Message IDs are
// immutable; a historical page must never roll back an already observed reply.
export function mergeChatHistory(current: ChatMessage[], incoming: ChatMessage[]): ChatMessage[] {
  const messages = new Map(current.map(message => [message.id, message]));
  for (const row of incoming) {
    const live = messages.get(row.id);
    const preserve = live?.role === "assistant" && (
      finished(live) || (!finished(row) && (
        live.content.length > row.content.length ||
        live.status === "streaming" && row.status === "waiting"
      ))
    );
    messages.set(row.id, preserve ? { ...row, ...live, position: row.position ?? live.position } : row);
  }
  // Keep local messages omitted by an older page, including snapshots that
  // already have server positions. Pagination adds older messages in order.
  const order = new Map<string, number>();
  let nextPosition = Number.MAX_SAFE_INTEGER;
  for (let index = current.length - 1; index >= 0; index--) {
    const message = messages.get(current[index].id)!;
    nextPosition = message.position ?? nextPosition - 1 / (current.length + 1);
    order.set(message.id, nextPosition);
  }
  // A submitted user message can lack a position even after its assistant
  // snapshot has one. Keep it ahead of that answer until history supplies it.
  return [...messages.values()].sort((a, b) =>
    (a.position ?? order.get(a.id) ?? Number.MAX_SAFE_INTEGER) -
    (b.position ?? order.get(b.id) ?? Number.MAX_SAFE_INTEGER));
}

export function reconcileRunId(chat: ChatConversation, incoming: string | null) {
  const active = chat.runId && !chat.settledRunIds?.includes(chat.runId) ? chat.runId : null;
  if (!incoming || chat.settledRunIds?.includes(incoming)) return active;
  return active ?? incoming;
}
