"""Workflow-neutral desktop transport; AX768 owns dispatch and reply templates."""

import json
import re
from copy import deepcopy
from dataclasses import dataclass, replace

from app.api.device_request import compact
from app.api.operations_client import (
    WORKFLOW_ID,
    OperationsClient,
    OperationsResult,
    OperationsSettings,
    credential_destination,
    parse_result,
)
from app.api.workflow_requests import (
    INSTALLATION,
    device_command,
    installation_header,
    kakao_command,
    parse_analysis,
)
from app.models import AgentError
from app.utils.windows import get_token


@dataclass(frozen=True, kw_only=True)
class InstallationResult(OperationsResult):
    kakao_reply: str
    sms: dict
    subscriber_name: str = ""
    signal_status: str = "not_checked"
    issue_summary: str = ""


@dataclass(frozen=True, kw_only=True)
class GuardianAdditionResult(OperationsResult):
    sms: dict
    kakao_reply: str
    guardian_addition: bool = True


def kakao_reply(body):
    """Require ready-to-paste server text; never compose or fall back locally."""
    reply = body.get("kakao-reply")
    if (not isinstance(reply, str) or not reply.strip() or len(reply) > 2000
            or any(ord(c) < 32 and c not in "\r\n\t" for c in reply)):
        raise AgentError("AX768 must return a nonempty kakao-reply string of at most 2000 characters; no chat reply sent")
    if body.get("response") != reply:
        raise AgentError("AX768 response and kakao-reply must contain the same text; no chat reply sent")
    return reply


def installation_result(body, response):
    completed = body["status"] == "completed"
    reply, sms = body.get("kakao-reply"), body.get("sms")
    if (
        not isinstance(sms, dict)
        or (sms.get("should_send") and not completed)
    ):
        raise AgentError("Invalid AX768 installation reply or SMS decision")
    if completed:
        receipts = body.get("receipts")
        if not isinstance(receipts, dict) or not all(
            isinstance(receipts.get(stage), dict)
            and receipts[stage].get("verified") is True
            and receipts[stage].get("status") == "updated"
            and receipts[stage].get("rows")
            for stage in ("roster", "inventory", "member")
        ):
            raise AgentError("AX768 installation lacks verified registration receipts")
    if sms["should_send"]:
        recipients = sms.get("recipients")
        if (
            not isinstance(recipients, list)
            or not 1 <= len(recipients) <= 2
            or not all(
                isinstance(n, str) and re.fullmatch(r"01[016789][0-9]{7,8}", n) for n in recipients
            )
            or len(set(recipients)) != len(recipients)
            or type(body.get("guardian_count")) is not int
            or len(recipients) != body["guardian_count"]
            or not all(
                isinstance(sms.get(k), str) and sms[k].strip() and len(sms[k]) <= limit
                for k, limit in (("title", 100), ("text", 3000))
            )
        ):
            raise AgentError("Invalid AX768 guardian message or recipients")
    elif sms != {"should_send": False, "recipients": [], "title": "", "text": ""}:
        raise AgentError("Unexpected guardian message for incomplete registration")
    return InstallationResult(
        body["status"], response, completed, kakao_reply=reply, sms=sms,
        subscriber_name=body.get("subscriber_name", ""), signal_status=body.get("signal_status", "not_checked"),
        issue_summary=body.get("issue_summary", ""),
    )


def _parse_unified_result(body):
    if not isinstance(body, dict):
        raise AgentError("Invalid AX768 result")
    if body.get("workflow_id") == WORKFLOW_ID and body.get("ok") is True:
        # The server owns device completion. Its reply does not depend on the
        # desktop independently validating receipts or the duplicate Kakao field.
        response = body.get("response")
        if (not isinstance(response, str) or not response.strip() or len(response) > 2000
                or any(ord(c) < 32 and c not in "\r\n\t" for c in response)):
            raise AgentError("AX768 response must be nonempty text of at most 2000 characters; no chat reply sent")
        return OperationsResult("completed", response, True)
    status = body.get("status")
    workflow = body.get("workflow_id")
    if (
        body.get("api_version", "1") != "1"
        or not isinstance(status, str)
        or status
        not in {"completed", "disconnected", "not_found", "needs_confirmation", "blocked", "failed"}
        or body.get("verified") is not (status == "completed")
        or body.get("ok") is not (status == "completed")
        or not (
            workflow is None
            and status == "needs_confirmation"
            or isinstance(workflow, str)
            and re.fullmatch(r"[a-z][a-z0-9_]{0,79}", workflow)
        )
    ):
        raise AgentError("Invalid AX768 response contract or verification")
    execution_id, issues, sms = body.get("id"), body.get("issues"), body.get("sms")
    if (not isinstance(execution_id, str) or not execution_id.strip()
            or len(execution_id) > 200 or not execution_id.isprintable()):
        raise AgentError("AX768 response is missing a valid execution id")
    if (not isinstance(issues, list) or (status == "completed" and issues)
            or (status != "completed" and not issues)
            or any(not isinstance(issue, dict) or any(
                not isinstance(issue.get(key), str) or not issue[key].strip()
                for key in ("code", "stage", "message", "next_action")
            ) for issue in issues)):
        raise AgentError("AX768 issues do not match the overall outcome")
    if (not isinstance(sms, dict) or type(sms.get("should_send")) is not bool
            or (sms["should_send"] and (status != "completed" or workflow not in {INSTALLATION, "information_update"}))
            or (not sms["should_send"] and sms != {
                "should_send": False, "recipients": [], "title": "", "text": ""
            })):
        raise AgentError("Invalid AX768 SMS instructions")
    # OperationsResult.response is the delivery text throughout the desktop.
    # Only the API's dedicated Kakao field may supply it.
    response = kakao_reply(body)
    if workflow == INSTALLATION:
        return installation_result(body, response)
    if body.get("workflow_id") == WORKFLOW_ID:
        checked = parse_result({**body, "response": response})
        return OperationsResult(checked.status, response, checked.completed)
    if body.get("workflow_id") is None and body.get("status") == "needs_confirmation":
        return OperationsResult("needs_confirmation", response)
    if body.get("workflow_id") == "information_update" and body.get("status") in {
        "completed",
        "blocked",
        "failed",
    }:
        completed = body["status"] == "completed"
        if completed:
            receipts = body.get("receipts", {})
            if not isinstance(receipts, dict) or set(receipts) != {
                "roster",
                "as_update",
                "member_note",
            }:
                raise AgentError("AX768 completion lacks verified receipts")
            for key, receipt in receipts.items():
                if (
                    not isinstance(receipt, dict)
                    or receipt.get("verified") is not True
                    or not (
                        receipt.get("status") == "updated"
                        and receipt.get("rows")
                        or key == "as_update"
                        and receipt.get("status") == "skipped"
                    )
                ):
                    raise AgentError("AX768 completion lacks verified receipts")
        return OperationsResult(body["status"], response, completed)
    # New workflows use the same server-verified envelope. Their registered
    # handlers own receipt validation before the dispatcher sets verified=True.
    return OperationsResult(status, response, status == "completed")


def parse_unified_result(body):
    result = _parse_unified_result(body)
    return replace(result, api_response=deepcopy(body))


class UnifiedOperationsClient(OperationsClient):
    endpoint = "/api/ax768/runs"
    # The model may choose only the two actions within this device workflow.
    workflow_id = WORKFLOW_ID
    parse_response = staticmethod(parse_unified_result)

    def parse_run_result(self, body, payload):
        result = self.parse_response(body)
        if body.get("workflow_id") != payload["workflow_id"] and not (
            (payload["workflow_id"] == WORKFLOW_ID or payload.get("source") == "kakao")
            and body.get("workflow_id") is None
            and result.status == "needs_confirmation"
        ):
            raise AgentError("AX768 returned a different workflow than requested")
        sms = body.get("sms")
        if isinstance(sms, dict) and sms.get("should_send") and body["workflow_id"] != INSTALLATION:
            fields = [s.strip() for s in payload["message"].split("/")]
            if (payload.get("source") != "kakao" or payload["workflow_id"] != "information_update" or not result.completed
                    or compact(fields[0]) != "보호자추가" or len(fields) != 6):
                raise AgentError("Unexpected guardian notification for this request")
            number = re.sub(r"\D", "", fields[4])
            if (sms["should_send"] is not True or sms.get("recipients") != [number]
                    or not re.fullmatch(r"[0-9() +.\-]+", fields[4])
                    or not re.fullmatch(r"010[0-9]{8}", number)
                    or not all(isinstance(sms.get(k), str) and sms[k].strip() and len(sms[k]) <= limit
                               for k, limit in (("title", 100), ("text", 3000)))):
                raise AgentError("Invalid guardian addition SMS instructions")
            return GuardianAdditionResult(result.status, result.response, True, sms=sms,
                                          kakao_reply=result.response, api_response=result.api_response)
        return result

    def request_payload(self, request):
        if (isinstance(request, dict) and request.get("workflow_id") == WORKFLOW_ID
                and set(request) == {"workflow_id", "message", "confirmed_name"}):
            if device_command(request.get("message")) != request:
                raise AgentError("An incoming device action command is required; no workflow executed")
            return request
        if isinstance(request, dict) and request.get("source") == "kakao":
            expected = kakao_command(request.get("message"), request.get("manager", ""), request.get("received_date", ""))
            if expected != request:
                raise AgentError("AX768 workflow does not match the received Kakao command")
            return request
        if isinstance(request, dict) and request.get("workflow_id") == INSTALLATION:
            if (
                set(request) != {"workflow_id", "message"}
                or not installation_header(request["message"])
                or len(request["message"]) > 8000
            ):
                raise AgentError("A complete incoming installation form is required")
            return request
        if not isinstance(request, dict) or set(request) != {
            "message",
            "action",
            "action_text",
            "name",
            "address",
        }:
            raise AgentError("A grounded structured action is required; no workflow executed")
        source = request["message"]
        if not isinstance(source, str) or not source.strip():
            raise AgentError("Original request text is required; no workflow executed")
        analysis = parse_analysis(
            json.dumps({k: v for k, v in request.items() if k != "message"}), source
        )
        if analysis is None:
            raise AgentError("An actionable request is required; no workflow executed")
        # Older stored plans may still contain extracted fields for a slash
        # command. They use the same web payload; free-form reports keep their
        # existing grounded intent fields.
        return device_command(source) or {
            "workflow_id": self.workflow_id, "confirmed_name": None, **analysis
        }

    async def preflight(self, client):
        # The dispatcher checks the selected graph's version and write capabilities.
        pass


def create_unified_operations(config):
    settings = OperationsSettings.resolve(config)
    return UnifiedOperationsClient(
        settings,
        get_token(credential_destination(settings.url, settings.username), "OPERATIONS_PASSWORD"),
    )
