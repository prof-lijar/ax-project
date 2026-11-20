import { authenticatedFetch } from "./authenticatedFetch";
import { isSheetUrl, isMemberNote, type MemberNoteReceipt } from "./ax768Client";
import { ACTIVE_AX768_WORKFLOW, type Ax768WorkflowId } from "./ax768Workflows";

export type WorkflowStatus = "completed" | "disconnected" | "not_found" | "needs_confirmation" | "blocked" | "failed";
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
export interface WorkflowSignal {
  status: "skipped" | "failed" | "connected" | "disconnected";
  imei_column: string | null; imei: string | null; sn: string | null;
  connected: boolean | null; fresh: boolean | null; signal_label: string | null;
  rssi: number | null; reason: string | null;
}
export interface WorkflowResult {
  workflow_id: typeof ACTIVE_AX768_WORKFLOW;
  id: string; started_at: string; duration_ms: number; status: WorkflowStatus; response: string;
  parsed: { name: string | null; lookup_name: string | null; address: string | null; mode: string | null; };
  signal: WorkflowSignal;
  member_note: MemberNoteReceipt | null;
  roster: WorkflowStage; as_lookup: WorkflowStage; as_update: WorkflowUpdate; candidates: WorkflowStage[]; notices: string[];
  attempts: Array<{sheet_alias: string | null; city: string | null; status: "found" | "not_found" | "failed"}>;
}
export const workflowStatusLabels: Record<WorkflowStatus, string> = {
  completed: "Signal confirmed · General notes saved", disconnected: "Device disconnected", not_found: "No match", needs_confirmation: "Choose a matching name", blocked: "Needs attention", failed: "Run failed"
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
function isSignal(value: unknown, roster: WorkflowStage): value is WorkflowSignal {
  if (!value || typeof value !== "object") return false;
  const v = value as WorkflowSignal;
  if (!["skipped", "failed", "connected", "disconnected"].includes(v.status) ||
      ![v.imei_column, v.imei, v.sn, v.signal_label, v.reason].every(nullableString) ||
      !(v.rssi === null || typeof v.rssi === "number" && Number.isFinite(v.rssi) && v.rssi >= -200 && v.rssi <= 200) ||
      !(v.imei === null || /^[0-9]{15}$/.test(v.imei)) ||
      !(v.imei_column === null || ["AA", "Z", "W"].includes(v.imei_column))) return false;
  if (["connected", "disconnected"].includes(v.status)) {
    const columns: Record<string, string> = {"uljin-users": "AA", "yeongdeok-users": "Z", "gwangmyeon-users": "W"};
    return roster.status === "found" && !!v.imei && !!v.sn && /^[0-9]{1,32}$/.test(v.sn) &&
      v.imei_column === columns[roster.sheet_alias ?? ""] && typeof v.connected === "boolean" &&
      typeof v.fresh === "boolean" && v.connected === (v.status === "connected") && (!v.connected || v.fresh);
  }
  return v.sn === null && v.connected === null && v.fresh === null;
}
function memberAddressMatches(roster: WorkflowStage, address: string | null): boolean {
  const prefixes: Record<string, string[][]> = {
    "uljin-users": [["경상북도", "경북"], ["울진군"]],
    "yeongdeok-users": [["경상북도", "경북"], ["영덕군"]],
    "gwangmyeon-users": [["경기도", "경기"], ["광명시"]]
  };
  const allowed = prefixes[roster.sheet_alias ?? ""];
  if (!allowed || !roster.address?.trim() || !address?.trim()) return false;
  const canonical = (value: string) => {
    let text = value.normalize("NFKC").trim();
    for (const choices of allowed) text = text.replace(new RegExp("^(?:" + choices.join("|") + ")\\s+"), "");
    return text.replace(/\s+/g, "");
  };
  return !!canonical(roster.address) && canonical(roster.address) === canonical(address);
}
function isWorkflowMember(value: unknown, v: WorkflowResult): boolean {
  if (value === null) return v.status !== "completed";
  if (!value || typeof value !== "object") return false;
  const m = value as MemberNoteReceipt;
  const outcomes = {saved: "note_saved", already_present: "note_present", not_found: "not_found", needs_confirmation: "blocked", blocked: "blocked", failed: "failed", unknown: "unknown"};
  const status = ["saved", "already_present", "not_found"].includes(m.status) ? "completed" : ["blocked", "needs_confirmation"].includes(m.status) ? "blocked" : "failed";
  const compact = (s: string | null) => (s ?? "").normalize("NFKC").replace(/\s+/g, "");
  return isMemberNote(m, status, outcomes[m.status]) && v.signal.status === "connected" &&
    (v.as_lookup.status === "found" && v.as_update.status === "updated" || v.as_lookup.status === "not_found" && v.as_update.status === "skipped") &&
    /^\d{4}-\d{2}-\d{2} \[현지관리자 방문\] (기기위치조정|전원연결)$/.test(m.note ?? "") &&
    (v.as_update.status !== "updated" || m.note?.slice(0, 10) === v.as_update.date) &&
    !!compact(v.roster.name) && compact(m.name).includes(compact(v.roster.name)) &&
    memberAddressMatches(v.roster, m.address) &&
    (m.verified === (v.status === "completed"));
}
function isResult(value: unknown): value is WorkflowResult {
  if (!value || typeof value !== "object") return false;
  const v = value as WorkflowResult;
  return v.workflow_id === ACTIVE_AX768_WORKFLOW && typeof v.id === "string" && typeof v.started_at === "string" && typeof v.duration_ms === "number" && Number.isFinite(v.duration_ms) &&
    Object.prototype.hasOwnProperty.call(workflowStatusLabels, v.status) && typeof v.response === "string" &&
    !!v.parsed && typeof v.parsed === "object" && [v.parsed.name, v.parsed.lookup_name, v.parsed.address, v.parsed.mode].every(nullableString) &&
    isStage(v.roster) && isStage(v.as_lookup) && isUpdate(v.as_update) && isSignal(v.signal, v.roster) &&
    (!["updated", "unknown"].includes(v.as_update.status) || v.signal.status === "connected") &&
    (v.status !== "disconnected" || v.signal.status === "disconnected" && v.as_update.status === "skipped") &&
    (v.as_update.status !== "updated" || v.as_update.row === v.as_lookup.row) && isWorkflowMember(v.member_note, v) &&
    Array.isArray(v.candidates) && v.candidates.length <= 10 && v.candidates.every(isStage) &&
    Array.isArray(v.notices) && v.notices.every(n => typeof n === "string") &&
    Array.isArray(v.attempts) && v.attempts.every(a => a && ["found", "not_found", "failed"].includes(a.status) && [a.city, a.sheet_alias].every(nullableString));
}
export async function runAx768Workflow(workflowId: Ax768WorkflowId | "", message: string, confirmedName?: string): Promise<WorkflowResult> {
  if (!workflowId) throw new Error("Please select a workflow.");
  if (workflowId !== ACTIVE_AX768_WORKFLOW) throw new Error("This workflow is coming soon.");
  if (!message.trim() || message.length > 8000) throw new Error("Enter a message of 1–8,000 characters.");
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 435_000);
  try {
    const response = await authenticatedFetch("/api/ax768/runs", {
      method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({workflow_id: workflowId, message: message.trim(), confirmed_name: confirmedName ?? null}), signal: controller.signal
    });
    if ([401, 403].includes(response.status)) throw new Error("Administrator access is required.");
    if (response.status === 409) throw new Error("Restart Agent Server to enable the unified workflow.");
    if (response.status === 422) throw new Error("Check the name and address in your request.");
    if (!response.ok) throw new Error("The workflow result could not be retrieved. Check the AS row and member general notes before running again.");
    const result: unknown = await response.json();
    if (!isResult(result)) throw new Error("The workflow result could not be retrieved. Check the AS row and member general notes before running again.");
    return result;
  } catch (error) {
    if (error instanceof Error && ["Administrator access is required.", "Restart Agent Server to enable the unified workflow.", "Check the name and address in your request."].includes(error.message)) throw error;
    throw new Error("The workflow result could not be retrieved. Check the AS row and member general notes before running again.");
  } finally { clearTimeout(timeout); }
}
