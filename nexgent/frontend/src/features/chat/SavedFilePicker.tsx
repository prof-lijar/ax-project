import { useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useAccount } from "../accounts/accountContext";
import { chatHistoryClient } from "../../shared/api/chatHistoryClient";
import { useChatStore, type ChatConversation, type ChatAttachmentSummary } from "../../shared/state/useChatStore";
import styles from "./ChatPage.module.css";

export function selectSavedFile(chat: ChatConversation, file: ChatAttachmentSummary) {
  if (!file.id || chat.selectedFiles?.some(f => f.id === file.id)) return;
  const selected = [...(chat.selectedFiles ?? []), file];
  const all = [...chat.files, ...selected];
  const state = useChatStore.getState();
  if (all.length > 5 || all.reduce((sum, f) => sum + f.size, 0) > 25 * 1024 * 1024) {
    state.patchChat(chat.id, { error: "Select at most five files totaling 25 MiB." }); return;
  }
  state.patchChat(chat.id, { selectedFiles: selected, error: null });
}
export function SavedFilePicker({ conversation }: { conversation: ChatConversation }) {
  const [open, setOpen] = useState(false);
  const account = useAccount();
  const files = useInfiniteQuery({ queryKey: ["chat-history", account.id, "files", conversation.serverId],
    enabled: open && !!conversation.serverId, initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) => chatHistoryClient.files(conversation.serverId!, pageParam, signal),
    getNextPageParam: page => page.next_cursor, retry: false });
  return <details className={styles.savedFilePicker} onToggle={e => setOpen(e.currentTarget.open)}>
    <summary>Use a saved file</summary>
    {open && <div>
      {files.isPending && <p role="status">Loading files…</p>}
      {files.isError && <p role="alert">Couldn't load files. <button type="button" onClick={() => void files.refetch()}>Retry</button></p>}
      {files.data && !files.data.pages[0].items.length && <p>No saved files in this chat.</p>}
      {files.data?.pages.flatMap(page => page.items).map(file => <div key={file.id}>
        <button type="button" disabled={conversation.selectedFiles?.some(f => f.id === file.id)}
          onClick={() => selectSavedFile(conversation, file)}>{file.name}</button>
      </div>)}
      {files.hasNextPage && <button type="button" disabled={files.isFetchingNextPage} onClick={() => void files.fetchNextPage()}>More files</button>}
    </div>}
  </details>;
}
