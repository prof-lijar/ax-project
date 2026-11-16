import { extractInformation } from "../../shared/api/ax768ExtractionClient";
import { ACTIVE_AX768_WORKFLOW, type Ax768WorkflowId } from "../../shared/api/ax768Workflows";
import { makeImageDraft, type ImageDraft, type OcrPage } from "./ax768ImageInput";

export function rawImageDraft(pages: OcrPage[], original: string): ImageDraft {
  return { original, pages, message: [original, ...pages.map(page => page.text)].filter(Boolean).join("\n\n"), needsReview: true, conflicts: false };
}

export async function extractWorkflowDraft(workflow: Ax768WorkflowId | "", pages: OcrPage[], original: string, signal: AbortSignal): Promise<ImageDraft> {
  if (workflow === ACTIVE_AX768_WORKFLOW) return makeImageDraft(pages, original);
  if (workflow !== "information_update") return rawImageDraft(pages, original);
  const sources = [
    ...(original.trim() ? [{ text: original }] : []),
    ...pages.map(page => ({ text: page.text }))
  ];
  const fields = await extractInformation(sources.map(({ text }) => ({ text })), signal);
  const message = sources.map((_, index) => {
    const values = fields.filter(field => field.source_index === index);
    // A successful empty result may be chat chrome/noise; do not reinsert it.
    return values.length ? values.map(field => `${field.label}${field.uncertain ? " (확인 필요)" : ""}: ${field.value}`).join("\n") : "";
  }).filter(Boolean).join("\n\n");
  return { original, pages, message, structured: true, noInformation: fields.length === 0, conflicts: fields.some(field => field.uncertain),
    needsReview: fields.length > 0 && (fields.some(field => field.uncertain) || pages.some(page => page.confidence < 65)) };
}
