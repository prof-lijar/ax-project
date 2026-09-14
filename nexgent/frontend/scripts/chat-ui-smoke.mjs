// Optional browser check. See docs/08-implementation/chat-session-ui-upgrade.md.
// Uses mocked existing HTTP responses; never calls a live chat service.
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
const { chromium } = await import(
  process.env.PLAYWRIGHT_MODULE ?? "playwright"
);
const baseURL = process.env.CHAT_UI_URL ?? "http://127.0.0.1:5187";
const artifacts =
  process.env.CHAT_UI_ARTIFACTS ?? "/tmp/nexgent-chat-ui-artifacts";
await mkdir(artifacts, { recursive: true });
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  permissions: ["clipboard-read", "clipboard-write"]
});
const page = await context.newPage();
page.setDefaultTimeout(10000);
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
await context.addInitScript(() => {
  const nativeFetch = window.fetch.bind(window);
  window.chatSmoke = { next: null, requests: [] };
  window.fetch = async (input, options = {}) => {
    const url = String(input);
    if (url.endsWith("/ok")) return new Response("true", { status: 200 });
    if (
      !url.includes("/api/chat/stream") &&
      !url.includes("/api/rag/chat/stream")
    ) {
      if (url.includes("/api/"))
        return new Response("{}", {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      return nativeFetch(input, options);
    }
    const config = window.chatSmoke.next ?? {
      chunks: ["Here is a useful reply."],
      delay: 30
    };
    window.chatSmoke.next = null;
    const prompt =
      options.body instanceof FormData
        ? options.body.get("prompt")
        : JSON.parse(options.body).question;
    const request = {
      url,
      prompt,
      files:
        options.body instanceof FormData
          ? options.body.getAll("files").map((file) => file.name)
          : [],
      finished: false,
      aborted: false
    };
    window.chatSmoke.requests.push(request);
    const encoder = new TextEncoder();
    let timer;
    return new Response(
      new ReadableStream({
        start(controller) {
          let index = 0;
          let response = "";
          let closed = false;
          function next() {
            if (closed) return;
            if (index < config.chunks.length) {
              const chunk = config.chunks[index++];
              response += chunk;
              controller.enqueue(
                encoder.encode(
                  `event: custom\ndata: ${JSON.stringify({ response_delta: chunk })}\n\n`
                )
              );
              timer = setTimeout(next, config.delay ?? 30);
            } else {
              closed = true;
              request.finished = true;
              if (config.fail)
                controller.error(new Error("Test connection lost"));
              else {
                controller.enqueue(
                  encoder.encode(
                    `event: values\ndata: ${JSON.stringify({ response })}\n\n`
                  )
                );
                controller.close();
              }
            }
          }
          options.signal?.addEventListener("abort", () => {
            request.aborted = true;
            clearTimeout(timer);
            if (!closed) {
              closed = true;
              controller.error(new DOMException("Aborted", "AbortError"));
            }
          });
          timer = setTimeout(next, config.delay ?? 30);
        },
        cancel() {
          clearTimeout(timer);
        }
      }),
      { headers: { "Content-Type": "text/event-stream" } }
    );
  };
});
const input = () => page.getByRole("textbox", { name: /^Message / });
const send = () =>
  page.getByRole("button", { name: "Send message", exact: true });
const configure = (config) =>
  page.evaluate((value) => {
    window.chatSmoke.next = value;
  }, config);
const requestCount = () =>
  page.evaluate(() => window.chatSmoke.requests.length);
async function newChat() {
  await page
    .getByRole("button", { name: "New chat", exact: true })
    .last()
    .click();
}
async function noOverflow() {
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth
    ),
    true,
    "No page horizontal overflow"
  );
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollHeight <= innerHeight
    ),
    true,
    "No page vertical overflow"
  );
}
try {
  await page.goto(`${baseURL}/chat`);
  await page.getByRole("heading", { name: "How can I help?" }).waitFor();
  await noOverflow();
  await page.screenshot({ path: `${artifacts}/chat-empty-1440.png` });
  assert.equal(await send().isDisabled(), true);
  await page
    .getByRole("button", { name: "Draft a message", exact: true })
    .click();
  assert.equal(await input().inputValue(), "Help me draft a message about ");
  assert.equal(await requestCount(), 0);
  await input().fill("First line");
  await input().press("Shift+Enter");
  await input().press("x");
  assert.equal(await input().inputValue(), "First line\nx");
  await input().dispatchEvent("keydown", {
    key: "Enter",
    code: "Enter",
    isComposing: true
  });
  assert.equal(await requestCount(), 0, "IME Enter must not send");
  await input().fill("Line\n".repeat(30));
  const height = await input().evaluate((element) => element.clientHeight);
  assert.ok(height >= 190 && height <= 200, "Composer height capped at 200px");

  // Stream into the original chat while a second chat holds its own draft.
  await configure({
    chunks: ["A partial reply", "\n\nThe final answer."],
    delay: 600
  });
  await input().fill("First conversation");
  await input().press("Enter");
  await page.getByRole("button", { name: "Stop response" }).waitFor();
  await newChat();
  await input().fill("Second draft");
  assert.equal(await send().isDisabled(), true);
  await page.getByRole("button", { name: "View chat", exact: true }).click();
  await page.getByText("The final answer.", { exact: true }).waitFor();
  await page
    .getByRole("button", { name: "Stop response" })
    .waitFor({ state: "hidden" });
  await page
    .getByRole("button", { name: "Copy message", exact: true })
    .last()
    .waitFor();
  await page
    .getByRole("button", { name: "Copy message", exact: true })
    .last()
    .click();
  assert.match(
    await page.evaluate(() => navigator.clipboard.readText()),
    /final answer/
  );
  await page
    .getByRole("button", { name: "New chat", exact: true })
    .first()
    .click();
  // A drafted second conversation must not be consumed by New chat.
  assert.equal(await input().inputValue(), "");
  await page
    .getByRole("navigation", { name: "Session conversations" })
    .getByRole("button", { name: "New chat", exact: true })
    .last()
    .click();
  assert.equal(await input().inputValue(), "Second draft");

  // Attachments, validation, prompt recovery and text-only co-workers.
  await page.locator('input[type="file"]').setInputFiles({
    name: "notes.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("notes")
  });
  await page.getByRole("button", { name: "Remove notes.txt" }).waitFor();
  await configure({ chunks: ["Partial response"], delay: 200, fail: true });
  await input().fill("Recover my prompt");
  await send().click();
  await input().fill("Keep my newer draft");
  await page.getByRole("button", { name: "Restore prompt" }).waitFor();
  await page.getByRole("button", { name: "Restore prompt" }).click();
  await page.getByRole("button", { name: "Keep draft", exact: true }).click();
  assert.equal(await input().inputValue(), "Keep my newer draft");
  await page.getByRole("button", { name: "Restore prompt" }).click();
  await page.getByRole("button", { name: "Replace", exact: true }).click();
  assert.equal(await input().inputValue(), "Recover my prompt");
  await page.getByRole("button", { name: "Remove notes.txt" }).waitFor();
  await page.getByLabel("Choose a co-worker for Chat").click();
  await page.getByRole("button", { name: /RAG Agent Grounded/ }).click();
  assert.equal(
    await page
      .getByRole("button", { name: "Attach files", exact: true })
      .isDisabled(),
    true
  );
  assert.equal(
    await page.getByRole("button", { name: "Remove notes.txt" }).count(),
    0
  );
  await send().click();
  await page
    .getByRole("button", { name: "Stop response" })
    .waitFor({ state: "hidden" });
  assert.match(
    await page.evaluate(() => window.chatSmoke.requests.at(-1).url),
    /rag\/chat\/stream/
  );
  await page.getByLabel("Choose a co-worker for Chat").click();
  await page.getByRole("button", { name: /AX Chat General questions/ }).click();
  await page.getByRole("button", { name: "Reuse prompt" }).last().click();
  assert.equal(await input().inputValue(), "Recover my prompt");

  // Long responses, code copy, table overflow and manual scrolling while streaming.
  const paragraphs = Array.from(
    { length: 25 },
    (_, index) =>
      `## Step ${index + 1}\n\nReview the current work and make the next decision.\n\n`
  ).join("");
  await configure({
    chunks: [
      paragraphs,
      "```ts\nconst answer = 42;\n```\n\n| Item | Result |\n| --- | --- |\n| " +
        "wide".repeat(80) +
        " | Ready |\n\n",
      "More detail.\n\n",
      "Finished."
    ],
    delay: 600
  });
  await input().fill("Long response");
  await send().click();
  await page.getByRole("heading", { name: "Step 25", exact: true }).waitFor();
  const transcript = page.getByRole("region", { name: "Chat transcript" });
  await transcript.evaluate((element) => {
    element.scrollTop = 0;
    element.dispatchEvent(new Event("scroll"));
  });
  await page.getByRole("button", { name: "Jump to latest" }).waitFor();
  await page.getByText("Finished.", { exact: true }).waitFor();
  assert.equal(
    await transcript.evaluate((element) => element.scrollTop),
    0,
    "Streaming must not pull the reader down"
  );
  await page.getByRole("button", { name: "Jump to latest" }).click();
  await page.getByRole("button", { name: "Copy code" }).click();
  assert.equal(
    await page.evaluate(() => navigator.clipboard.readText()),
    "const answer = 42;"
  );
  await noOverflow();
  await page.screenshot({ path: `${artifacts}/chat-conversation-1440.png` });

  // Explicit Stop preserves partial output; section navigation preserves drafts.
  await configure({ chunks: ["Keep partial", "Discard later"], delay: 500 });
  await input().fill("Stop this reply");
  await send().click();
  await page.getByText("Keep partial", { exact: true }).waitFor();
  await page.getByRole("button", { name: "Stop response" }).click();
  await page.getByText("Response stopped", { exact: true }).waitFor();
  assert.equal(
    await page.getByText("Discard later", { exact: true }).count(),
    0
  );
  await input().fill("Draft survives navigation");
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await page.getByRole("link", { name: "Chat", exact: true }).click();
  assert.equal(await input().inputValue(), "Draft survives navigation");

  // Rename and keep/cancel deletion are local conversation operations.
  await page
    .getByRole("button", { name: "Rename Recover my prompt", exact: true })
    .click();
  await page
    .getByRole("textbox", { name: "Conversation title" })
    .fill("Working notes");
  await page.getByRole("button", { name: "Save title" }).click();
  await page
    .getByRole("button", { name: "Working notes", exact: true })
    .waitFor();
  await page
    .getByRole("button", { name: "Delete Working notes", exact: true })
    .click();
  await page.getByRole("button", { name: "Keep", exact: true }).click();
  await page
    .getByRole("button", { name: "Working notes", exact: true })
    .waitFor();

  // File picker, drop, paste and preview cleanup; unsupported files preserve the draft.
  await newChat();
  await page.locator('input[type="file"]').setInputFiles({
    name: "unsupported.exe",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("test")
  });
  await page
    .getByRole("alert")
    .filter({ hasText: "not a supported attachment type" })
    .waitFor();
  await page
    .getByRole("button", { name: "Dismiss error", exact: true })
    .click();
  await input().evaluate((element) => {
    const transfer = new DataTransfer();
    transfer.items.add(
      new File(["dropped text"], "dropped.txt", { type: "text/plain" })
    );
    element.closest("form").dispatchEvent(
      new DragEvent("drop", {
        bubbles: true,
        cancelable: true,
        dataTransfer: transfer
      })
    );
  });
  await page
    .getByRole("button", { name: "Remove dropped.txt", exact: true })
    .waitFor();
  await page
    .getByRole("button", { name: "Remove dropped.txt", exact: true })
    .click();
  await input().evaluate((element) => {
    const png = Uint8Array.from(
      atob(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWioAAAAASUVORK5CYII="
      ),
      (c) => c.charCodeAt(0)
    );
    const transfer = new DataTransfer();
    transfer.items.add(new File([png], "pasted.png", { type: "image/png" }));
    element.dispatchEvent(
      new ClipboardEvent("paste", {
        bubbles: true,
        cancelable: true,
        clipboardData: transfer
      })
    );
  });
  await page
    .getByRole("button", { name: "Remove pasted.png", exact: true })
    .waitFor();
  assert.equal(await page.locator('img[src^="blob:"]').count(), 1);
  await page
    .getByRole("button", { name: "Remove pasted.png", exact: true })
    .click();
  assert.equal(await page.locator('img[src^="blob:"]').count(), 0);

  // Deleting the generating chat aborts its reply and leaves no late output.
  await configure({
    chunks: ["Disposable partial", "Disposable late"],
    delay: 500
  });
  await input().fill("Delete active stream");
  await send().click();
  await page.getByText("Disposable partial", { exact: true }).waitFor();
  await page
    .getByRole("button", { name: "Delete Delete active stream", exact: true })
    .click();
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  assert.equal(
    await page
      .getByRole("button", { name: "Delete active stream", exact: true })
      .count(),
    0
  );
  await page
    .getByRole("button", { name: "Working notes", exact: true })
    .click();
  // A response completes while Chat is unmounted, then renders on return.
  const beforeNavigation = await requestCount();
  await configure({
    chunks: ["Navigation partial", "\n\nNavigation complete"],
    delay: 500
  });
  await input().fill("Leave during reply");
  await send().click();
  await page.getByText("Navigation partial", { exact: true }).waitFor();
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await page.getByRole("heading", { name: "Coming Soon" }).waitFor();
  await page.waitForFunction(() => window.chatSmoke.requests.at(-1).finished);
  assert.equal(
    await page.evaluate(() => window.chatSmoke.requests.at(-1).aborted),
    false
  );
  await page.getByRole("link", { name: "Chat", exact: true }).click();
  await page.getByText("Navigation complete", { exact: true }).waitFor();
  assert.equal(
    await page.getByRole("button", { name: "Stop response" }).count(),
    0
  );
  assert.equal(
    await requestCount(),
    beforeNavigation + 1,
    "Returning must not restart the request"
  );

  // Native clipboard rejection falls back to selection-based copy.
  await page.evaluate(() => {
    navigator.clipboard.writeText = async () => {
      throw new Error("Denied");
    };
  });
  await page
    .getByRole("button", { name: "Copy message", exact: true })
    .last()
    .click();
  assert.equal(
    await page.evaluate(() => navigator.clipboard.readText()),
    "Navigation partial\n\nNavigation complete"
  );
  assert.equal(
    await page
      .getByRole("button", { name: "Copy message", exact: true })
      .last()
      .evaluate((element) => element === document.activeElement),
    true
  );
  // Simulate a plain-HTTP environment with no writeText API, for user text and code.
  await page.evaluate(() => {
    navigator.clipboard.writeText = undefined;
  });
  await page
    .getByRole("button", { name: "Copy message", exact: true })
    .nth(-2)
    .click();
  assert.equal(
    await page.evaluate(() => navigator.clipboard.readText()),
    "Leave during reply"
  );
  await page.getByRole("button", { name: "Copy code", exact: true }).click();
  assert.equal(
    await page.evaluate(() => navigator.clipboard.readText()),
    "const answer = 42;"
  );
  assert.equal(
    await page.locator("textarea[readonly]").count(),
    0,
    "Temporary copy field is removed"
  );
  // Report failure only if both browser mechanisms are blocked.
  await page.evaluate(() => {
    document.execCommand = () => false;
  });
  await page
    .getByRole("button", { name: "Copy message", exact: true })
    .last()
    .click();
  await page
    .getByText("Couldn't copy. Select the text to copy manually.", {
      exact: true
    })
    .waitFor();

  // Returning mid-stream reconnects Stop to the same request; browser history
  // and another menu must not create a second runner or cancel the first.
  await configure({
    chunks: ["Still responding", "Should be cancelled"],
    delay: 1500
  });
  await input().fill("Return before completion");
  await send().click();
  await page.getByText("Still responding", { exact: true }).waitFor();
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await page.goBack();
  await page.getByRole("button", { name: "Stop response" }).waitFor();
  assert.equal(
    await page.evaluate(() => window.chatSmoke.requests.at(-1).aborted),
    false
  );
  await page.getByRole("button", { name: "Stop response" }).click();
  assert.equal(
    await page.evaluate(() => window.chatSmoke.requests.at(-1).aborted),
    true
  );
  assert.equal(
    await page.getByText("Should be cancelled", { exact: true }).count(),
    0
  );

  // Failures occurring off-screen remain recoverable when returning to Chat.
  await configure({ chunks: ["Background partial"], delay: 500, fail: true });
  await input().fill("Background failure");
  await send().click();
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await page.waitForFunction(() => window.chatSmoke.requests.at(-1).finished);
  await page.getByRole("link", { name: "Chat", exact: true }).click();
  await page.getByRole("button", { name: "Restore prompt" }).waitFor();
  await page.getByRole("button", { name: "Restore prompt" }).click();
  assert.equal(await input().inputValue(), "Background failure");

  for (const width of [1024, 760]) {
    await page.setViewportSize({ width, height: 900 });
    await noOverflow();
    await page.getByRole("button", { name: "Toggle chat list" }).click();
    const dialog = page.getByRole("dialog", { name: "Chat conversations" });
    await dialog.waitFor();
    assert.equal(
      await dialog.evaluate((element) =>
        element.contains(document.activeElement)
      ),
      true
    );
    await page.keyboard.press("Shift+Tab");
    assert.equal(
      await dialog.evaluate((element) =>
        element.contains(document.activeElement)
      ),
      true
    );
    await page.keyboard.press("Escape");
    await dialog.waitFor({ state: "hidden" });
    assert.equal(
      await page
        .getByRole("button", { name: "Toggle chat list" })
        .evaluate((element) => element === document.activeElement),
      true
    );
    await page.screenshot({
      path: `${artifacts}/chat-conversation-${width}.png`
    });
  }
  await page.reload();
  await page.getByRole("heading", { name: "How can I help?" }).waitFor();
  assert.equal(await input().inputValue(), "");
  // A non-loopback HTTP origin actually has no secure Clipboard API.
  // Proxy only this test origin to the local Vite preview; no DNS setup needed.
  const insecurePage = await context.newPage();
  insecurePage.on("pageerror", (error) => errors.push(error.message));
  await insecurePage.route("http://nexgent-chat.test/**", async (route) => {
    const response = await route.fetch({
      url: route.request().url().replace("http://nexgent-chat.test", baseURL)
    });
    await route.fulfill({ response });
  });
  await insecurePage.goto("http://nexgent-chat.test/chat");
  await insecurePage
    .getByRole("heading", { name: "How can I help?" })
    .waitFor();
  assert.equal(
    await insecurePage.evaluate(() => window.isSecureContext),
    false
  );
  assert.equal(
    await insecurePage.evaluate(() => navigator.clipboard === undefined),
    true
  );
  await insecurePage
    .getByRole("textbox", { name: "Message AX", exact: true })
    .fill("Copy over plain HTTP");
  await insecurePage
    .getByRole("button", { name: "Send message", exact: true })
    .click();
  await insecurePage
    .getByText("Here is a useful reply.", { exact: true })
    .waitFor();
  await insecurePage
    .getByRole("button", { name: "Stop response" })
    .waitFor({ state: "hidden" });
  await insecurePage
    .getByRole("button", { name: "Copy message", exact: true })
    .last()
    .click();
  await page.bringToFront();
  assert.equal(
    await page.evaluate(() => navigator.clipboard.readText()),
    "Here is a useful reply."
  );
  await insecurePage.bringToFront();
  await insecurePage
    .getByRole("button", { name: "Copy message", exact: true })
    .first()
    .click();
  await page.bringToFront();
  assert.equal(
    await page.evaluate(() => navigator.clipboard.readText()),
    "Copy over plain HTTP"
  );
  await insecurePage.close();
  assert.deepEqual(errors, [], "No browser runtime errors");
  console.log(`Chat browser smoke checks passed. Screenshots: ${artifacts}`);
} catch (error) {
  await page.screenshot({ path: `${artifacts}/failure.png` });
  throw error;
} finally {
  await browser.close();
}
