import { useLayoutEffect, useRef, useState } from "react";
import type { ChatMessage } from "../../shared/state/useChatStore";

const segmenter = typeof Intl.Segmenter === "function"
  ? new Intl.Segmenter(undefined, { granularity: "grapheme" })
  : null;

// Animate only new text observed while mounted. Saved replies and the existing
// prefix of a rejoined reply must appear immediately.
export function useStreamingText(content: string, status: ChatMessage["status"]) {
  const [displayed, setDisplayed] = useState(content);
  const visible = useRef(content);
  const live = useRef(false);
  const lastFrame = useRef<number | null>(null);

  useLayoutEffect(() => {
    if (status === "waiting" || status === "streaming") live.current = true;
    const animate = live.current && (status === "streaming" || status === "complete");
    if (!animate || !content.startsWith(visible.current)) {
      visible.current = content;
      setDisplayed(content);
      lastFrame.current = null;
      if (status !== "waiting" && status !== "streaming") live.current = false;
      return;
    }
    if (visible.current === content) {
      lastFrame.current = null;
      if (status === "complete") live.current = false;
      return;
    }

    let frame: number;
    function reveal(now: number) {
      const elapsed = lastFrame.current === null ? 16 : Math.min(now - lastFrame.current, 64);
      // Usually one character per frame; gently catch up on large server bursts.
      const interval = Math.max(4, 16 - (content.length - visible.current.length) / 40);
      const count = Math.min(4, Math.floor(elapsed / interval));
      if (count > 0) {
        const suffix = content.slice(visible.current.length);
        const remaining = segmenter?.segment(suffix) ?? Array.from(suffix, segment => ({ segment }));
        let end = visible.current.length;
        let revealed = 0;
        for (const part of remaining) {
          end += part.segment.length;
          if (++revealed === count) break;
        }
        visible.current = content.slice(0, end);
        lastFrame.current = now;
        setDisplayed(visible.current);
      }
      if (visible.current !== content) frame = requestAnimationFrame(reveal);
      else {
        lastFrame.current = null;
        if (status === "complete") live.current = false;
      }
    }
    frame = requestAnimationFrame(reveal);
    return () => cancelAnimationFrame(frame);
  }, [content, status]);

  return {
    content: displayed,
    revealing: displayed !== content && content.startsWith(displayed) &&
      (status === "streaming" || status === "complete")
  };
}
