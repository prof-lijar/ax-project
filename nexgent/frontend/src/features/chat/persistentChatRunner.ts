import { chatHistoryClient, HistoryError, type RunSnapshot } from "../../shared/api/chatHistoryClient";
import { RAG_CHAT_GRAPH_ID } from "../../shared/api/agentCatalogClient";
import { chatId, useChatStore } from "../../shared/state/useChatStore";
import { createChatRunner, type ChatRunner } from "./chatRunner";
import { toAttachmentSummary } from "./chatAttachments";

export const HISTORY_CHANGED = "nexgent-chat-history-changed";
export function historyChanged() { window.dispatchEvent(new Event(HISTORY_CHANGED)); }
const terminal = (status: string) => !["queued", "running"].includes(status);

export function createPersistentChatRunner(client = chatHistoryClient): ChatRunner {
  const rag = createChatRunner();
  const observers = new Map<string, AbortController>();
  const submissions = new Map<string, AbortController>();
  let generation = 0;
  function watch(id: string, runId: string) {
    const chat = useChatStore.getState().conversations.find(c => c.id === id);
    if (observers.has(id) || chat?.settledRunIds?.includes(runId)) return;
    const controller = new AbortController();
    observers.set(id, controller);
    let revision = -1, finished = false;
    const update = (value: RunSnapshot) => {
      if (controller.signal.aborted || value.run_id !== runId || value.revision < revision) return;
      const state = useChatStore.getState();
      const chat = state.conversations.find(c => c.id === id);
      if (!chat || chat.runId !== runId) return;
      revision = value.revision;
      const found = chat.messages.some(m => m.id === value.message.id);
      if (found) state.updateMessage(id, value.message.id, value.message);
      else state.appendMessage(id, value.message);
      if (terminal(value.status)) {
        finished = true;
        state.patchChat(id, { runId: null,
          settledRunIds: [...new Set([...(chat.settledRunIds ?? []), runId])],
          error: ["failed", "interrupted"].includes(value.status) ? "Reply interrupted. Your messages are saved; reuse your prompt to try again." : null,
          notice: value.status === "stopped" ? "Response stopped." : null });
        historyChanged();
      }
    };
    void (async () => {
      try {
        for (let attempt = 0; !finished && !controller.signal.aborted; attempt++) {
          try {
            update(await client.run(runId, controller.signal));
            if (!finished) await client.observe(runId, controller.signal, update);
          } catch (error) {
            if (controller.signal.aborted) return;
            if (error instanceof HistoryError && [401, 404].includes(error.status)) throw error;
          }
          if (!finished) {
            if (attempt >= 5) throw new Error("Connection interrupted. Refresh this chat to reconnect; the reply may still be running.");
            await new Promise<void>(resolve => {
              const timer = setTimeout(resolve, Math.min(1000 * 2 ** attempt, 10000));
              controller.signal.addEventListener("abort", () => { clearTimeout(timer); resolve(); }, { once: true });
            });
          }
        }
      } catch (error) {
        if (!controller.signal.aborted) useChatStore.getState().patchChat(id, { error: (error as Error).message });
      } finally { if (observers.get(id) === controller) observers.delete(id); }
    })();
  }
  async function send(id: string) {
    const state = useChatStore.getState();
    const chat = state.conversations.find(c => c.id === id);
    if (!chat) return;
    if (chat.agent?.graphId === RAG_CHAT_GRAPH_ID) return rag.send(id);
    if (chat.runId || chat.submitting || !chat.draft.trim()) return;
    const epoch = generation, prompt = chat.draft.trim(), files = chat.files;
    const selected = chat.selectedFiles ?? [];
    const signature = JSON.stringify([prompt, files.map(f => [f.name, f.size, f.lastModified]), selected.map(f => f.id)]);
    const key = chat.submissionSignature === signature && chat.submissionKey ? chat.submissionKey : chat.sessionId + "-" + chatId();
    const controller = new AbortController(); submissions.set(id, controller);
    state.patchChat(id, { submitting: true, error: null, notice: null, submissionKey: key, submissionSignature: signature });
    try {
      const result = await client.submit(chat.serverId, prompt, files, selected.map(f => f.id!), key, controller.signal);
      if (generation !== epoch || controller.signal.aborted) return;
      const current = useChatStore.getState();
      const updated = current.conversations.find(c => c.id === id);
      if (!updated) return;
      current.patchChat(id, { serverId: result.conversation_id, runId: result.run_id,
        submitting: false, draft: updated.draft === chat.draft ? "" : updated.draft,
        files: updated.files === files ? [] : updated.files, selectedFiles: [],
        submissionKey: undefined, submissionSignature: undefined, historyLoaded: true, following: true });
      if (!updated.messages.some(m => m.id === result.user_message_id)) {
        current.appendMessage(id, { id: result.user_message_id, role: "user", content: prompt,
          attachments: [...files.map(toAttachmentSummary), ...selected], status: "complete" });
        current.appendMessage(id, { id: result.assistant_message_id, role: "assistant", content: "", status: "waiting" });
      }
      if (current.activeId === id && window.location.pathname.startsWith("/chat")) {
        window.history.replaceState(null, "", `/chat/${result.conversation_id}`);
        window.dispatchEvent(new PopStateEvent("popstate"));
      }
      historyChanged(); watch(id, result.run_id);
    } catch (error) {
      if (generation === epoch && !controller.signal.aborted) {
        useChatStore.getState().patchChat(id, { submitting: false, error: (error as Error).message });
      }
    } finally { if (submissions.get(id) === controller) submissions.delete(id); }
  }
  function stop(id = useChatStore.getState().activeId) {
    const chat = useChatStore.getState().conversations.find(c => c.id === id);
    if (!chat?.runId) { rag.stop(); return; }
    void client.cancel(chat.runId).then(() => {
      useChatStore.getState().patchChat(id, { notice: "Stopping response…" });
      watch(id, chat.runId!);
    }).catch(error => useChatStore.getState().patchChat(id, { error: error.message }));
  }
  function detach() {
    generation++;
    observers.forEach(c => c.abort()); submissions.forEach(c => c.abort());
    observers.clear(); submissions.clear(); rag.detach();
  }
  return { send, stop, detach, watch };
}
