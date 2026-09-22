// Exercises the real history hook, query cache, runner, and transcript.
import assert from "node:assert/strict";
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE ?? "playwright");
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/history-race-test", route => route.fulfill({
    contentType: "text/html", body: '<html><body><div id="fixture"></div></body></html>'
  }));
  await page.goto((process.env.CHAT_UI_URL ?? "http://127.0.0.1:5187") + "/history-race-test");
  const result = await page.evaluate(async () => {
    const { default: refresh } = await import("/@react-refresh");
    refresh.injectIntoGlobalHook(window);
    window.$RefreshReg$ = () => {};
    window.$RefreshSig$ = () => type => type;
    window.__vite_plugin_react_preamble_installed__ = true;
    const { createElement } = (await import("/node_modules/.vite/deps/react.js")).default;
    const { createRoot } = (await import("/node_modules/.vite/deps/react-dom_client.js")).default;
    const { flushSync } = (await import("/node_modules/.vite/deps/react-dom.js")).default;
    // Use the hook's versioned Vite import so both share the same context.
    const hookSource = await (await fetch("/src/features/chat/useSavedChatHistory.ts")).text();
    const queryModule = hookSource.match(/from "([^"]+@tanstack_react-query[^"]+)"/)[1];
    const { QueryClient, QueryClientProvider } = await import(queryModule);
    const { AccountContext } = await import("/src/features/accounts/accountContext.ts");
    const { useSavedChatHistory } = await import("/src/features/chat/useSavedChatHistory.ts");
    const { createPersistentChatRunner } = await import("/src/features/chat/persistentChatRunner.ts");
    const { chatHistoryClient } = await import("/src/shared/api/chatHistoryClient.ts");
    const { ChatTranscript } = await import("/src/features/chat/ChatTranscript.tsx");
    const { createConversation, useChatStore } = await import("/src/shared/state/useChatStore.ts");
    const chat = { ...createConversation(), serverId: "saved", runId: "run", historyLoaded: true,
      messages: [{ id: "answer", role: "assistant", content: "A complete SAT plan", status: "streaming", position: 2 }] };
    useChatStore.setState({ conversations: [chat], activeId: chat.id });
    // Completion invalidates these requests. Hold their results so detail and
    // message responses can be delivered independently, as on a real network.
    chatHistoryClient.list = chatHistoryClient.get = chatHistoryClient.messages = () => new Promise(() => {});
    const cache = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } });
    const key = ["chat-history", "account"];
    const detail = { id: "saved", title: "SAT", updated_at: "2026-09-22T00:00:00Z", active_run_id: "run" };
    const waiting = { ...chat.messages[0], content: "", status: "waiting" };
    const pages = items => ({ pages: [{ items, next_cursor: null }], pageParams: [null] });
    cache.setQueryData([...key, "list"], pages([detail]));
    cache.setQueryData([...key, "detail", "saved"], detail);
    cache.setQueryData([...key, "messages", "saved"], pages([waiting]));
    let push;
    let runReads = 0;
    const snapshot = { conversation_id: "saved", run_id: "run", assistant_message_id: "answer", user_message_id: "user",
      status: "running", revision: 1, cancel_requested: false, error_code: null, message: chat.messages[0] };
    const runner = createPersistentChatRunner({ ...chatHistoryClient,
      run: async () => { runReads++; return snapshot; },
      observe: (_id, signal, update) => { push = update; return new Promise(resolve => signal.addEventListener("abort", resolve)); }
    });
    function Fixture() {
      useSavedChatHistory(runner);
      const current = useChatStore(state => state.conversations[0]);
      return createElement(ChatTranscript, { conversation: current, onReuse() {} });
    }
    const root = createRoot(document.getElementById("fixture"));
    flushSync(() => root.render(createElement(QueryClientProvider, { client: cache },
      createElement(AccountContext.Provider, { value: { id: "account" } }, createElement(Fixture)))));
    const settle = () => new Promise(resolve => setTimeout(resolve, 80));
    for (let attempt = 0; !push && attempt < 30; attempt++) await settle();
    if (!push) throw new Error("Run observer did not start");
    flushSync(() => push({ ...snapshot, status: "completed", revision: 2,
      message: { ...snapshot.message, status: "complete" } }));
    // Metadata wins the race; the cache still contains the old empty message.
    cache.setQueryData([...key, "detail", "saved"], { ...detail, active_run_id: null });
    await settle();
    const afterDetail = useChatStore.getState().conversations[0];
    if (afterDetail.messages[0]?.content !== "A complete SAT plan" || afterDetail.messages[0]?.status !== "complete") {
      throw new Error("Completion was overwritten by stale waiting history: " + JSON.stringify(afterDetail.messages));
    }
    if (!document.querySelector("article")?.textContent.includes("A complete SAT plan")) throw new Error("The visible answer was cleared");
    // A late list response must not reactivate the finished run.
    cache.setQueryData([...key, "list"], pages([{ ...detail, title: "Late list" }]));
    await settle();
    if (useChatStore.getState().conversations[0].runId !== null) throw new Error("Stale list resurrected the run");
    cache.setQueryData([...key, "detail", "saved"], { ...detail, title: "Late detail" });
    await settle();
    if (useChatStore.getState().conversations[0].runId !== null || runReads !== 1) throw new Error("Stale detail restarted observation");
    cache.setQueryData([...key, "messages", "saved"], pages([{ ...snapshot.message, status: "complete" }]));
    await settle();
    if (document.querySelectorAll('article[aria-label="AX response"]').length !== 1) throw new Error("Duplicate answer rows");
    flushSync(() => root.unmount()); runner.detach(); cache.clear();
    return "PASS: completed answer survives stale history, late list/detail cannot restart it, final history keeps one response";
  });
  assert.deepEqual(errors, []);
  console.log(result);
} finally { await browser.close(); }
