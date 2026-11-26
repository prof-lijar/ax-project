import json
import threading

import httpx
import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from app.api.operations_client import OperationsSettings
from app.api.unified_operations import UnifiedOperationsClient
from app.api.workflow_requests import kakao_command
from app.gui.api_response_log import ApiResponseLog
from app.gui.main_window import Signals
from app.gui.theme import WindowText
from app.models import AgentError


@pytest.mark.parametrize("status,body", [
    (200, {"invalid_contract": "원본 응답"}),
    (422, {"detail": "요청 검증 실패"}),
    (503, "<html>Unavailable</html>"),
])
def test_raw_workflow_errors_reach_observer_without_auth_data(status, body):
    observed, calls = [], []

    def server(request):
        calls.append(request.url.path)
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={"secret": "login-data"})
        if request.url.path == "/api/me":
            return httpx.Response(200, json={"is_admin": True, "csrf_token": "secret-token"})
        return (httpx.Response(status, json=body) if isinstance(body, dict)
                else httpx.Response(status, text=body))

    client = UnifiedOperationsClient(
        OperationsSettings("https://example.test", "admin"), "password",
        httpx.MockTransport(server), response_observer=observed.append,
    )
    with pytest.raises(AgentError):
        client.run(kakao_command("기기분실/이영희/광명시 OO동 OO로 56"), threading.Event())
    assert len(observed) == 1
    assert observed[0]["http_status"] == status
    assert observed[0]["body"] == body
    assert observed[0]["endpoint"] == "/api/ax768/runs"
    assert "secret" not in json.dumps(observed)
    assert calls == ["/auth/login", "/api/me", "/api/ax768/runs"]


def test_json_view_receives_worker_events_and_preserves_complete_documents(qt_app):
    view = ApiResponseLog(WindowText("en"))
    signals = Signals()
    signals.api_response.connect(view.append_response)
    event = {"chat": "운영 테스트", "http_status": 200,
             "body": {"kakao-reply": "<b>원문 그대로</b>", "rows": list(range(350))}}
    try:
        thread = threading.Thread(target=lambda: signals.api_response.emit(event))
        thread.start()
        thread.join()
        qt_app.processEvents()
        parsed = json.loads(view.body.toPlainText())
        assert parsed["body"] == event["body"]
        assert parsed["chat"] == event["chat"]
        assert "\\uc6d0" not in view.body.toPlainText()
        copy = next(b for b in view.findChildren(QPushButton) if b.text() == "Copy JSON")
        copy.click()
        assert QApplication.clipboard().text() == view.body.toPlainText()
        view.append_response({"body": {"second": True}})
        view.selector.setCurrentIndex(0)
        view.append_response({"body": {"third": True}})
        assert json.loads(view.body.toPlainText())["body"] == event["body"]
        for i in range(60):
            view.append_response({"body": {"i": i}})
        assert len(view.responses) == view.selector.count() == 50
        assert json.loads(view.responses[0])["body"] == {"i": 10}
        view.clear()
        assert not view.responses and not view.body.toPlainText()
    finally:
        view.deleteLater()
