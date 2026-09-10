import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

/** Keeps deletion confirmation isolated from the surrounding workspace. */
export function RagDialog({
  children,
  pending,
  onCancel
}: {
  children: ReactNode;
  pending: boolean;
  onCancel: () => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const controls = useRef({ pending, onCancel });
  controls.current = { pending, onCancel };
  useEffect(() => {
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const root = document.getElementById("root");
    const wasInert = root?.hasAttribute("inert");
    root?.setAttribute("inert", "");
    container.current?.querySelector<HTMLInputElement>("input")?.focus();
    function keydown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        if (!controls.current.pending) controls.current.onCancel();
      }
      if (event.key !== "Tab") return;
      const focusable = container.current?.querySelectorAll<HTMLElement>(
        "input:not(:disabled), button:not(:disabled)"
      );
      if (!focusable?.length) {
        event.preventDefault();
        container.current?.focus();
        return;
      }
      const first = focusable[0],
        last = focusable[focusable.length - 1];
      if (
        !container.current?.contains(document.activeElement) ||
        (!event.shiftKey && document.activeElement === last)
      ) {
        event.preventDefault();
        first.focus();
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      }
    }
    document.addEventListener("keydown", keydown);
    return () => {
      document.removeEventListener("keydown", keydown);
      if (!wasInert) root?.removeAttribute("inert");
      previous?.focus({ preventScroll: true });
    };
  }, []);
  const content = (
    <div ref={container} tabIndex={-1}>
      {children}
    </div>
  );
  return typeof document === "undefined"
    ? content
    : createPortal(content, document.body);
}
