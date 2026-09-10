import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
const { chromium } = await import(
  process.env.PLAYWRIGHT_MODULE ?? "playwright"
);
const baseURL = process.env.AGENTS_UI_URL ?? "http://127.0.0.1:5187";
const artifacts =
  process.env.AGENTS_UI_ARTIFACTS ?? "/tmp/nexgent-agents-ui-artifacts";
await mkdir(artifacts, { recursive: true });
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.setDefaultTimeout(10000);
const errors = [];
const mutations = [];
page.on("pageerror", (error) => errors.push(error.message));
await page.route(
  /\/(?:api|weekly-report-bulk-api|scout-api|agent-server)\//,
  async (route) => {
    if (!["fetch", "xhr"].includes(route.request().resourceType())) {
      await route.continue();
      return;
    }
    if (!["GET", "HEAD", "OPTIONS"].includes(route.request().method()))
      mutations.push(route.request().url());
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        detail: "Service unavailable during UI-only check"
      })
    });
  }
);
await page.route("**/ok", (route) =>
  route.fulfill({ status: 200, body: "true" })
);
try {
  await page.goto(`${baseURL}/agents`);
  await page.getByRole("heading", { name: "Your co-workers" }).waitFor();
  const cards = () =>
    page
      .getByRole("list", { name: "Co-workers", exact: true })
      .locator(":scope > article");
  const search = page.getByRole("searchbox", { name: "Find a co-worker" });
  assert.equal(await cards().count(), 3);
  assert.equal(await page.getByText("Google ADK", { exact: true }).count(), 0);
  await search.fill("zip");
  assert.equal(await cards().count(), 1);
  await page
    .getByRole("heading", { name: "Weekly Reporter", exact: true })
    .waitFor();
  await search.press("Escape");
  assert.equal(await search.inputValue(), "");
  assert.equal(await cards().count(), 3);
  await search.fill("sources");
  assert.equal(await cards().count(), 2);
  await search.fill("no-such-coworker");
  await page.getByRole("heading", { name: "No co-workers found" }).waitFor();
  await page
    .getByRole("button", { name: "Clear search", exact: true })
    .last()
    .click();
  assert.equal(await cards().count(), 3);
  assert.equal(
    await search.evaluate((element) => element === document.activeElement),
    true
  );

  for (const width of [1440, 1024, 760]) {
    await page.setViewportSize({ width, height: 900 });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth
      ),
      true,
      `No overflow at ${width}`
    );
    for (const card of await cards().all()) {
      assert.equal(
        await card.evaluate(
          (element) => element.scrollWidth <= element.clientWidth
        ),
        true,
        "Card content fits"
      );
    }
    await page.screenshot({ path: `${artifacts}/agents-${width}.png` });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page
    .getByRole("button", { name: "Start chat with RAG Agent", exact: true })
    .click();
  await page.waitForURL("**/chat");
  await page
    .getByRole("textbox", { name: "Message RAG Agent", exact: true })
    .waitFor();
  assert.equal(
    await page
      .getByRole("button", { name: "Attach files", exact: true })
      .isDisabled(),
    true
  );
  await page.getByRole("link", { name: "Agents", exact: true }).click();
  await page.getByText("Selected in Chat", { exact: true }).waitFor();
  await page
    .getByRole("link", { name: "View RAG Agent details", exact: true })
    .click();
  await page.waitForURL("**/agents/7");
  await page.goBack();
  const weekly = page.getByRole("link", {
    name: "Open Weekly Reporter workspace",
    exact: true
  });
  await weekly.focus();
  await page.keyboard.press("Enter");
  await page.waitForURL("**/agents/1");
  await page.goBack();
  await page
    .getByRole("link", {
      name: "Open AnsimK Scout Agent workspace",
      exact: true
    })
    .click();
  await page.waitForURL("**/agents/ansimk_scout_agent");
  await page.goBack();
  await page
    .getByRole("heading", { name: "Your co-workers", exact: true })
    .waitFor();
  assert.deepEqual(
    mutations,
    [],
    "Navigation must not launch work or send messages"
  );
  assert.deepEqual(errors, [], "No browser runtime errors");
  console.log(`Agents UI checks passed. Screenshots: ${artifacts}`);
} catch (error) {
  await page.screenshot({ path: `${artifacts}/failure.png` });
  throw error;
} finally {
  await browser.close();
}
