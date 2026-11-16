import { authenticatedFetch } from "./authenticatedFetch";

export interface ExtractionSource { text: string }
export interface ExtractedField { label: string; value: string; source_index: number; uncertain: boolean }
export const EXTRACTION_ERROR = "Information extraction failed. Review the original text and try again.";

export async function extractInformation(sources: ExtractionSource[], signal: AbortSignal): Promise<ExtractedField[]> {
  if (!sources.length || sources.length > 6 || sources.some(source => !source.text.trim() || source.text.length > 8000)) {
    throw new Error("Use up to 8,000 characters per source for information extraction.");
  }
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal.addEventListener("abort", abort, { once: true });
  const timer = setTimeout(abort, 120_000);
  try {
    if (signal.aborted) controller.abort();
    const response = await authenticatedFetch("/api/ax768/workflow/extract", {
      method: "POST", headers: { "Content-Type": "application/json" }, signal: controller.signal,
      body: JSON.stringify({ workflow_id: "information_update", sources })
    });
    if (response.status === 409) throw new Error("Restart Agent Server to enable information extraction.");
    if (!response.ok) throw new Error(EXTRACTION_ERROR);
    const data = await response.json();
    if (data?.workflow_id !== "information_update" || data.extraction_version !== "1" || !Array.isArray(data.fields) || data.fields.length > 200) throw new Error(EXTRACTION_ERROR);
    const fields: ExtractedField[] = data.fields;
    if (!fields.every(field => field && typeof field.label === "string" && !!field.label.trim() && field.label.length <= 200 &&
      typeof field.value === "string" && !!field.value.trim() && field.value.length <= 8000 &&
      Number.isInteger(field.source_index) && field.source_index >= 0 && field.source_index < sources.length &&
      sources[field.source_index].text.includes(field.value) && typeof field.uncertain === "boolean") ||
      fields.reduce((size, field) => size + field.label.length + field.value.length, 0) > 56000) throw new Error(EXTRACTION_ERROR);
    return fields;
  } finally { clearTimeout(timer); signal.removeEventListener("abort", abort); }
}
