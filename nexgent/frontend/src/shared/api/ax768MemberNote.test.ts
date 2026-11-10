import { afterEach, describe, expect, it, vi } from "vitest";
import { ax768Client, memberCandidateMessage } from "./ax768Client";
const note="2026-10-28 [현지관리자 방문] 기기위치조정";
const member={status:"saved",member_id:12,name:"이은경",address:"테스트로 1",note,verified:true,candidates:[]};
const fixture={id:"run",case_id:"member_note",status:"completed",outcome:"note_saved",response:"저장 확인",started_at:"2026-11-10",duration_ms:100,
 city:null,sheet_alias:null,sheet_title:null,selected_row:null,name:"이은경",address:"테스트로 1",sheet_url:null,highlighted_range:null,
 stored_verified:null,visible_verified:null,overridden_cells:[],overridden_cell_count:0,match_count:0,matches:[],attempts:[],member_note:member};
afterEach(()=>vi.unstubAllGlobals());
describe("member note Test case",()=>{
 it("accepts only a verified save receipt",async()=>{
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response(JSON.stringify(fixture))));
  expect((await ax768Client.run("member_note","이름: 이은경")).member_note?.verified).toBe(true);
 });
 it.each([{...fixture,member_note:undefined},{...fixture,member_note:{...member,verified:false}},
  {...fixture,member_note:{...member,member_id:null}}, {...fixture,member_note:{...member,note:"missing date"}},
  {...fixture,case_id:"4.2"},{...fixture,status:"failed"}])("rejects contradictory or missing member evidence",async body=>{
   vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response(JSON.stringify(body))));
   await expect(ax768Client.run("member_note","text")).rejects.toThrow();
 });
 it("keeps candidate selection separate from saving",()=>{
  expect(memberCandidateMessage(`이름: 이은경\n일반 사항: ${note}`,{member_id:12,name:"넥스터_이은경",address:"테스트로 1"})).toBe(`이름: 넥스터_이은경\n주소: 테스트로 1\n가입자 ID: 12\n일반 사항: ${note}`);
 });
 it("does not retry a save with an uncertain response",async()=>{
  const fetch=vi.fn().mockResolvedValue(new Response('{}',{status:502}));vi.stubGlobal("fetch",fetch);
  await expect(ax768Client.run("member_note","text")).rejects.toThrow("Check general notes");expect(fetch).toHaveBeenCalledTimes(1);
 });
 it("explains missing runtime support",async()=>{
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response('{}',{status:409})));
  await expect(ax768Client.run("member_note","text")).rejects.toThrow("enable member general notes");
 });
});
