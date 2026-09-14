import { Check, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { copyChatText } from "./copyChatText";
import styles from "./ChatPage.module.css";

export function CopyButton({
  text,
  label = "Copy message"
}: {
  text: string;
  label?: string;
}) {
  const [feedback, setFeedback] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      clearTimeout(timer.current);
    };
  }, []);
  async function copy() {
    try {
      await copyChatText(text);
      if (mounted.current) setFeedback("Copied");
    } catch {
      if (mounted.current)
        setFeedback("Couldn't copy. Select the text to copy manually.");
    }
    if (mounted.current) {
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setFeedback(""), 3000);
    }
  }
  return (
    <span className={styles.copyControl}>
      <button
        type="button"
        className={styles.iconButton}
        onClick={() => void copy()}
        aria-label={label}
        title={label}
      >
        {feedback === "Copied" ? <Check size={15} /> : <Copy size={15} />}
      </button>
      <span className={styles.copyFeedback} role="status">
        {feedback}
      </span>
    </span>
  );
}
