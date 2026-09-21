// Opt-in real HTTP/DB/worker browser check using backend/tests/chat_smoke_server.py.
// Requires the isolated fixture stack documented in persistent-ax-chat-history.md.
import assert from "node:assert/strict";
import { mkdir, readFile } from "node:fs/promises";
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE ?? "playwright");
const origin = process.env.CHAT_UI_URL ?? "http://127.0.0.1:58173";
const artifacts = process.env.CHAT_UI_ARTIFACTS ?? "/tmp/nexgent-saved-chat-ui-artifacts";
await mkdir(artifacts, { recursive: true });
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
let page = await context.newPage();
const errors = [];
context.on("page", p => p.on("pageerror", error => errors.push(error.message)));
page.on("pageerror", error => errors.push(error.message));
page.setDefaultTimeout(15000);
async function login(target, name) {
  await target.getByLabel("Username", { exact: true }).fill(name);
  await target.getByLabel("Password", { exact: true }).fill("smoke-test");
  await target.getByRole("button", { name: "Sign in", exact: true }).click();
}
const input = () => page.getByRole("textbox", { name: "Message AX", exact: true });
async function send(prompt) {
  await input().fill(prompt);
  await page.getByRole("button", { name: "Send message", exact: true }).click();
}
try {
  await page.goto(origin + "/chat"); await login(page, "alice");
  await page.locator('input[type="file"]').setInputFiles({ name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("Original file\r\ncontents") });
  await send("remember my saved file");
  await page.getByText("Reply to: remember my saved file | History: 0 | Files: 1", { exact: true }).waitFor();
  await page.getByRole("link", { name: "Download", exact: true }).waitFor();
  const chatURL = page.url();
  assert.match(chatURL, /\/chat\/[0-9a-f-]{36}$/);
  const fileURL = await page.getByRole("link", { name: "Download", exact: true }).getAttribute("href");
  const downloadWait = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download", exact: true }).click();
  const download = await downloadWait;
  assert.equal(await readFile(await download.path(), "utf8"), "Original file\r\ncontents");
  await page.reload();
  await page.getByText("Reply to: remember my saved file | History: 0 | Files: 1", { exact: true }).waitFor();
  await page.getByRole("button", { name: "Use again", exact: true }).click();
  await send("use the file again");
  await page.getByText("Reply to: use the file again | History: 1 | Files: 1", { exact: true }).waitFor();
  await page.getByRole("button", { name: "Stop response", exact: true }).waitFor({ state: "hidden" });
  await page.getByRole("button", { name: "Rename remember my saved file", exact: true }).click();
  await page.getByRole("textbox", { name: "Conversation title" }).fill("Saved work");
  await page.getByRole("button", { name: "Save title", exact: true }).click();
  await page.getByRole("button", { name: "Saved work", exact: true }).waitFor();
  await send("slow finish while closed");
  await page.getByRole("button", { name: "Stop response", exact: true }).waitFor();
  await page.close();
  page = await context.newPage(); page.setDefaultTimeout(15000);
  await page.goto(chatURL);
  await page.getByText("Reply to: slow finish while closed | History: 2 | Files: 0", { exact: true }).waitFor();
  await page.getByRole("button", { name: "Stop response", exact: true }).waitFor({ state: "hidden" });
  await page.getByRole("button", { name: "Saved work", exact: true }).waitFor();

  const otherContext = await browser.newContext(); const other = await otherContext.newPage();
  await other.goto(chatURL); await login(other, "bob");
  await other.getByText("This conversation or file is unavailable.", { exact: true }).waitFor();
  assert.equal(await other.getByText("remember my saved file", { exact: true }).count(), 0);
  assert.equal((await otherContext.request.get(origin + fileURL)).status(), 404);
  await otherContext.close();

  await send("slow stop explicitly");
  await page.getByRole("button", { name: "Stop response", exact: true }).click();
  await page.getByRole("button", { name: "Stop response", exact: true }).waitFor({ state: "hidden" });
  await page.getByText("Response stopped", { exact: true }).waitFor();
  await page.setViewportSize({ width: 860, height: 800 });
  await page.screenshot({ path: artifacts + "/saved-chat-narrow.png", fullPage: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({ path: artifacts + "/saved-chat-desktop.png", fullPage: true });
  await page.getByRole("button", { name: "Delete Saved work", exact: true }).click();
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await page.getByRole("button", { name: "Saved work", exact: true }).waitFor({ state: "hidden" });
  await page.reload();
  assert.equal(await page.getByRole("button", { name: "Saved work", exact: true }).count(), 0);
  assert.equal((await context.request.get(origin + fileURL)).status(), 404);
  assert.deepEqual(errors, []);
  console.log("PASS: persistence, file download/reuse, rename, close/rejoin, account isolation, Stop, delete, responsive rendering");
} finally { await browser.close(); }
