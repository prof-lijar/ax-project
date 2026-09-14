import {
  agentServerClient,
  AgentServerError
} from "../../shared/api/agentServerClient";
import { RAG_CHAT_GRAPH_ID } from "../../shared/api/agentCatalogClient";
import { chatId, useChatStore } from "../../shared/state/useChatStore";
import { toAttachmentSummary } from "./chatAttachments";

export type ChatRunner = ReturnType<typeof createChatRunner>;

// The app owns this runner across menu changes. Every callback is scoped
// to its request, so cancellation/deletion cannot resurrect a stale response.
export function createChatRunner(client = agentServerClient) {
  let active: {
    controller: AbortController;
    conversationId: string;
    messageId: string;
  } | null = null;
  function stop() {
    if (!active) return;
    const request = active;
    active = null;
    request.controller.abort();
    const state = useChatStore.getState();
    state.updateMessage(request.conversationId, request.messageId, {
      status: "stopped"
    });
    state.patchChat(request.conversationId, { notice: null });
    useChatStore.setState({ activeRequest: null });
  }
  async function send(conversationId: string) {
    const state = useChatStore.getState();
    const conversation = state.conversations.find(
      (c) => c.id === conversationId
    );
    if (state.activeRequest || !conversation?.draft.trim()) return;
    const prompt = conversation.draft.trim();
    const rag = conversation.agent?.graphId === RAG_CHAT_GRAPH_ID;
    const files = rag ? [] : conversation.files;
    const request = {
      controller: new AbortController(),
      conversationId,
      messageId: chatId()
    };
    active = request;
    useChatStore.setState({
      activeRequest: { conversationId, messageId: request.messageId }
    });
    state.patchChat(conversationId, {
      draft: "",
      files: [],
      error: null,
      notice: null,
      recovery: null,
      following: true
    });
    state.appendMessage(conversationId, {
      id: chatId(),
      role: "user",
      content: prompt,
      attachments: files.map(toAttachmentSummary)
    });
    state.appendMessage(conversationId, {
      id: request.messageId,
      role: "assistant",
      content: "",
      speaker: conversation.agent?.name ?? "AX",
      status: "waiting"
    });
    const isCurrent = () =>
      active === request &&
      useChatStore
        .getState()
        .conversations.some((c) => c.id === conversationId);
    try {
      const options = {
        signal: request.controller.signal,
        onResponse: (content: string) => {
          if (isCurrent())
            useChatStore
              .getState()
              .updateMessage(conversationId, request.messageId, {
                content,
                status: content ? "streaming" : "waiting"
              });
        }
      };
      const response = rag
        ? await client.streamRagChat(prompt, options)
        : await client.streamChat(prompt, {
            ...options,
            files,
            sessionId: conversation.sessionId
          });
      if (isCurrent())
        useChatStore
          .getState()
          .updateMessage(conversationId, request.messageId, {
            content: response,
            status: "complete"
          });
    } catch (error) {
      if (!isCurrent()) return;
      const cancelled =
        request.controller.signal.aborted ||
        (error instanceof AgentServerError && error.code === "cancelled");
      useChatStore.getState().updateMessage(conversationId, request.messageId, {
        status: cancelled ? "stopped" : "failed"
      });
      useChatStore.getState().patchChat(
        conversationId,
        cancelled
          ? { notice: null }
          : {
              error:
                error instanceof Error
                  ? error.message
                  : "Couldn't complete this reply. Please try again.",
              recovery: { prompt, files }
            }
      );
    } finally {
      if (active === request) {
        active = null;
        useChatStore.setState({ activeRequest: null });
      }
    }
  }
  return { send, stop };
}
