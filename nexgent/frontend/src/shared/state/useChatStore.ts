import { create } from "zustand";

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
}

interface ChatState {
  messages: ChatMessage[];
  errorMessage: string | null;
  appendMessage: (message: ChatMessage) => void;
  updateMessage: (id: string, content: string) => void;
  setErrorMessage: (message: string | null) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  errorMessage: null,
  appendMessage: (message) =>
    set((state) => ({ messages: [...state.messages, message] })),
  updateMessage: (id, content) =>
    set((state) => ({
      messages: state.messages.map((message) =>
        message.id === id ? { ...message, content } : message
      )
    })),
  setErrorMessage: (errorMessage) => set({ errorMessage })
}));
