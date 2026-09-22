// Deterministic browser regression for the actual transcript and animation hook.
// Run against Vite; no backend or signed-in account is required.
import assert from "node:assert/strict";
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE ?? "playwright");
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/streaming-test", route => route.fulfill({
    contentType: "text/html", body: '<html><body><div id="fixture"></div></body></html>'
  }));
  await page.goto((process.env.CHAT_UI_URL ?? "http://127.0.0.1:5187") + "/streaming-test");
  const results = await page.evaluate(async () => {
    const { default: refresh } = await import("/@react-refresh");
    refresh.injectIntoGlobalHook(window);
    window.$RefreshReg$ = () => {};
    window.$RefreshSig$ = () => type => type;
    window.__vite_plugin_react_preamble_installed__ = true;
    const { createElement, StrictMode } = (await import("/node_modules/.vite/deps/react.js")).default;
    const { createRoot } = (await import("/node_modules/.vite/deps/react-dom_client.js")).default;
    const { flushSync } = (await import("/node_modules/.vite/deps/react-dom.js")).default;
    const { ChatTranscript } = await import("/src/features/chat/ChatTranscript.tsx");
    const { createConversation, useChatStore } = await import("/src/shared/state/useChatStore.ts");
    const frames = new Map();
    let sequence = 0, now = 0;
    window.requestAnimationFrame = callback => { frames.set(++sequence, callback); return sequence; };
    window.cancelAnimationFrame = id => frames.delete(id);
    const root = createRoot(document.getElementById("fixture"));
    let chat = createConversation();
    function render(content, status, id = "reply") {
      chat = { ...chat, messages: [{ id, content, status, role: "assistant" }] };
      useChatStore.setState({ conversations: [chat], activeId: chat.id });
      flushSync(() => root.render(createElement(StrictMode, null,
        createElement(ChatTranscript, { key: chat.id, conversation: chat, onReuse() {} }))));
    }
    function tick() {
      now += 17;
      const pending = [...frames.values()]; frames.clear();
      flushSync(() => pending.forEach(callback => callback(now)));
    }
    const text = () => document.querySelector("article p")?.textContent ?? "";
    const check = (ok, name) => { if (!ok) throw new Error(name); results.push(name); };
    const results = [];
    render("", "waiting");
    check(!document.body.textContent.includes("Thinking") &&
      document.querySelector('article[aria-label="Waiting for AX"]') !== null,
      "waiting is a quiet state, not a second response");
    render("Hello world", "streaming");
    check(text() === "", "a server chunk is buffered");
    const prefixes = [];
    for (let i = 0; i < 5; i++) { tick(); prefixes.push(text()); }
    check(JSON.stringify(prefixes) === JSON.stringify(["H", "He", "Hel", "Hell", "Hello"]), "words reveal character by character");
    render("Hello world!", "complete");
    check(text() === "Hello" && !document.body.textContent.includes("Reply complete."), "completion does not dump the final chunk");
    for (let i = 0; i < 20; i++) tick();
    check(text() === "Hello world!" && document.body.textContent.includes("Reply complete."), "the full reply completes exactly");
    check(frames.size === 0, "idle replies leave no animation scheduled");
    render("Saved history", "complete", "saved");
    check(text() === "Saved history" && frames.size === 0, "saved history renders immediately");
    render("Existing prefix", "streaming", "rejoined");
    check(text() === "Existing prefix", "rejoined streams keep their existing prefix");
    render("", "waiting", "unicode");
    render("👩🏽‍💻e\u0301한글", "streaming", "unicode");
    tick(); check(text() === "👩🏽‍💻", "emoji remain whole");
    tick(); check(text() === "👩🏽‍💻e\u0301", "combining characters remain whole");
    render("Corrected answer", "complete", "unicode");
    check(text() === "Corrected answer", "authoritative replacements reconcile immediately");
    render(String.raw`Solve $x$ using $\frac{a}{b}$.

| Type | Formula |
| --- | --- |
| Quadratic | $b^2 - 4ac$ |

$$
\frac{-b \pm \sqrt{b^2-4ac}}{2a}
$$`, "complete", "math");
    const math = document.querySelector("math");
    check(document.querySelectorAll("math").length === 4 &&
      math?.namespaceURI === "http://www.w3.org/1998/Math/MathML",
      "inline, table and display formulas render as native MathML");
    const fraction = document.querySelector("mfrac");
    const numerator = fraction.children[0].getBoundingClientRect();
    const denominator = fraction.children[1].getBoundingClientRect();
    check(numerator.top < denominator.top && numerator.height > 0,
      "the browser typesets a stacked fraction");
    check(document.querySelector('math[display="block"]') !== null &&
      !document.querySelector(".katex-error"), "display formulas render without errors");
    for (const status of ["stopped", "failed"]) {
      render("", "waiting", status);
      render("Partial response", "streaming", status); tick();
      render("Partial response", status, status);
      check(text() === "Partial response" && frames.size === 0, `${status} preserves received text and cancels animation`);
    }
    render("", "waiting", "scroll");
    const viewport = document.querySelector('section[aria-label="Chat transcript"]');
    viewport.style.height = "80px"; viewport.style.overflow = "auto";
    render("line\n\n".repeat(60), "streaming", "scroll");
    for (let i = 0; i < 90; i++) tick();
    check(viewport.scrollHeight > viewport.clientHeight && viewport.scrollHeight - viewport.clientHeight - viewport.scrollTop < 2, "revealed text follows the bottom");
    useChatStore.getState().patchChat(chat.id, { following: false }); viewport.scrollTop = 0;
    for (let i = 0; i < 10; i++) tick();
    check(viewport.scrollTop === 0, "reading earlier text is not interrupted");
    flushSync(() => root.unmount());
    check(frames.size === 0, "unmount cancels pending frames");
    return results;
  });
  assert.deepEqual(errors, []);
  console.log(`PASS: ${results.length} streaming browser checks\n${results.join("\n")}`);
} finally { await browser.close(); }
