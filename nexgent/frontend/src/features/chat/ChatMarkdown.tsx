import { Children, isValidElement, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
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
  return (
    <div className={styles.markdown}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node: _node, children, ...props }) => (
            <a {...props} target="_blank" rel="noreferrer">
              {children}
            </a>
          ),
          pre: ({ children }) => (
            <div className={styles.codeBlock}>
              <div className={styles.codeToolbar}>
                <span>Code</span>
                <CopyButton
                  text={plainText(children).replace(/\n$/, "")}
                  label="Copy code"
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
