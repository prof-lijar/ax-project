"""Deterministic operational failure copy; never infer report coverage."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

STAGES = {
    "configuration": "설정 확인",
    "submission": "작업 요청",
    "generation": "리포트 생성·로컬 저장",
    "migration": "운영 DB 업데이트",
    "notification": "저장 현황 알림",
    "schedule": "예약 실행",
}
REASONS = {
    "error": "작업 중 오류가 발생했습니다.",
    "terminated": "스케줄러 프로세스가 종료되었습니다.",
    "heartbeat": "5분 이상 스케줄러의 실행 신호가 없습니다. 중단 여부를 확인해 주세요.",
    "overdue": "전체 실행 시간이 27시간을 초과했습니다. 지연·정지 여부를 확인해 주세요.",
    "missed": "월요일 01:00 예약 시각 이후 15분 동안 실행이 확인되지 않았습니다.",
}
JOB_STATUSES = {
    "pending": "대기", "queued": "대기", "running": "진행 중",
    "finalizing": "로컬 저장 중",
    "completed": "완료", "partial": "일부 실패", "failed": "실패",
    "cancelled": "취소", "expired": "만료", "cancelling": "취소 중",
}


def failure_payload(record, *, observed_at, destination):
    reason = record.get("reason", "error")
    title = {
        "heartbeat": "주간 리포트 스케줄러 응답 없음",
        "overdue": "주간 리포트 작업 지연",
        "missed": "주간 리포트 예약 실행 누락",
    }.get(reason, "주간 리포트 작업 실패")
    start = date.fromisoformat(record["week_start"])
    rows = [
        ("보고 기간", f"{start:%Y/%m/%d} ~ {start + timedelta(days=6):%m/%d}"),
        ("확인 시각", datetime.fromisoformat(observed_at).astimezone(
            ZoneInfo("Asia/Seoul")).strftime("%Y/%m/%d %H:%M:%S (한국 시간)")),
        ("마지막 단계", STAGES.get(record["stage"], "미확인")),
    ]
    job = record.get("job", {})
    if job:
        rows.append(("마지막 작업 상태", JOB_STATUSES.get(job.get("status"), "미확인")))
        for key, label in (("discovered_count", "대상"), ("completed_count", "완료"),
                           ("failed_count", "실패"), ("pending_count", "대기"),
                           ("running_count", "진행 중")):
            if key in job:
                rows.append((f"마지막 배치 · {label}", f"{job[key]:,}건"))
        if job.get("job_id"):
            rows.append(("작업 ID", job["job_id"]))
    if record.get("run_id"):
        rows.append(("실행 ID", record["run_id"]))
    detail = REASONS.get(reason, REASONS["error"])
    note = (
        "• 운영 DB 업데이트는 완료됐으나 저장 현황 알림 단계가 완료되지 않았습니다.\n"
        if record["stage"] == "notification" else
        "• 운영 DB 업데이트 완료 여부는 이 알림만으로 확인할 수 없습니다.\n"
    )
    note += (
        "• 배치 건수는 마지막으로 확인한 작업 기준이며, 전체 가입자의 저장 성공·누락 집계가 아닙니다.\n"
        "• 해당 단계와 작업 ID의 로그를 확인해 주세요. 이 알림의 재전송은 리포트 작업을 다시 실행하지 않습니다."
    )
    return {
        "destination": destination, "severity": "error", "locale": "ko",
        "text": "\n".join([title, detail, *(f"{k}: {v}" for k, v in rows), note]),
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": title}},
            {"type": "section", "text": {"type": "plain_text", "text": detail}},
            {"type": "table", "rows": [
                [{"type": "raw_text", "text": k}, {"type": "raw_text", "text": v}]
                for k, v in [("항목", "현황"), *rows]
            ]},
            {"type": "section", "text": {"type": "plain_text", "text": note}},
        ],
    }
