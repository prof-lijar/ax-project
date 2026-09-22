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

  it("renders SAT formulas in paragraphs, lists, and tables as native math", () => {
    const html = renderToStaticMarkup(<ChatMarkdown content={String.raw`Solve for $x$ or $y$.

- The ratio: $\frac{a}{b} = \frac{c}{d}$.
- Vertex: $a(x-h)^2+k$; discriminant: $b^2 - 4ac$.
- Percentage: $\text{Original} \times (1 \pm \text{rate}) = \text{New}$.

| Type | Formula |
| --- | --- |
| Algebra | $y = mx + b$ |
| Geometry | $\sin(x) = \cos(90-x)$ |
| Direction | $\rightarrow$ |
`} />);
    expect(html.match(/<math[ >]/g)).toHaveLength(9);
    expect(html).toContain("<mfrac>");
    expect(html).toContain("<msup>");
    expect(html).toContain("<mtext>Original</mtext>");
    expect(html).toContain("<table>");
    expect(html).not.toContain("$x$");
    expect(html).not.toContain('style="');
  });

  it("renders display math without treating it as a code block", () => {
    const html = renderToStaticMarkup(<ChatMarkdown content={"$$\n\\frac{-b \\pm \\sqrt{b^2-4ac}}{2a}\n$$"} />);
    expect(html).toContain('display="block"');
    expect(html).toContain("<msqrt>");
    expect(html).not.toContain("Copy code");
  });

  it("preserves literal dollars and code examples", () => {
    const html = renderToStaticMarkup(<ChatMarkdown content={'Costs \\$5 and \\$10.\n\n`$x$`\n\n```js\nconst formula = "$x$";\n```'} />);
    expect(html).toContain("Costs $5 and $10.");
    expect(html).toContain("<code>$x$</code>");
    expect(html).not.toContain("<math");
  });

  it("tolerates unfinished streamed math and malformed formulas", () => {
    const formula = String.raw`The ratio is $\frac{a}{b}$.`;
    for (let end = 1; end <= formula.length; end++) {
      expect(() => renderToStaticMarkup(<ChatMarkdown content={formula.slice(0, end)} />)).not.toThrow();
    }
    expect(() => renderToStaticMarkup(<ChatMarkdown content={String.raw`$\frac{a}$`} />)).not.toThrow();
  });

  it("does not allow math commands to insert links or images", () => {
    const html = renderToStaticMarkup(<ChatMarkdown content={String.raw`$\href{javascript:alert(1)}{click}$ $\includegraphics{https://example.com/image.png}$`} />);
    expect(html).not.toContain("<a ");
    expect(html).not.toContain("<img");
    expect(html).not.toContain('href="javascript:');
  });
});
