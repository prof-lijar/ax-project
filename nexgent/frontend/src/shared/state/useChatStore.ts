import { create } from "zustand";

export type ChatRole = "user" | "assistant";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
}

interface ChatState {
  messages: ChatMessage[];
  appendMessage: (message: ChatMessage) => void;
  updateMessage: (id: string, content: string) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  appendMessage: (message) =>
    set((state) => ({ messages: [...state.messages, message] })),
  updateMessage: (id, content) =>
    set((state) => ({
      messages: state.messages.map((message) =>
        message.id === id ? { ...message, content } : message
      )
    }))
}));
