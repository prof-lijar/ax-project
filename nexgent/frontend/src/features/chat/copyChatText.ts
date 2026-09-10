/** Copy from a user action, including browsers running on plain-HTTP LAN URLs. */
export async function copyChatText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch {
      // Some webviews expose Clipboard but reject it. Try the browser's
      // selection-based copy command without adding native permissions.
    }
  }

  const focused =
    document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
  const inputSelection =
    focused instanceof HTMLInputElement ||
    focused instanceof HTMLTextAreaElement
      ? {
          start: focused.selectionStart,
          end: focused.selectionEnd,
          direction: focused.selectionDirection
        }
      : null;
  const selection = window.getSelection();
  const ranges = selection
    ? Array.from({ length: selection.rangeCount }, (_, index) =>
        selection.getRangeAt(index).cloneRange()
      )
    : [];
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.readOnly = true;
  textarea.tabIndex = -1;
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "0";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  try {
    textarea.focus({ preventScroll: true });
    textarea.select();
    textarea.setSelectionRange(0, text.length);
    if (!document.execCommand("copy"))
      throw new Error("Clipboard copy was blocked");
  } finally {
    textarea.remove();
    focused?.focus({ preventScroll: true });
    if (
      inputSelection &&
      (focused instanceof HTMLInputElement ||
        focused instanceof HTMLTextAreaElement)
    ) {
      if (inputSelection.start !== null && inputSelection.end !== null) {
        focused.setSelectionRange(
          inputSelection.start,
          inputSelection.end,
          inputSelection.direction ?? undefined
        );
      }
    } else if (selection) {
      selection.removeAllRanges();
      ranges.forEach((range) => selection.addRange(range));
    }
  }
}
