"""Workflow-neutral desktop transport; AX768 owns dispatch and reply templates."""

import re

from app.api.operations_client import (
    WORKFLOW_ID,
    OperationsClient,
    OperationsResult,
    OperationsSettings,
    credential_destination,
    parse_result,
)
from app.models import AgentError
from app.utils.windows import get_token

ACTION_KEYWORDS = {"위치조정": "기기위치조정", "전원연결": "전원연결"}


def message_action(text):
    actions = {action for keyword, action in ACTION_KEYWORDS.items() if keyword in text}
    return next(iter(actions)) if len(actions) == 1 else None


def parse_unified_result(body):
    if not isinstance(body, dict):
        raise AgentError("Invalid AX768 result")
    status = body.get("status")
    workflow = body.get("workflow_id")
    if (
        body.get("api_version") != "1"
        or status
        not in {"completed", "disconnected", "not_found", "needs_confirmation", "blocked", "failed"}
        or body.get("verified") is not (status == "completed")
        or not (
            workflow is None
            and status == "needs_confirmation"
            or isinstance(workflow, str)
            and re.fullmatch(r"[a-z][a-z0-9_]{0,79}", workflow)
        )
    ):
        raise AgentError("Invalid AX768 response contract or verification")
    response = body.get("response")
    if (
        not isinstance(response, str)
        or not response.strip()
        or len(response) > 2000
        or any(ord(c) < 32 and c not in "\n\t" for c in response)
    ):
        raise AgentError("AX768 reply is invalid or too long; inspect the workflow result")
    if body.get("workflow_id") == WORKFLOW_ID:
        checked = parse_result(body)
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


class UnifiedOperationsClient(OperationsClient):
    endpoint = "/api/ax768/runs"
    # Only 위치조정 and 전원연결 are enabled in the desktop watcher. Do not let a keyword
    # mentioned inside another workflow's request select that other handler.
    workflow_id = WORKFLOW_ID
    parse_response = staticmethod(parse_unified_result)

    def request_payload(self, message):
        action = message_action(message)
        if action is None:
            raise AgentError("A single enabled action keyword is required; no workflow executed")
        return {**super().request_payload(message), "action": action}

    async def preflight(self, client):
        # The dispatcher checks the selected graph's version and write capabilities.
        pass


def create_unified_operations(config):
    settings = OperationsSettings.resolve(config)
    return UnifiedOperationsClient(
        settings,
        get_token(credential_destination(settings.url, settings.username), "OPERATIONS_PASSWORD"),
    )
