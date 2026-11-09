import { authenticatedFetch } from "./authenticatedFetch";
import { isSheetUrl } from "./ax768Client";

export type WorkflowStatus = "completed" | "not_found" | "needs_confirmation" | "blocked" | "failed";
export interface WorkflowStage {
  status: "found" | "not_found" | "skipped" | "failed" | "needs_confirmation" | "candidate";
  row: number | null; sheet_alias: string | null; city: string | null; sheet_title: string | null;
  name: string | null; address: string | null; reason: string | null; sheet_url: string | null;
}
export interface WorkflowUpdate {
  status: "updated" | "skipped" | "failed" | "unknown";
  row: number | null; date: string | null;
  changes: Array<{column: "S" | "X" | "Y"; value: string}>;
  y_action: "updated" | "unchanged" | null; verified: boolean; reason: string | null;
}
export interface WorkflowResult {
  id: string; started_at: string; duration_ms: number; status: WorkflowStatus; response: string;
  parsed: { name: string | null; lookup_name: string | null; address: string | null; mode: string | null; };
  roster: WorkflowStage; as_lookup: WorkflowStage; as_update: WorkflowUpdate; candidates: WorkflowStage[]; notices: string[];
  attempts: Array<{sheet_alias: string | null; city: string | null; status: "found" | "not_found" | "failed"}>;
}
export const workflowStatusLabels: Record<WorkflowStatus, string> = {
  completed: "AS row updated", not_found: "No match", needs_confirmation: "Choose a matching name", blocked: "Needs attention", failed: "Run failed"
};
const nullableString = (v: unknown) => v === null || typeof v === "string";
function isStage(value: unknown): value is WorkflowStage {
  if (!value || typeof value !== "object") return false;
  const v = value as WorkflowStage;
  return ["found", "not_found", "skipped", "failed", "needs_confirmation", "candidate"].includes(v.status) &&
    [v.sheet_alias, v.city, v.sheet_title, v.name, v.address, v.reason, v.sheet_url].every(nullableString) &&
    (v.row === null || (Number.isInteger(v.row) && v.row > 0)) &&
    (!["found", "candidate"].includes(v.status) || (v.row !== null && !!v.name && isSheetUrl(v.sheet_url)));
}
function isUpdate(value: unknown): value is WorkflowUpdate {
  if (!value || typeof value !== "object") return false;
  const v = value as WorkflowUpdate;
  return ["updated", "skipped", "failed", "unknown"].includes(v.status) &&
    (v.row === null || (Number.isInteger(v.row) && v.row > 0)) && nullableString(v.date) && nullableString(v.reason) &&
    [null, "updated", "unchanged"].includes(v.y_action) && typeof v.verified === "boolean" &&
    Array.isArray(v.changes) && v.changes.length <= 3 && v.changes.every(c => c && ["S", "X", "Y"].includes(c.column) && typeof c.value === "string") &&
    (v.status === "updated" ? v.verified && v.row !== null && !!v.date &&
      v.changes[0]?.column === "S" && v.changes[0].value === "처리완료" && v.changes[1]?.column === "X" && v.changes[1].value === v.date &&
      (v.y_action === "unchanged" ? v.changes.length === 2 : v.y_action === "updated" && v.changes.length === 3 && v.changes[2].column === "Y" && ["위치점검완료", "전원연결완료"].includes(v.changes[2].value)) : !v.verified);
}
function isResult(value: unknown): value is WorkflowResult {
  if (!value || typeof value !== "object") return false;
  const v = value as WorkflowResult;
  return typeof v.id === "string" && typeof v.started_at === "string" && typeof v.duration_ms === "number" && Number.isFinite(v.duration_ms) &&
    Object.prototype.hasOwnProperty.call(workflowStatusLabels, v.status) && typeof v.response === "string" &&
    !!v.parsed && typeof v.parsed === "object" && [v.parsed.name, v.parsed.lookup_name, v.parsed.address, v.parsed.mode].every(nullableString) &&
    isStage(v.roster) && isStage(v.as_lookup) && isUpdate(v.as_update) && (v.status !== "completed" || (v.as_lookup.status === "found" && v.as_update.status === "updated" && v.as_update.row === v.as_lookup.row)) &&
    Array.isArray(v.candidates) && v.candidates.length <= 10 && v.candidates.every(isStage) &&
    Array.isArray(v.notices) && v.notices.every(n => typeof n === "string") &&
    Array.isArray(v.attempts) && v.attempts.every(a => a && ["found", "not_found", "failed"].includes(a.status) && [a.city, a.sheet_alias].every(nullableString));
}
export async function runAx768Workflow(message: string, confirmedName?: string): Promise<WorkflowResult> {
  if (!message.trim() || message.length > 8000) throw new Error("Enter a message of 1–8,000 characters.");
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 285_000);
  try {
    const response = await authenticatedFetch("/api/ax768/workflow/runs", {
      method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({message: message.trim(), confirmed_name: confirmedName ?? null}), signal: controller.signal
    });
    if ([401, 403].includes(response.status)) throw new Error("Administrator access is required.");
    if (response.status === 409) throw new Error("Restart Agent Server to enable the unified workflow.");
    if (response.status === 422) throw new Error("Check the name and address in your request.");
    if (!response.ok) throw new Error("The workflow result could not be retrieved. Check the AS row before running again.");
    const result: unknown = await response.json();
    if (!isResult(result)) throw new Error("The workflow result could not be retrieved. Check the AS row before running again.");
    return result;
  } catch (error) {
    if (error instanceof Error && ["Administrator access is required.", "Restart Agent Server to enable the unified workflow.", "Check the name and address in your request."].includes(error.message)) throw error;
    throw new Error("The workflow result could not be retrieved. Check the AS row before running again.");
  } finally { clearTimeout(timeout); }
}
