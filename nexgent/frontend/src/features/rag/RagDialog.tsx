import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

/** Isolates modal drawers and confirmations, preserving keyboard focus. */
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
    const initial = container.current?.querySelector<HTMLElement>(
      'input:not([type="file"]):not(:disabled), textarea:not(:disabled), button:not(:disabled)'
    );
    (initial ?? container.current)?.focus();
    function keydown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        if (!controls.current.pending) controls.current.onCancel();
      }
      if (event.key !== "Tab") return;
      const focusable = container.current?.querySelectorAll<HTMLElement>(
        'input:not([type="file"]):not(:disabled), textarea:not(:disabled), button:not(:disabled), summary, a[href], select:not(:disabled)'
      );
      if (!focusable?.length) {
        event.preventDefault();
        container.current?.focus();
        return;
      }
      const visible = Array.from(focusable).filter(
        (element) => element.getClientRects().length > 0
      );
      const first = visible[0],
        last = visible[visible.length - 1];
      if (!first || !last) {
        event.preventDefault();
        container.current?.focus();
        return;
      }
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
