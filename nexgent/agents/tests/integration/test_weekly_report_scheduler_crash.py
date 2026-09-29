"""A killed scheduler cannot notify; another process must observe its state."""

import json
import subprocess
import sys
from datetime import datetime, timedelta

from apps.weekly_report_scheduler.monitor import monitor_once
from apps.weekly_report_scheduler.notification import NotificationSettings


def test_monitor_alerts_after_scheduler_is_killed(tmp_path):
    code = """
import sys
import time
from pathlib import Path
from apps.weekly_report_scheduler.status import RunStatus
run = RunStatus(Path(sys.argv[1]), '2026-09-21', interval=0.05)
run.start()
run.update(stage='generation')
print('ready', flush=True)
time.sleep(60)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", code, str(tmp_path)], stdout=subprocess.PIPE, text=True
    )
    try:
        # communicate timeout prevents a broken startup from hanging the suite.
        import selectors

        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            assert selector.select(timeout=10), "scheduler did not start"
        assert process.stdout.readline().strip() == "ready"
        process.kill()  # SIGKILL: no exception/finally handler can run.
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()
    record = json.loads(next((tmp_path / "runs").glob("*.json")).read_text())
    assert record["status"] == "running"
    sent = []
    monitor_once(
        tmp_path,
        settings=NotificationSettings(True, "http://backend:8000", "x" * 32),
        now=datetime.fromisoformat(record["heartbeat_at"]) + timedelta(seconds=301),
        send=lambda settings, event: sent.append(event) or {"id": "test", "status": "queued"},
    )
    assert len(sent) == 1
    assert "스케줄러 응답 없음" in sent[0]["payload"]["text"]
    assert "리포트 생성·로컬 저장" in sent[0]["payload"]["text"]
