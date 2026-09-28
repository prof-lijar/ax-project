"""Content-free metadata shared by weekly-report source and worker logs."""

from contextvars import ContextVar

SOURCE_JOB_ID: ContextVar[str | None] = ContextVar("weekly_source_job_id", default=None)

DIAGNOSTIC_FIELDS = (
    "job_id",
    "week_start",
    "stage",
    "status",
    "worker_concurrency",
    "item_concurrency",
    "completed_count",
    "failed_count",
    "fallback_count",
    "ward_id",
    "error_code",
    "error_type",
    "cause_type",
    "http_status",
    "attempt",
    "max_attempts",
    "retryable",
    "retry_in_seconds",
    "elapsed_seconds",
    "timeout_seconds",
    "report_count",
    "active_jobs",
    "active_job_limit",
)
