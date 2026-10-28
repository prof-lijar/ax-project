"""Aggregate-only operational status, outside the reconciliation transaction."""

from datetime import datetime

from workflows.daily_risk_counts.workflow import TIMEZONE


def status_payload(
    *, started_at: datetime, ended_at: datetime, issue: str | None = None
) -> dict:
    def timestamp(value: datetime) -> str:
        return value.astimezone(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S KST")

    text = "\n".join(
        [
            f"Status: {'Fail' if issue else 'Success'}",
            "Title: Daily Risk Count",
            f"Start time: {timestamp(started_at)}",
            f"End time: {timestamp(ended_at)}",
            f"Message: {issue or 'Successfully done!'}",
        ]
    )
    return {
        "destination": "daily_risk",
        "severity": "error" if issue else "success",
        "locale": "en",
        "text": text,
        "blocks": [{"type": "section", "text": {"type": "plain_text", "text": text}}],
    }
