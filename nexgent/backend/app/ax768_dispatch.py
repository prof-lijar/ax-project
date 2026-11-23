"""One authenticated AX768 entrypoint; workflow handlers retain verification authority."""
import re
import unicodedata
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app import ax768, ax768_information, ax768_workflow
from app.identity.router import require_admin

router = APIRouter(prefix="/api/ax768", tags=["ax768"], dependencies=[Depends(require_admin)])

# Add future workflows here with an explicit handler and grounded action aliases.
ACTIONS = {
    "device_adjustment_power": {
        "기기위치조정": "기기위치조정", "위치조정": "기기위치조정",
        "위치변경": "기기위치조정", "위치점검": "기기위치조정", "기기이동": "기기위치조정",
        "전원연결": "전원연결", "기기전원연결": "전원연결", "전원접속": "전원연결",
    },
    "information_update": {"정보수정": "정보수정", "정보변경": "정보수정", "정보확인&수정": "정보수정"},
}
CLARIFY = "[자동 확인]\n작업, 대상자 이름, 주소를 확인해 주세요. 예: 위치조정/이영희/광명시 OO동 OO로 56"


class DispatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    message: str = Field(min_length=1, max_length=8000)
    workflow_id: Literal["auto", "device_adjustment_power", "information_update"] = "auto"
    confirmed_name: str | None = Field(default=None, min_length=2, max_length=100)
    action: Literal["기기위치조정", "전원연결"] | None = None
    name: str | None = Field(default=None, min_length=2, max_length=100)
    address: str | None = Field(default=None, min_length=1, max_length=500)
    action_text: str | None = Field(default=None, min_length=1, max_length=500)


def compact(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def route_message(message):
    """Only explicit action fields authorize automatic writes, never keyword mentions."""
    fields = [value.strip() for value in unicodedata.normalize("NFKC", message).split("/")]
    matches = [(workflow, aliases[compact(field)], index)
               for workflow, aliases in ACTIONS.items()
               for index, field in enumerate(fields) if compact(field) in aliases]
    if len(matches) != 1:
        return None
    workflow, action, index = matches[0]
    if workflow == "information_update":
        # The existing grounded planner validates identity and requested new values.
        return workflow, message
    if len(fields) != 3:
        return None
    remaining = [field for i, field in enumerate(fields) if i != index]
    # Registered names may include an underscore-separated label. Preserve it
    # through lookup; stripping it would silently select a different identity.
    names = [field for field in remaining if re.fullmatch(r"[가-힣]{2,10}(?:_[가-힣]{2,10})?(?:님)?", compact(field))]
    if len(names) != 1:
        return None
    name = compact(names[0]).removesuffix("님")
    address = remaining[1] if remaining[0] == names[0] else remaining[0]
    if not re.search(r"[가-힣A-Za-z0-9·.]+(?:로|길)\s*\d+(?:\s*-\s*\d+)?", address):
        return None
    # Reject extra instructions disguised as identity/address fields.
    if not re.fullmatch(r"[가-힣A-Za-z0-9·.\s]+(?:로|길)\s*\d+(?:\s*-\s*\d+)?(?:\s+\d+동)?(?:\s+\d+호)?", address):
        return None
    return workflow, f"{address} {name}님 {action} 신호확인요."


def device_reply(result):
    """Build customer text only after the existing handler validates all receipts."""
    name = result["roster"]["name"]
    if result["status"] == "completed":
        action = "기기 전원연결" if result["member_note"]["note"].endswith("전원연결") else "기기 위치변경"
        return f"[자동 확인]\n{name}님 {action} 후 기기신호 확인 완료입니다.\n내용 기재해두었습니다.\n감사합니다. :)"
    roster_missing = (result["status"] == "not_found"
                      and result["roster"]["status"] == "not_found"
                      and result["signal"]["status"] == "skipped")
    if roster_missing:
        # No matched row exists: address the requested person, keeping the
        # not_found status and skipped write receipts intact for diagnostics.
        name = result["parsed"]["lookup_name"] or result["parsed"]["name"]
        if not name:
            return CLARIFY
    if result["status"] == "disconnected" or roster_missing:
        return f"[자동 확인]\n{name}님 신규설치 기기신호가 아직 확인되지 않습니다.\n기기 전원 및 설치 위치 확인 부탁드립니다. "
    return "[자동 확인]\n" + result["response"]


async def device_handler(body):
    result = await ax768_workflow.run(ax768_workflow.WorkflowInput(
        workflow_id="device_adjustment_power", message=body.message, confirmed_name=body.confirmed_name))
    if (body.action is not None and result["status"] == "completed"
            and not result["member_note"]["note"].endswith(" " + body.action)):
        raise HTTPException(502, detail="Completed device action differs from the request.")
    return {**result, "response": device_reply(result)}


async def information_handler(body):
    if body.confirmed_name is not None:
        raise HTTPException(422, detail="Information updates do not accept confirmed_name.")
    result = await ax768_information.run(ax768_information.InformationInput(
        workflow_id="information_update", message=body.message))
    return {**result, "response": "[자동 확인]\n" + result["response"]}


HANDLERS = {"device_adjustment_power": device_handler, "information_update": information_handler}


@router.post("/runs")
async def run(body: ax768.RunInput | DispatchInput):
    if isinstance(body, ax768.RunInput):
        return await ax768.run(body)
    if not body.message.strip():
        raise HTTPException(422, detail="Enter a request.")
    if body.name is not None or body.address is not None:
        if (body.name is None or body.address is None or body.action is None
                or body.workflow_id not in {"auto", "device_adjustment_power"}):
            raise HTTPException(422, detail="Provide the device action, full name and address together.")
        # The capture agent supplies analyzed fields. Validate those fields as a
        # complete request, and ground them in the unchanged source message.
        selected = route_message(f"{body.action}/{body.name}/{body.address}")
        def is_grounded(value):
            token = compact(value)
            pattern = (r"(?<![가-힣A-Za-z0-9_])" + r"\s*".join(map(re.escape, token))
                       + r"(?:님)?(?:은|는|이|가|을|를|의|에서|에)?(?=$|[^가-힣A-Za-z0-9_])")
            return bool(token and re.search(pattern, unicodedata.normalize("NFKC", body.message)))

        # Intent was selected by the capture agent. Validate literal identity and
        # action evidence, without requiring exact keywords or slash field order.
        known_action = ACTIONS["device_adjustment_power"].get(compact(body.action_text or ""))
        grounded = (is_grounded(body.name) and is_grounded(body.address)
                    and body.action_text is not None
                    and body.action_text in body.message
                    and known_action in {None, body.action}
                    and not re.search(r"취소|하지\s*마|아닙니다|하지\s*않", body.message))
        if selected is None or not grounded:
            return {"api_version": "1", "verified": False, "workflow_id": None, "status": "needs_confirmation", "response": CLARIFY}
        if body.workflow_id == "auto" and body.confirmed_name is not None:
            raise HTTPException(422, detail="Select a workflow before confirming a name.")
        body = body.model_copy(update={"workflow_id": selected[0], "message": selected[1]})
    if body.workflow_id == "auto":
        if body.confirmed_name is not None:
            raise HTTPException(422, detail="Select a workflow before confirming a name.")
        selection = route_message(body.message)
        if selection is None:
            return {"api_version": "1", "verified": False, "workflow_id": None, "status": "needs_confirmation", "response": CLARIFY}
        workflow, message = selection
        body = body.model_copy(update={"workflow_id": workflow, "message": message})
    elif body.workflow_id == "device_adjustment_power" and "/" in body.message:
        # A selected workflow still accepts the capture agent's verbatim slash
        # fields in any order, without letting text choose another handler.
        selection = route_message(body.message)
        if selection is None or selection[0] != body.workflow_id:
            return {"api_version": "1", "verified": False, "workflow_id": None, "status": "needs_confirmation", "response": CLARIFY}
        body = body.model_copy(update={"message": selection[1]})
    if body.action is not None:
        if body.workflow_id != "device_adjustment_power":
            raise HTTPException(422, detail="The action argument requires the device workflow.")
        actions = {action for alias, action in ACTIONS["device_adjustment_power"].items()
                   if alias in compact(body.message)}
        if actions != {body.action}:
            return {"api_version": "1", "verified": False, "workflow_id": None, "status": "needs_confirmation", "response": CLARIFY}
    result = await HANDLERS[body.workflow_id](body)
    return {**result, "api_version": "1", "verified": result["status"] == "completed"}
