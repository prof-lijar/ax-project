import { useEffect } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAccount } from "../accounts/accountContext";
import { chatHistoryClient } from "../../shared/api/chatHistoryClient";
import { createConversation, useChatStore } from "../../shared/state/useChatStore";
import { useUiStore } from "../../shared/state/useUiStore";
import { HISTORY_CHANGED } from "./persistentChatRunner";
import type { ChatRunner } from "./chatRunner";

export function navigateChat(serverId?: string) {
  const path = serverId ? `/chat/${serverId}` : "/chat";
  if (window.location.pathname !== path) window.history.pushState(null, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}
export function useSavedChatHistory(runner: ChatRunner) {
  const account = useAccount();
  const cache = useQueryClient();
  const path = useUiStore(s => s.activePath);
  const chats = useChatStore(s => s.conversations);
  const activeId = useChatStore(s => s.activeId);
  const active = chats.find(c => c.id === activeId)!;
  const routeId = /^\/chat\/([0-9a-f-]{36})$/i.exec(path)?.[1];
  const serverId = routeId ?? active.serverId;
  const key = ["chat-history", account.id];
  const list = useInfiniteQuery({ queryKey: [...key, "list"], initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) => chatHistoryClient.list(pageParam, signal),
    getNextPageParam: page => page.next_cursor, refetchOnWindowFocus: true, retry: false });
  const detail = useQuery({ queryKey: [...key, "detail", serverId], enabled: !!serverId,
    queryFn: ({ signal }) => chatHistoryClient.get(serverId!, signal), retry: false });
  const messages = useInfiniteQuery({ queryKey: [...key, "messages", serverId], enabled: !!serverId,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) => chatHistoryClient.messages(serverId!, pageParam, signal),
    getNextPageParam: page => page.next_cursor, retry: false });

  useEffect(() => {
    const refresh = () => { void cache.invalidateQueries({ queryKey: ["chat-history", account.id] }); };
    window.addEventListener(HISTORY_CHANGED, refresh);
    return () => window.removeEventListener(HISTORY_CHANGED, refresh);
  }, [account.id, cache]);
  useEffect(() => {
    if (!routeId) return;
    const state = useChatStore.getState();
    let chat = state.conversations.find(c => c.serverId === routeId);
    if (!chat) {
      chat = { ...createConversation(), id: routeId, serverId: routeId };
      useChatStore.setState({ conversations: [...state.conversations, chat] });
    }
    state.selectChat(chat.id);
    useUiStore.setState({ selectedAgent: null });
  }, [routeId]);
  useEffect(() => {
    if (!list.data) return;
    const state = useChatStore.getState();
    const conversations = [...state.conversations];
    for (const row of list.data.pages.flatMap(p => p.items)) {
      const index = conversations.findIndex(c => c.serverId === row.id);
      const old = index >= 0 ? conversations[index] : { ...createConversation(), id: row.id, serverId: row.id };
      const next = { ...old, title: row.title, updatedAt: new Date(row.updated_at).getTime(), runId: row.active_run_id ?? old.runId };
      if (index >= 0) conversations[index] = next; else conversations.push(next);
    }
    useChatStore.setState({ conversations });
  }, [list.data]);
  useEffect(() => {
    if (!serverId || !detail.data || !messages.data) return;
    const state = useChatStore.getState();
    const chat = state.conversations.find(c => c.serverId === serverId);
    if (!chat) return;
    let rows = [...messages.data.pages].reverse().flatMap(p => p.items);
    if (chat.runId) {
      rows = rows.map(row => {
        const live = chat.messages.find(m => m.id === row.id);
        return live && live.role === "assistant" && (live.status === "streaming" || live.status === "complete") ? live : row;
      });
      const ids = new Set(rows.map(m => m.id));
      rows.push(...chat.messages.filter(m => !ids.has(m.id) && !m.position));
    }
    state.patchChat(chat.id, { title: detail.data.title, messages: rows, historyLoaded: true,
      runId: detail.data.active_run_id ?? chat.runId, updatedAt: new Date(detail.data.updated_at).getTime() });
    const runId = detail.data.active_run_id ?? chat.runId;
    if (runId) runner.watch?.(chat.id, runId);
  }, [serverId, detail.data, messages.data, runner]);

  return { list, detail, messages,
    loading: !!serverId && (!active.historyLoaded || routeId !== undefined && active.serverId !== routeId) && (detail.isPending || messages.isPending),
    error: detail.error ?? messages.error,
    refresh: () => { void cache.invalidateQueries({ queryKey: key }); }
  };
}
export type SavedChatHistory = ReturnType<typeof useSavedChatHistory>;
