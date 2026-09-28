import { t, useLanguage } from "../../shared/i18n";
import { Children, isValidElement, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import { CopyButton } from "./MessageActions";
import styles from "./ChatPage.module.css";

function plainText(node: ReactNode): string {
  return Children.toArray(node)
    .map((child) =>
      isValidElement<{ children?: ReactNode }>(child)
        ? plainText(child.props.children)
        : typeof child === "string" || typeof child === "number"
          ? String(child)
          : ""
    )
    .join("");
}
export function ChatMarkdown({ content }: { content: string }) {
  useLanguage((state) => state.language);
  return (
    <div className={styles.markdown}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        // Native MathML fits the desktop CSP without inline layout styles or
        // external fonts. Keep model-provided HTML/URL commands untrusted.
        rehypePlugins={[[rehypeKatex, { output: "mathml", trust: false, maxSize: 10, maxExpand: 1000 }]]}
        components={{
          a: ({ node: _node, children, ...props }) => (
            <a {...props} target="_blank" rel="noreferrer">
              {children}
            </a>
          ),
          pre: ({ children }) => (
            <div className={styles.codeBlock}>
              <div className={styles.codeToolbar}>
                <span>{t("Code")}</span>
                <CopyButton
                  text={plainText(children).replace(/\n$/, "")}
                  label={t("Copy code")}
                />
              </div>
              <pre>{children}</pre>
            </div>
          )
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
