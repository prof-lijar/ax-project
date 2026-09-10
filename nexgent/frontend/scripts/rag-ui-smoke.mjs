import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
const { chromium } = await import(
  process.env.PLAYWRIGHT_MODULE ?? "playwright"
);
const baseURL = process.env.RAG_UI_URL ?? "http://127.0.0.1:5187";
const artifacts =
  process.env.RAG_UI_ARTIFACTS ?? "/tmp/nexgent-rag-ui-artifacts";
await mkdir(artifacts, { recursive: true });
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
page.setDefaultTimeout(10000);
const errors = [],
  requests = [];
let documents = 2,
  passages = 80,
  failEmbed = false,
  failDelete = false,
  emptySearch = false;
page.on("pageerror", (error) => errors.push(error.message));
// Intercept every RAG request, including all writes/deletions: no live data touched.
await page.route("**/rag/v1/**", async (route) => {
  const request = route.request(),
    url = new URL(request.url());
  requests.push({
    method: request.method(),
    path: url.pathname,
    query: url.searchParams.get("query"),
    topK: url.searchParams.get("top_k"),
    body: request.postData()
  });
  let data;
  if (url.pathname.endsWith("/data/stats"))
    data = {
      document_rows: documents,
      embedding_rows: passages,
      legacy_embedding_rows: 0,
      provenance_embedding_rows: passages
    };
  else if (url.pathname.endsWith("/search")) {
    await new Promise((resolve) => setTimeout(resolve, 300));
    data = {
      results: emptySearch
        ? []
        : [
            {
              id: 1,
              similarity: 0.87,
              context:
                "Review the handover notes and record the next action.\n\n".repeat(
                  20
                ),
              document_id: 12,
              source_type: "file",
              source_name: "team-handbook.pdf",
              chunk_index: 1,
              source_start_character: 0,
              source_end_character: 1040,
              token_count: 200
            },
            {
              id: 2,
              similarity: 0.61,
              context: "This passage has no source information.",
              document_id: null,
              source_type: null,
              source_name: null,
              chunk_index: null,
              source_start_character: null,
              source_end_character: null,
              token_count: null
            }
          ],
      timing_ms: { query_embedding: 8, database_search: 2, total: 10 }
    };
  } else if (request.method() === "DELETE") {
    await new Promise((resolve) => setTimeout(resolve, 2500));
    if (failDelete) {
      failDelete = false;
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Deletion failed. Try again." })
      });
      return;
    }
    data = {
      deleted_document_rows: documents,
      deleted_embedding_rows: passages
    };
    documents = 0;
    passages = 0;
  } else if (request.method() === "POST") {
    await new Promise((resolve) => setTimeout(resolve, 2500));
    if (failEmbed) {
      failEmbed = false;
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Indexing failed. Try again." })
      });
      return;
    }
    documents++;
    passages += 2;
    data = {
      ok: true,
      source: {
        document_id: 12,
        source_type: "text",
        source_name: "Handover notes",
        filename: null,
        size_bytes: 100,
        character_count: 100,
        token_count: 25
      },
      chunking: {
        max_chunk_tokens: 500,
        chunk_count: 2,
        chunk_token_counts: [15, 10],
        preview_truncated: false,
        chunks: [
          {
            index: 1,
            token_count: 15,
            character_count: 50,
            source_start_character: 0,
            source_end_character: 50,
            overlap_with_previous_tokens: 0,
            context: "A useful source passage."
          }
        ]
      },
      timing_ms: { chunking: 1, embedding: 20, total: 21 }
    };
  } else
    throw new Error(
      `Unexpected RAG request: ${request.method()} ${url.pathname}`
    );
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(data)
  });
});
const add = () =>
  page.getByRole("button", { name: "Add to knowledge", exact: true });
const tab = (name) => page.getByRole("tab", { name, exact: true });
const search = () => page.getByRole("button", { name: "Search", exact: true });
const query = () =>
  page.getByRole("searchbox", {
    name: "What are you looking for?",
    exact: true
  });
async function noOverflow() {
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth
    ),
    true
  );
}
try {
  await page.goto(`${baseURL}/rag`);
  await page.getByRole("heading", { name: "Knowledge", exact: true }).waitFor();
  await page
    .getByLabel("Knowledge summary")
    .getByText("80", { exact: true })
    .waitFor();
  assert.equal(await add().isDisabled(), true);
  assert.equal(
    await page
      .getByRole("button", { name: "Empty database", exact: true })
      .isVisible(),
    false
  );
  await noOverflow();
  await page.screenshot({ path: `${artifacts}/knowledge-add-1440.png` });
  await tab("Add knowledge").focus();
  await page.keyboard.press("ArrowRight");
  await page.getByRole("heading", { name: "Find useful passages" }).waitFor();
  assert.equal(
    await tab("Search knowledge").evaluate(
      (element) => element === document.activeElement
    ),
    true
  );
  await query().fill("handover");
  await page.getByRole("spinbutton", { name: "Top results" }).fill("0");
  assert.equal(await search().isDisabled(), true);
  await page.getByRole("spinbutton", { name: "Top results" }).fill("5");
  await query().press("Enter");
  await page
    .getByRole("heading", { name: "team-handbook.pdf", exact: true })
    .waitFor();
  assert.equal(requests.at(-1).query, "handover");
  assert.equal(requests.at(-1).topK, "5");
  await page
    .getByRole("button", { name: "Read full passage", exact: true })
    .click();
  assert.equal(
    await page
      .getByRole("button", { name: "Show less", exact: true })
      .getAttribute("aria-expanded"),
    "true"
  );
  await page.getByRole("button", { name: "Show less", exact: true }).click();
  await page.getByText("Match details", { exact: true }).first().click();
  await page.getByText("Cosine similarity: 0.87", { exact: true }).waitFor();
  await query().fill("unsent draft");
  await page.getByText("Results for “handover”", { exact: true }).waitFor();
  for (const width of [1440, 1024, 760]) {
    await page.setViewportSize({ width, height: 1000 });
    await noOverflow();
    await page.screenshot({
      path: `${artifacts}/knowledge-search-${width}.png`
    });
  }
  emptySearch = true;
  await search().click();
  await page.getByText("No matching passages", { exact: true }).waitFor();
  emptySearch = false;
  await tab("Add knowledge").click();
  await page.locator('input[type="file"]').setInputFiles({
    name: "image.png",
    mimeType: "image/png",
    buffer: Buffer.from("unsupported")
  });
  await page.getByRole("alert").filter({ hasText: "Choose a TXT" }).waitFor();
  await page.locator('input[type="file"]').setInputFiles({
    name: "notes.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("hello")
  });
  await page.getByRole("button", { name: "Remove file" }).click();
  assert.equal(await add().isDisabled(), true);
  const dropZone = page
    .getByText("Drop a document here", { exact: true })
    .locator("..");
  await dropZone.evaluate((element) => {
    const data = new DataTransfer();
    data.items.add(new File(["one"], "one.txt"));
    data.items.add(new File(["two"], "two.txt"));
    element.dispatchEvent(
      new DragEvent("drop", {
        bubbles: true,
        cancelable: true,
        dataTransfer: data
      })
    );
  });
  await page.getByRole("alert").filter({ hasText: "one document" }).waitFor();
  await page.getByRole("button", { name: "Paste text", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Display title (optional)" })
    .fill("Handover notes");
  await page
    .getByRole("textbox", { name: "Source text", exact: true })
    .fill("Review the handover notes.");
  await page.getByText("Indexing options", { exact: true }).click();
  await page
    .getByRole("spinbutton", { name: "Maximum tokens per chunk" })
    .fill("1001");
  assert.equal(await add().isDisabled(), true);
  await page
    .getByRole("spinbutton", { name: "Maximum tokens per chunk" })
    .fill("500");
  await page.getByText("Manage knowledge", { exact: true }).click();
  await add().click();
  await page
    .getByRole("button", { name: "Adding to knowledge…", exact: true })
    .waitFor();
  assert.equal(
    await page
      .getByRole("button", { name: "Empty database", exact: true })
      .isDisabled(),
    true
  );
  await page.getByText("Source added to knowledge", { exact: true }).waitFor();
  const embedRequest = requests.find((request) =>
    request.path.endsWith("/embed/text")
  );
  assert.deepEqual(JSON.parse(embedRequest.body), {
    text: "Review the handover notes.",
    title: "Handover notes",
    max_chunk_tokens: 500
  });
  await page.getByText("Processing details", { exact: true }).click();
  await page.getByText("A useful source passage.", { exact: true }).waitFor();
  await page
    .getByLabel("Knowledge summary")
    .getByText("3", { exact: true })
    .waitFor();
  await page
    .getByRole("button", { name: "Search your knowledge", exact: true })
    .click();
  await page.getByRole("heading", { name: "Find useful passages" }).waitFor();
  await tab("Add knowledge").click();
  failEmbed = true;
  await add().click();
  await page
    .getByRole("alert")
    .filter({ hasText: "Indexing failed" })
    .waitFor();
  assert.equal(
    await page
      .getByRole("textbox", { name: "Source text", exact: true })
      .inputValue(),
    "Review the handover notes."
  );
  // All deletion is mocked. Check exact confirmation, Escape, focus and failure recovery.
  const openDelete = page.getByRole("button", {
    name: "Empty database",
    exact: true
  });
  await openDelete.click();
  const dialog = page.getByRole("dialog", { name: "Delete all RAG data?" });
  await dialog.waitFor();
  const confirm = dialog.getByRole("textbox", {
    name: "Type DELETE to confirm"
  });
  assert.equal(
    await confirm.evaluate((element) => element === document.activeElement),
    true
  );
  await confirm.fill("delete");
  assert.equal(
    await dialog
      .getByRole("button", { name: "Delete all data", exact: true })
      .isDisabled(),
    true
  );
  await confirm.fill("DELETE");
  await confirm.press("Enter");
  assert.equal(requests.filter((r) => r.method === "DELETE").length, 0);
  await page.keyboard.press("Escape");
  await dialog.waitFor({ state: "hidden" });
  assert.equal(
    await openDelete.evaluate((element) => element === document.activeElement),
    true
  );
  await openDelete.click();
  await confirm.fill("DELETE");
  await page.setViewportSize({ width: 760, height: 800 });
  await page.screenshot({
    path: `${artifacts}/knowledge-delete-confirmation.png`
  });
  failDelete = true;
  await dialog
    .getByRole("button", { name: "Delete all data", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Deleting…", exact: true })
    .waitFor();
  await page.keyboard.press("Escape");
  assert.equal(await dialog.isVisible(), true);
  await dialog
    .getByRole("alert")
    .filter({ hasText: "Deletion failed" })
    .waitFor();
  await dialog
    .getByRole("button", { name: "Delete all data", exact: true })
    .click();
  await dialog.waitFor({ state: "hidden" });
  await page.getByText(/RAG database emptied successfully/).waitFor();
  assert.equal(await page.locator("#root").getAttribute("inert"), null);
  assert.deepEqual(errors, [], "No runtime errors");
  console.log(`RAG UI checks passed. Screenshots: ${artifacts}`);
} catch (error) {
  await page.screenshot({ path: `${artifacts}/failure.png` });
  throw error;
} finally {
  await browser.close();
}
