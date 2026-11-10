import { authenticatedFetch } from "./authenticatedFetch";

export const AX768_CASES = [
  { id: "member_note", title: "Member general note", target: "Member admin · General notes", format: "Name and dated general note on separate labeled lines", example: "이름: 이은경\n일반 사항: 2026-10-28 [현지관리자 방문] 기기위치조정", writes: true, description: "Find a member, replace General notes and verify the saved text." },
  { id: "imei", title: "IMEI case", target: "Uljin AA → Gwangmyeong W → Yeongdeok Z → Signal check", format: "Name + signal-check request", example: "김순옥님 신호확인요.", writes: false, description: "Find the latest roster match, read its IMEI and check the device signal." },
  { id: "1.1", title: "Name lookup", target: "AS sheet", format: "Name + signal-check request", example: "김순옥님 신호확인요.", writes: false, description: "Find the latest matching name and return its row." },
  { id: "2.2", title: "Address lookup", target: "Uljin user roster", format: "Address", example: "상밤터1길 59-4", writes: false, description: "Find the latest matching address and return its row." },
  { id: "2.3", title: "AS name and address", target: "AS sheet", format: "Address + name", example: "오봉길 24 주정수", writes: false, description: "Find the latest AS row matching both name and address." },
  { id: "4.2", title: "User lookup · signal request", target: "Uljin → Gwangmyeong → Yeongdeok", format: "Address + name + signal-check request", example: "울진북로 164 김순옥님 신호확인요.", writes: false, description: "Search rosters in order and return the city and latest matching row." },
  { id: "4.3", title: "AS lookup · signal request", target: "AS sheet", format: "Address + name + signal-check request", example: "울진북로 164 김순옥님 신호확인요.", writes: false, description: "Find the latest AS match from a signal request." },
  { id: "6.2", title: "User lookup · comma-separated", target: "Uljin → Gwangmyeong → Yeongdeok", format: "Address, name, request", example: "왕피길83-15,정영자,기기위치조정 수신확인요~", writes: false, description: "Use the address and name to locate the user across city rosters." },
  { id: "6.3", title: "AS lookup · comma-separated", target: "AS sheet", format: "Address, name, request", example: "왕피길83-15,정영자,기기위치조정 수신확인요~", writes: false, description: "Use the address and name to find the latest AS row." }
] as const;
export type Ax768CaseId = typeof AX768_CASES[number]["id"];
export type Ax768Outcome = "note_saved" | "note_present" | "connected" | "disconnected" | "found" | "not_found" | "highlighted" | "highlighted_with_warnings" | "blocked" | "failed" | "unknown";
export interface Ax768Ping { imei: string; sn: string; connected: boolean; fresh: boolean; signal_label: string | null; rssi: number | null; elapsed_ms: number | null }
export interface MemberCandidate { member_id: number; name: string; address: string }
export interface MemberNoteReceipt {
  status: "saved" | "already_present" | "not_found" | "needs_confirmation" | "blocked" | "failed" | "unknown";
  member_id: number | null; name: string | null; address: string | null; note: string | null;
  verified: boolean; candidates: MemberCandidate[];
}
export function memberCandidateMessage(message: string, candidate: MemberCandidate) {
  const note = message.split(/\r?\n/).filter(line => /^\s*일반\s*사항\s*[:：]/.test(line));
  return `이름: ${candidate.name}\n주소: ${candidate.address}\n가입자 ID: ${candidate.member_id}\n${note.join("\n")}`;
}
export function isMemberNote(value: unknown, status: string, outcome: string): value is MemberNoteReceipt {
  if (!value || typeof value !== "object") return false;
  const v = value as MemberNoteReceipt;
  const outcomes = {saved: "note_saved", already_present: "note_present", not_found: "not_found", needs_confirmation: "blocked", blocked: "blocked", failed: "failed", unknown: "unknown"};
  if (!Object.prototype.hasOwnProperty.call(outcomes, v.status) || outcomes[v.status] !== outcome) return false;
  const saved = ["saved", "already_present"].includes(v.status);
  const expected = saved || v.status === "not_found" ? "completed" : ["blocked", "needs_confirmation"].includes(v.status) ? "blocked" : "failed";
  return status === expected && typeof v.verified === "boolean" && v.verified === saved &&
    (v.member_id === null || (Number.isSafeInteger(v.member_id) && v.member_id > 0)) &&
    [v.name, v.address, v.note].every(x => x === null || typeof x === "string") &&
    (v.name?.length ?? 0) <= 100 && (v.address?.length ?? 0) <= 1000 && (v.note?.length ?? 0) <= 500 &&
    (!(saved || v.status === "unknown") || (!!v.member_id && !!v.name && !!v.note)) &&
    (!saved || /^\d{4}-\d{2}-\d{2} [^\r\n]+$/.test(v.note ?? "")) &&
    Array.isArray(v.candidates) && v.candidates.length <= 20 && Boolean(v.candidates.length) === (v.status === "needs_confirmation") &&
    v.candidates.every(c => c && Number.isSafeInteger(c.member_id) && c.member_id > 0 && typeof c.name === "string" && c.name.length > 0 && c.name.length <= 100 && typeof c.address === "string" && c.address.length <= 1000);
}
export interface Ax768Result {
  member_note?: MemberNoteReceipt;
  imei?: string | null; imei_column?: string | null; ping?: Ax768Ping | null;
  id: string; case_id: Ax768CaseId; status: "completed" | "failed" | "blocked";
  outcome: Ax768Outcome; response: string; started_at: string; duration_ms: number;
  city: string | null; sheet_alias: string | null; sheet_title: string | null;
  selected_row: number | null; name: string | null; address: string | null;
  sheet_url: string | null; highlighted_range: string | null;
  stored_verified: boolean | null; visible_verified: boolean | null;
  overridden_cells: string[]; overridden_cell_count: number; match_count: number;
  matches: Array<{row: number; cells: Array<{cell: string | null; address: string | null; truncated: boolean}>}>;
  attempts: Array<{city: string | null; sheet_alias: string | null; status: "found" | "not_found" | "failed"}>;
}
export const outcomeLabels: Record<Ax768Outcome, string> = {
  note_saved: "General note saved and verified", note_present: "General note already present",
  connected: "Connected", disconnected: "No device response",
  found: "Match found", not_found: "No match", highlighted: "Yellow applied",
  highlighted_with_warnings: "Yellow saved · display overridden", blocked: "Needs attention",
  failed: "Run failed", unknown: "Outcome unknown"
};
export class Ax768ClientError extends Error {
  constructor(message: string, readonly outcome: "blocked" | "unknown" = "unknown") { super(message); }
}
export function isSheetUrl(value: unknown): value is string {
  return typeof value === "string" && /^https:\/\/docs\.google\.com\/spreadsheets\/d\/[A-Za-z0-9_-]+\/edit(?:[#?].*)?$/.test(value);
}
function isResult(value: unknown): value is Ax768Result {
  if (!value || typeof value !== "object") return false;
  const v = value as Ax768Result;
  return typeof v.id === "string" && typeof v.response === "string" && typeof v.started_at === "string" &&
    typeof v.duration_ms === "number" && Number.isFinite(v.duration_ms) &&
    AX768_CASES.some(c => c.id === v.case_id) &&
    (v.case_id === "member_note" ? isMemberNote(v.member_note, v.status, v.outcome) : !["note_saved", "note_present"].includes(v.outcome) && v.member_note === undefined) && ["completed", "failed", "blocked"].includes(v.status) &&
    Object.prototype.hasOwnProperty.call(outcomeLabels, v.outcome) &&
    (!["connected", "disconnected"].includes(v.outcome) || (v.case_id === "imei" && !!v.ping &&
      typeof v.imei === "string" && /^[0-9]{15}$/.test(v.imei) && v.ping.imei === v.imei &&
      typeof v.ping.sn === "string" && /^[0-9]{1,32}$/.test(v.ping.sn) &&
      typeof v.ping.connected === "boolean" && v.ping.connected === (v.outcome === "connected") &&
      typeof v.ping.fresh === "boolean" && (!v.ping.connected || v.ping.fresh) &&
      (v.ping.signal_label === null || typeof v.ping.signal_label === "string") &&
      [v.ping.rssi, v.ping.elapsed_ms].every(x => x === null || (typeof x === "number" && Number.isFinite(x))))) &&
    [v.city, v.sheet_alias, v.sheet_title, v.name, v.address, v.sheet_url, v.highlighted_range].every(x => x === null || typeof x === "string") &&
    (v.selected_row === null || (Number.isInteger(v.selected_row) && v.selected_row > 0)) &&
    [v.stored_verified, v.visible_verified].every(x => x === null || typeof x === "boolean") &&
    typeof v.match_count === "number" && typeof v.overridden_cell_count === "number" &&
    Array.isArray(v.overridden_cells) && v.overridden_cells.every(x => typeof x === "string") &&
    Array.isArray(v.matches) && v.matches.every(m => m && Number.isInteger(m.row) && Array.isArray(m.cells) && m.cells.every(c => c && (c.cell === null || typeof c.cell === "string") && (c.address === null || typeof c.address === "string"))) &&
    Array.isArray(v.attempts) && v.attempts.every(a => a && ["found", "not_found", "failed"].includes(a.status) && [a.city, a.sheet_alias].every(x => x === null || typeof x === "string"));
}
export const ax768Client = {
  async run(caseId: Ax768CaseId, message: string): Promise<Ax768Result> {
    if (!message.trim() || message.length > 8000 || !AX768_CASES.some(c => c.id === caseId))
      throw new Ax768ClientError("Enter a message of 1–8,000 characters.", "blocked");
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 285_000);
    try {
      const response = await authenticatedFetch("/api/ax768/runs", {
        method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ case_id: caseId, message: message.trim() }), signal: controller.signal
      });
      if ([401, 403].includes(response.status)) throw new Ax768ClientError("Administrator access is required.", "blocked");
      if (response.status === 409) throw new Ax768ClientError(caseId === "member_note" ? "Restart Agent Server to enable member general notes." : caseId === "imei" ? "Restart Agent Server to enable the IMEI case." : "Restart Agent Server to enable search-only cases.", "blocked");
      if (response.status === 422) throw new Ax768ClientError("Check the input format for this case.", "blocked");
      if (!response.ok) throw new Ax768ClientError(caseId === "member_note" ? "The note save could not be confirmed. Check general notes before running again." : "The result could not be confirmed. Inspect the sheet before running again.");
      const result: unknown = await response.json();
      if (!isResult(result) || result.case_id !== caseId) throw new Ax768ClientError(caseId === "member_note" ? "The note save could not be confirmed. Check general notes before running again." : "The result could not be confirmed. Inspect the sheet before running again.");
      return { ...result, sheet_url: isSheetUrl(result.sheet_url) ? result.sheet_url : null };
    } catch (error) {
      if (error instanceof Ax768ClientError) throw error;
      throw new Ax768ClientError(caseId === "member_note" ? "The note save could not be confirmed. Check general notes before running again." : "The result could not be confirmed. Inspect the sheet before running again.");
    } finally { clearTimeout(timeout); }
  }
};
