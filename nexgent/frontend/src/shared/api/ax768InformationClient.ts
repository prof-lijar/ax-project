import { authenticatedFetch } from "./authenticatedFetch";

export type InformationRegion = "울진" | "영덕" | "광명";
export type InformationReceipt = { status: "updated" | "skipped" | "blocked" | "unknown"; reason: string; rows: number[]; changes: string[]; verified: boolean };
export type InformationResult = { workflow_id: "information_update"; id: string; region: InformationRegion | null; status: "completed" | "blocked" | "failed"; response: string; duration_ms: number; receipts: Record<"roster" | "as_update" | "member_note", InformationReceipt> };
const uncertain = "결과를 확인하지 못했습니다. 재실행 전에 명부·AS·마스터페이지를 확인해 주세요.";
export function isInformationResult(value: unknown): value is InformationResult {
  if (!value || typeof value !== "object") return false;
  const v = value as InformationResult;
  if (v.workflow_id !== "information_update" || typeof v.id !== "string" || (v.region !== null && !["울진", "영덕", "광명"].includes(v.region)) || !["completed", "blocked", "failed"].includes(v.status) || typeof v.response !== "string" || v.response.length > 2000 || !Number.isFinite(v.duration_ms) || v.duration_ms < 0 || !v.receipts) return false;
  const keys = ["roster", "as_update", "member_note"] as const;
  if (Object.keys(v.receipts).length !== 3) return false;
  for (const key of keys) {
    const r = v.receipts[key];
    if (!r || !["updated", "skipped", "blocked", "unknown"].includes(r.status) || typeof r.reason !== "string" || r.reason.length > 1000 || typeof r.verified !== "boolean" || !Array.isArray(r.rows) || r.rows.length > 100 || !r.rows.every(n => Number.isSafeInteger(n) && n > 0) || new Set(r.rows).size !== r.rows.length || !Array.isArray(r.changes) || r.changes.length > 20 || !r.changes.every(s => typeof s === "string" && s.length <= 600)) return false;
    if (r.status === "updated" && (!r.verified || !r.rows.length || key !== "as_update" && r.rows.length !== 1)) return false;
    if (["unknown", "blocked"].includes(r.status) && r.verified) return false;
    if (r.status === "skipped" && (r.rows.length || r.changes.length || r.verified && key !== "as_update")) return false;
  }
  const { roster, as_update: cases, member_note: member } = v.receipts;
  if ((roster.verified || roster.status === "unknown") && v.region === null) return false;
  return (!(cases.verified || cases.status === "unknown") || roster.verified) && (!(member.verified || member.status === "unknown") || roster.verified && cases.verified) && ((v.status === "completed") === keys.every(k => v.receipts[k].verified)) && (!keys.some(k => v.receipts[k].status === "unknown") || v.status === "failed");
}
export async function runInformationUpdate(message: string): Promise<InformationResult> {
  if (!message.trim() || message.length > 8000) throw new Error("한 가입자의 수정 요청을 8,000자 이내로 입력해 주세요.");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 555_000);
  try {
    const response = await authenticatedFetch("/api/ax768/runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({workflow_id: "information_update", message}), signal: controller.signal });
    if ([401, 403].includes(response.status)) throw new Error("관리자 권한이 필요합니다.");
    if (response.status === 409) throw new Error("정보확인&수정을 활성화하려면 Agent Server를 재시작해 주세요.");
    if (!response.ok) throw new Error(uncertain);
    const value: unknown = await response.json();
    if (!isInformationResult(value)) throw new Error(uncertain);
    return value;
  } catch (error) {
    if (error instanceof Error && ["관리자 권한이 필요합니다.", "정보확인&수정을 활성화하려면 Agent Server를 재시작해 주세요."].includes(error.message)) throw error;
    throw new Error(uncertain);
  } finally { clearTimeout(timer); }
}
