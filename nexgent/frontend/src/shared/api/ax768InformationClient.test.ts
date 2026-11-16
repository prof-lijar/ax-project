import { describe, expect, it } from "vitest";
import { isInformationResult } from "./ax768InformationClient";
const stage = { status: "updated", reason: "확인", rows: [6], changes: ["생년월일: 380215"], verified: true };
function result() { return { workflow_id: "information_update", id: "test", region: "영덕", status: "completed", response: "완료", duration_ms: 12, receipts: { roster: {...stage}, as_update: {...stage}, member_note: {...stage} } }; }
describe("information workflow evidence", () => {
  it("accepts verified stages and confirmed AS absence", () => {
    const r = result(); expect(isInformationResult(r)).toBe(true);
    r.receipts.as_update = {status:"skipped",reason:"없음",rows:[],changes:[],verified:true};
    expect(isInformationResult(r)).toBe(true);
  });
  it("rejects unverified writes, multiple roster rows and missing predecessors", () => {
    for (const key of ["roster", "as_update", "member_note"] as const) {
      const r = result(); r.receipts[key].verified = false; expect(isInformationResult(r)).toBe(false);
    }
    const r = result(); r.receipts.roster.rows = [6,7]; expect(isInformationResult(r)).toBe(false);
    r.receipts.roster.rows = [6]; r.receipts.as_update.status = "unknown"; expect(isInformationResult(r)).toBe(false);
  });
});

it("requires a resolved region for saved rows but allows no-match results", () => {
  expect(isInformationResult({...result(), region:null})).toBe(false);
  const skipped = {status:"skipped",reason:"not run",rows:[],changes:[],verified:false};
  expect(isInformationResult({...result(),status:"blocked",region:null,receipts:{roster:skipped,as_update:skipped,member_note:skipped}})).toBe(true);
});
