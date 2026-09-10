import { create } from "zustand";
import { RAG_CHAT_GRAPH_ID } from "../api/agentCatalogClient";
import type { AgentDefinition } from "../types/agents";

export type ChatRole = "user" | "assistant";
export interface ChatAttachmentSummary {
  name: string;
  size: number;
  type: string;
}
export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  attachments?: ChatAttachmentSummary[];
  speaker?: string;
  status?: "waiting" | "streaming" | "complete" | "stopped" | "failed";
}
export interface ChatConversation {
  id: string;
  title: string;
  renamed: boolean;
  messages: ChatMessage[];
  agent: AgentDefinition | null;
  draft: string;
  files: File[];
  error: string | null;
  notice: string | null;
  recovery: { prompt: string; files: File[] } | null;
  scrollTop: number;
  following: boolean;
  updatedAt: number;
}
let sequence = 0;
export function chatId() {
  return `chat-${Date.now()}-${++sequence}`;
}
export function createConversation(
  agent: AgentDefinition | null = null
): ChatConversation {
  return {
    id: chatId(),
    title: "New chat",
    renamed: false,
    messages: [],
    agent,
    draft: "",
    files: [],
    error: null,
    notice: null,
    recovery: null,
    scrollTop: 0,
    following: true,
    updatedAt: Date.now()
  };
}
interface ChatState {
  conversations: ChatConversation[];
  activeId: string;
  activeRequest: { conversationId: string; messageId: string } | null;
  newChat: (agent?: AgentDefinition | null) => string;
  selectChat: (id: string) => void;
  deleteChat: (id: string) => void;
  renameChat: (id: string, title: string) => void;
  patchChat: (id: string, patch: Partial<ChatConversation>) => void;
  appendMessage: (id: string, message: ChatMessage) => void;
  updateMessage: (
    id: string,
    messageId: string,
    patch: Partial<ChatMessage>
  ) => void;
  chooseAgent: (id: string, agent: AgentDefinition | null) => void;
}
const initial = createConversation();
export const useChatStore = create<ChatState>((set, get) => ({
  conversations: [initial],
  activeId: initial.id,
  activeRequest: null,
  patchChat: (id, patch) =>
    set((state) => ({
      conversations: state.conversations.map((c) =>
        c.id === id ? { ...c, ...patch } : c
      )
    })),
  newChat: (agent = null) => {
    const empty = get().conversations.find(
      (c) =>
        !c.messages.length &&
        !c.draft &&
        !c.files.length &&
        c.agent?.id === agent?.id
    );
    const conversation = empty ?? createConversation(agent);
    set((state) => ({
      activeId: conversation.id,
      conversations: empty
        ? state.conversations
        : [conversation, ...state.conversations]
    }));
    return conversation.id;
  },
  selectChat: (id) => {
    if (get().conversations.some((c) => c.id === id)) {
      get().patchChat(id, { updatedAt: Date.now() });
      set({ activeId: id });
    }
  },
  deleteChat: (id) =>
    set((state) => {
      let conversations = state.conversations.filter((c) => c.id !== id);
      if (!conversations.length) conversations = [createConversation()];
      return {
        conversations,
        activeId:
          state.activeId === id
            ? [...conversations].sort((a, b) => b.updatedAt - a.updatedAt)[0].id
            : state.activeId
      };
    }),
  renameChat: (id, title) => {
    if (title.trim())
      get().patchChat(id, { title: title.trim().slice(0, 120), renamed: true });
  },
  appendMessage: (id, message) =>
    set((state) => ({
      conversations: state.conversations.map((c) =>
        c.id !== id
          ? c
          : {
              ...c,
              messages: [...c.messages, message],
              updatedAt: Date.now(),
              title:
                message.role === "user" && !c.messages.length && !c.renamed
                  ? message.content.trim().replace(/\s+/g, " ").slice(0, 48)
                  : c.title
            }
      )
    })),
  updateMessage: (id, messageId, patch) =>
    set((state) => ({
      conversations: state.conversations.map((c) =>
        c.id !== id
          ? c
          : {
              ...c,
              messages: c.messages.map((m) =>
                m.id === messageId ? { ...m, ...patch } : m
              )
            }
      )
    })),
  chooseAgent: (id, agent) => {
    const conversation = get().conversations.find((c) => c.id === id);
    const textOnly = agent?.graphId === RAG_CHAT_GRAPH_ID;
    get().patchChat(id, {
      agent,
      ...(textOnly && conversation?.files.length
        ? {
            files: [],
            notice: "Attachments removed. RAG Agent supports text only."
          }
        : {})
    });
  }
}));
