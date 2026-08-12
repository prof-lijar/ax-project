import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ChatMarkdown } from "./ChatMarkdown";

describe("ChatMarkdown", () => {
  it("renders common Markdown and GitHub-flavored tables", () => {
    const html = renderToStaticMarkup(
      <ChatMarkdown
        content={[
          "## Result",
          "",
          "- **Ready**",
          "- `safe`",
          "",
          "| Item | Status |",
          "| --- | --- |",
          "| Chat | Working |",
          "",
          "```ts",
          "const answer = true;",
          "```"
        ].join("\n")}
      />
    );

    expect(html).toContain("<h2>Result</h2>");
    expect(html).toContain("<strong>Ready</strong>");
    expect(html).toContain("<table>");
    expect(html).toContain("language-ts");
  });

  it("does not render raw HTML from an assistant response", () => {
    const html = renderToStaticMarkup(
      <ChatMarkdown content={'<script>alert("unsafe")</script>'} />
    );

    expect(html).not.toContain("<script>");
  });
});
