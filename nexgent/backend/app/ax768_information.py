"""Admin boundary for the independently versioned information-update workflow."""
from datetime import datetime, timezone
from time import monotonic
from typing import Literal
from uuid import UUID, uuid4, uuid5

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.chat.config import get_chat_settings
from app.identity.router import require_admin

router = APIRouter(prefix="/api/ax768/workflow", tags=["ax768"], dependencies=[Depends(require_admin)])
GRAPH = "ax768_information_update"
ASSISTANT_ID = str(uuid5(UUID("6ba7b821-9dad-11d1-80b4-00c04fd430c8"), GRAPH))


class InformationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    workflow_id: Literal["information_update"]
    message: str = Field(min_length=1, max_length=8000)


class Receipt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    status: Literal["updated", "skipped", "blocked", "unknown"]
    reason: str = Field(max_length=1000)
    rows: list[int] = Field(max_length=100)
    changes: list[str] = Field(max_length=20)
    verified: bool


def normalize(value):
    if not isinstance(value, dict) or value.get("status") not in {"completed", "blocked", "failed"}:
        raise ValueError("Invalid status")
    response = value.get("response")
    if not isinstance(response, str) or len(response)>2000:
        raise ValueError("Invalid response")
    receipts = value.get("receipts")
    keys = ("roster", "as_update", "member_note")
    if not isinstance(receipts, dict) or set(receipts)!=set(keys):
        raise ValueError("Missing receipts")
    checked = {key: Receipt.model_validate(receipts[key]) for key in keys}
    for key,r in checked.items():
        if any(n<=0 for n in r.rows) or len(set(r.rows))!=len(r.rows) or any(len(s)>600 for s in r.changes):
            raise ValueError("Invalid receipt evidence")
        if r.status=="updated" and (not r.verified or not r.rows):
            raise ValueError("Missing write verification")
        if key!="as_update" and r.status=="updated" and len(r.rows)!=1:
            raise ValueError("Only one roster/member is allowed")
        if r.status in {"unknown","blocked"} and r.verified:
            raise ValueError("Uncertain write cannot be verified")
        if r.status=="skipped" and (r.rows or r.changes or (r.verified and key!="as_update")):
            raise ValueError("Invalid skipped stage")
    roster, cases, member = (checked[k] for k in keys)
    if (cases.verified or cases.status=="unknown") and not roster.verified:
        raise ValueError("AS cannot precede roster verification")
    if (member.verified or member.status=="unknown") and not (roster.verified and cases.verified):
        raise ValueError("Member cannot precede Sheets verification")
    region = value.get("region")
    if region not in {None, "울진", "영덕", "광명"} or ((roster.verified or roster.status=="unknown") and region is None):
        raise ValueError("Missing resolved roster region")
    complete = all(r.verified for r in checked.values())
    if (value["status"]=="completed") != complete:
        raise ValueError("Invalid completion")
    if any(r.status=="unknown" for r in checked.values()) and value["status"]!="failed":
        raise ValueError("Invalid uncertain result")
    return {"status":value["status"], "response":response, "region":region, "receipts":{k:r.model_dump() for k,r in checked.items()}}


@router.post("/information-runs")
async def run(body: InformationInput):
    if not body.message.strip():
        raise HTTPException(422, detail="한 가입자의 수정 요청을 입력해 주세요.")
    started, clock = datetime.now(timezone.utc).isoformat(), monotonic()
    url = get_chat_settings().agent_server_url
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(540,connect=5,pool=5),follow_redirects=False) as client:
            response = await client.get(f"{url}/assistants/{ASSISTANT_ID}/schemas")
            if response.status_code==404:
                raise HTTPException(409, detail="정보확인&수정을 활성화하려면 Agent Server를 재시작해 주세요.")
            response.raise_for_status()
            if response.json().get("input_schema",{}).get("properties",{}).get("information_version",{}).get("const")!="2":
                raise HTTPException(409, detail="정보확인&수정을 활성화하려면 Agent Server를 재시작해 주세요.")
            response = await client.post(f"{url}/runs/wait",json={
                "assistant_id":GRAPH,"input":{**body.model_dump(exclude={"workflow_id"}),"information_version":"2"},
                "on_completion":"delete","on_disconnect":"continue","config":{"recursion_limit":8}})
            response.raise_for_status()
            if len(response.content)>1_000_000:
                raise ValueError("Oversized result")
            result = normalize(response.json())
    except (httpx.HTTPError,ValueError,TypeError,AttributeError):
        raise HTTPException(502,detail="결과를 확인하지 못했습니다. 재실행 전에 명부·AS·마스터페이지를 확인해 주세요.") from None
    return {"workflow_id":body.workflow_id,"id":str(uuid4()),"started_at":started,"duration_ms":round((monotonic()-clock)*1000),**result}
