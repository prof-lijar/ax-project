"""Durable producer, leased consumers, and deterministic export finalizer."""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import zipfile
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from ax_contracts import (
    ArtifactRef,
    NarrativeGenerationMetadata,
    WardWeeklyMetrics,
    WardWeeklyReport,
    WeeklyReportBulkFailure,
    WeeklyReportBulkJobRequest,
    WeeklyReportBulkJobStatus,
    WeeklyReportBulkManifest,
    WeeklyReportRequest,
    WeeklyReportSourceResponse,
)
from ax_persistence import (
    BulkItemRecord,
    BulkJobStore,
    LocalBulkArtifactStore,
)
from pydantic import ValidationError

from workflows.weekly_report.agents.reporter import generate_narrative
from workflows.weekly_report.agents.reporter.fallback import build_fallback
from workflows.weekly_report.agents.reporter.prompt import PROMPT_VERSION
from workflows.weekly_report.domain import build_fact_package, render_report
from workflows.weekly_report.tools.source_repository import WeeklyReportSourceRepository

from .report_store import (
    WeeklyReportStorageRecord,
    WeeklyReportStorageUnavailable,
    WeeklyReportStore,
)

WEEKLY_REPORT_BULK_JOB_KIND = "weekly_report_export_v1"
_TERMINAL_STATES = {"completed", "partial", "failed", "cancelled", "expired"}
_STORAGE_ARTIFACT_BATCH_SIZE = 250
_LOG = logging.getLogger(__name__)


class WeeklyReportBulkExecutionError(Exception):
    """Safe top-level failure that leaves recoverable leases intact."""


class WeeklyReportBulkRunner:
    """Run one bulk job without placing report payloads in LangGraph state."""

    def __init__(
        self,
        store: BulkJobStore,
        artifacts: LocalBulkArtifactStore,
        source: WeeklyReportSourceRepository,
        model: Any,
        report_store: WeeklyReportStore,
        *,
        lease_seconds: int = 900,
        max_attempts: int = 3,
        claim_size: int = 1,
        poll_seconds: float = 0.1,
        retention_days: int = 7,
        item_timeout_seconds: float = 60.0,
        owner_prefix: str | None = None,
        item_semaphore: asyncio.Semaphore | None = None,
    ) -> None:
        if lease_seconds < 30 or not 1 <= max_attempts <= 3 or claim_size < 1:
            raise ValueError("bulk runner limits are invalid")
        if item_timeout_seconds <= 0:
            raise ValueError("bulk item timeout must be positive")
        if item_semaphore is not None and claim_size != 1:
            raise ValueError("shared bulk item concurrency requires claim_size=1")
        self.store = store
        self.artifacts = artifacts
        self.source = source
        self.model = model
        self.report_store = report_store
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts
        self.claim_size = claim_size
        self.poll_seconds = poll_seconds
        self.retention_days = retention_days
        self.item_timeout_seconds = item_timeout_seconds
        self.item_semaphore = item_semaphore
        base_owner = owner_prefix or socket.gethostname()
        self.owner_prefix = f"{base_owner}:{uuid4().hex[:8]}"

    async def run(self, job_id: UUID, *, concurrency: int) -> WeeklyReportBulkJobStatus:
        if not 1 <= concurrency <= 512:
            raise ValueError("bulk concurrency must be between 1 and 512")
        self.artifacts.ensure_capacity()
        job = await self.store.get_job(job_id)
        if job.job_kind != WEEKLY_REPORT_BULK_JOB_KIND:
            raise ValueError("bulk job kind is not supported by this runner")
        if job.status in _TERMINAL_STATES:
            return await bulk_job_status(self.store, job_id)
        _LOG.info(
            "bulk job started",
            extra={"job_id": str(job_id), "worker_concurrency": concurrency},
        )

        producer = asyncio.create_task(self._produce(job_id), name=f"producer-{job_id}")
        consumers = [
            asyncio.create_task(
                self._consume(job_id, f"{self.owner_prefix}:{index}"),
                name=f"consumer-{job_id}-{index}",
            )
            for index in range(concurrency)
        ]
        cancellation = asyncio.create_task(
            self._cancel_consumers_when_requested(job_id, consumers),
            name=f"cancellation-{job_id}",
        )
        try:
            producer_result = (await asyncio.gather(producer, return_exceptions=True))[
                0
            ]
            if isinstance(producer_result, BaseException):
                for consumer in consumers:
                    consumer.cancel()
                await asyncio.gather(*consumers, return_exceptions=True)
                await self._fail_job(job_id, producer_result, "producer")
            else:
                consumer_results = await asyncio.gather(
                    *consumers, return_exceptions=True
                )
                job = await self.store.get_job(job_id)
                if job.cancel_requested:
                    await self.store.cancel_pending_items(job_id)
                failures = [
                    result
                    for result in consumer_results
                    if isinstance(result, BaseException)
                    and not (
                        job.cancel_requested
                        and isinstance(result, asyncio.CancelledError)
                    )
                ]
                if failures:
                    await self._fail_job(job_id, failures[0], "consumer")
                else:
                    try:
                        await self._finalize(job_id)
                    except Exception as exc:  # noqa: BLE001 - terminal job boundary
                        await self._fail_job(job_id, exc, "finalizer")
        finally:
            cancellation.cancel()
            await asyncio.gather(cancellation, return_exceptions=True)
        try:
            await cleanup_weekly_report_exports(self.store, self.artifacts)
        except Exception:  # noqa: BLE001 - retention must not fail generated reports
            _LOG.exception("weekly report ZIP cleanup failed; retry on worker sweep")
        status = await bulk_job_status(self.store, job_id)
        _LOG.info(
            "bulk job finished",
            extra={
                "job_id": str(job_id),
                "status": status.status,
                "completed_count": status.completed_count,
                "failed_count": status.failed_count,
                "fallback_count": status.fallback_count,
            },
        )
        return status

    async def _produce(self, job_id: UUID) -> None:
        owner = f"{self.owner_prefix}:producer"
        while not await self.store.claim_producer(job_id, owner, self.lease_seconds):
            job = await self.store.get_job(job_id)
            if job.producer_done or job.status in _TERMINAL_STATES:
                return
            await asyncio.sleep(self.poll_seconds)
        job = await self.store.get_job(job_id)
        request = WeeklyReportBulkJobRequest.model_validate(job.request)
        cursor = job.cursor or request.cursor
        warnings = list(job.warnings)
        existing_items = await self.store.list_items(job_id)
        discovered = len(existing_items)
        seen_item_keys = {item.item_key for item in existing_items}

        while discovered < request.max_reports:
            job = await self.store.get_job(job_id)
            if job.cancel_requested:
                await self.store.cancel_pending_items(job_id)
                await self.store.finish_producer(
                    job_id,
                    next_cursor=cursor,
                    selection_truncated=cursor is not None,
                    warnings=sorted(set(warnings))[:100],
                )
                await self.store.request_cancel(job_id)
                return
            page_request = WeeklyReportRequest(
                week_start=request.week_start,
                timezone=request.timezone,
                cursor=cursor,
                limit=min(100, request.max_reports - discovered),
            )
            source = WeeklyReportSourceResponse.model_validate(
                await self.source.load(page_request)
            )
            self._validate_source(page_request, source)
            refreshed_job = await self.store.get_job(job_id)
            if refreshed_job.cancel_requested:
                await self.store.cancel_pending_items(job_id)
                await self.store.finish_producer(
                    job_id,
                    next_cursor=cursor,
                    selection_truncated=cursor is not None,
                    warnings=sorted(set(warnings))[:100],
                )
                await self.store.request_cancel(job_id)
                return
            staged: list[BulkItemRecord] = []
            for metrics in source.items:
                item_key = f"{metrics.ward_id:020d}"
                if item_key in seen_item_keys:
                    raise ValueError(
                        "weekly-report source returned a duplicate ward page"
                    )
                artifact = await asyncio.to_thread(
                    self.artifacts.write_json,
                    job_id,
                    f"inputs/{metrics.ward_id}.json",
                    metrics.model_dump(mode="json"),
                )
                staged.append(
                    BulkItemRecord(
                        job_id=job_id,
                        item_key=item_key,
                        payload_uri=artifact.uri,
                        payload_checksum=artifact.sha256,
                    )
                )
                seen_item_keys.add(item_key)
            warnings.extend(source.warnings)
            warnings.extend(
                f"ward-{item.ward_id}:{item.reason}" for item in source.skipped
            )
            next_cursor = source.next_cursor
            await self.store.stage_items(job_id, staged, next_cursor)
            discovered += len(staged)
            await self.store.heartbeat_producer(job_id, owner, self.lease_seconds)
            if next_cursor == cursor and next_cursor is not None:
                raise ValueError("weekly-report source returned a non-advancing cursor")
            if next_cursor is None:
                cursor = next_cursor
                break
            cursor = next_cursor

        await self.store.finish_producer(
            job_id,
            next_cursor=cursor,
            selection_truncated=cursor is not None
            and discovered >= request.max_reports,
            warnings=sorted(set(warnings))[:100],
        )

    async def _consume(self, job_id: UUID, owner: str) -> None:
        while True:
            job = await self.store.get_job(job_id)
            if job.cancel_requested:
                await self.store.cancel_pending_items(job_id)
                return
            if self.item_semaphore is None:
                claimed = await self._claim_and_process(job_id, owner)
            else:
                async with self.item_semaphore:
                    claimed = await self._claim_and_process(job_id, owner)
            if claimed:
                continue
            counts = await self.store.item_counts(job_id)
            if (
                job.producer_done
                and not counts.get("pending")
                and not counts.get("leased")
            ):
                return
            if job.status in _TERMINAL_STATES:
                return
            await asyncio.sleep(self.poll_seconds)

    async def _claim_and_process(
        self, job_id: UUID, owner: str
    ) -> list[BulkItemRecord]:
        claimed = await self.store.claim_items(
            job_id, owner, self.claim_size, self.lease_seconds
        )
        if claimed:
            await asyncio.gather(*(self._process_item(item, owner) for item in claimed))
        return claimed

    async def _cancel_consumers_when_requested(
        self, job_id: UUID, consumers: list[asyncio.Task[None]]
    ) -> None:
        cancellation_applied = False
        while True:
            job = await self.store.get_job(job_id)
            if job.cancel_requested and not cancellation_applied:
                for consumer in consumers:
                    consumer.cancel()
                await asyncio.gather(*consumers, return_exceptions=True)
                await self.store.cancel_pending_items(job_id)
                cancellation_applied = True
            if job.status in _TERMINAL_STATES:
                return
            await asyncio.sleep(min(self.poll_seconds, 0.1))

    async def _process_item(self, item: BulkItemRecord, owner: str) -> None:
        try:
            metrics = WardWeeklyMetrics.model_validate(
                await asyncio.to_thread(
                    self.artifacts.read_verified_json,
                    item.payload_uri,
                    item.payload_checksum,
                )
            )
            facts = build_fact_package(metrics)
            try:
                narrative, generation_mode, generation = await asyncio.wait_for(
                    generate_narrative(self.model, facts),
                    timeout=self.item_timeout_seconds,
                )
            except TimeoutError:
                narrative = build_fallback(facts)
                generation_mode = "template_fallback"
                generation = NarrativeGenerationMetadata(
                    prompt_version=PROMPT_VERSION,
                    model=_model_name(self.model),
                    validation_status="fallback",
                    fallback_reason="bulk_item_timeout",
                )
            report = render_report(metrics, narrative, generation_mode, generation)
            artifact = await asyncio.to_thread(
                self.artifacts.write_json,
                item.job_id,
                f"reports/{metrics.ward_id}.json",
                report.model_dump(mode="json"),
            )
            await self.store.complete_item(
                item.job_id,
                item.item_key,
                owner,
                output_uri=artifact.uri,
                output_checksum=artifact.sha256,
                generation_mode=generation_mode,
            )
        except Exception as exc:  # noqa: BLE001 - isolate one untrusted item
            _LOG.warning(
                "bulk item failed",
                extra={"job_id": str(item.job_id), "error_code": _error_code(exc)},
            )
            await self.store.fail_item(
                item.job_id,
                item.item_key,
                owner,
                _error_code(exc),
                self.max_attempts,
            )

    async def _fail_job(
        self,
        job_id: UUID,
        error: BaseException,
        stage: str,
    ) -> None:
        _LOG.error(
            "weekly report bulk stage failed",
            extra={
                "job_id": str(job_id),
                "stage": stage,
                "error_code": _error_code(error),
            },
        )
        try:
            await self.store.cancel_pending_items(job_id)
            await self.store.set_job_status(job_id, "failed")
        except Exception as exc:
            raise WeeklyReportBulkExecutionError(
                "weekly report bulk failure could not be persisted"
            ) from exc

    async def _finalize(self, job_id: UUID) -> None:
        owner = f"{self.owner_prefix}:finalizer"
        while not await self.store.try_start_finalizer(
            job_id, owner, max(self.lease_seconds, 1800)
        ):
            job = await self.store.get_job(job_id)
            if job.status in _TERMINAL_STATES:
                return
            await asyncio.sleep(self.poll_seconds)
        job = await self.store.get_job(job_id)
        items = await self.store.list_items(job_id)
        completed = [item for item in items if item.status == "completed"]

        def read_report(item: BulkItemRecord) -> WardWeeklyReport:
            if not item.output_uri or not item.output_checksum:
                raise WeeklyReportBulkExecutionError(
                    "completed bulk item is missing its output artifact"
                )
            return WardWeeklyReport.model_validate(
                self.artifacts.read_verified_json(item.output_uri, item.output_checksum)
            )

        def write_jsonl(stream: Any) -> None:
            for item in completed:
                stream.write((read_report(item).model_dump_json() + "\n").encode())

        jsonl_artifact = await asyncio.to_thread(
            self.artifacts.write_file, job_id, "reports.jsonl", write_jsonl
        )
        failures = [
            WeeklyReportBulkFailure(
                ward_id=int(item.item_key),
                error_code=item.error_code or item.status,
                attempts=item.attempt_count,
            )
            for item in items
            if item.status in {"failed", "cancelled"}
        ]
        terminal_status = (
            "cancelled"
            if job.cancel_requested
            else "partial"
            if failures
            else "completed"
        )
        request = WeeklyReportBulkJobRequest.model_validate(job.request)
        manifest = WeeklyReportBulkManifest(
            job_id=job_id,
            request=request,
            status=terminal_status,
            report_count=len(completed),
            fallback_count=sum(
                item.generation_mode == "template_fallback" for item in completed
            ),
            failures=failures,
            selection_truncated=job.selection_truncated,
            next_cursor=job.next_cursor,
            prompt_version=PROMPT_VERSION,
            model=_model_name(self.model),
            reports_jsonl_sha256=jsonl_artifact.sha256,
            created_at=job.created_at,
        )

        def write_zip(stream: Any) -> None:
            with zipfile.ZipFile(
                stream, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                archive.writestr("manifest.json", manifest.model_dump_json(indent=2))
                archive.write(
                    self.artifacts.local_path(jsonl_artifact.uri), "reports.jsonl"
                )
                for item in completed:
                    report = read_report(item)
                    archive.writestr(f"reports/{report.ward_id}.md", report.markdown)
                    archive.writestr(
                        f"json/{report.ward_id}.json",
                        report.template_data.model_dump_json(indent=2),
                    )

        export = await asyncio.to_thread(
            self.artifacts.write_file, job_id, "weekly-reports.zip", write_zip
        )
        if request.persist_reports:
            stored_count = await self.report_store.upsert_reports(
                self._storage_records(completed, read_report)
            )
            if stored_count != len(completed):
                raise WeeklyReportStorageUnavailable(
                    "weekly-report storage count did not match generated reports"
                )
            _LOG.info(
                "weekly reports stored",
                extra={"job_id": str(job_id), "stored_count": stored_count},
            )
        await self.store.finish_job(
            job_id,
            status=terminal_status,
            export_uri=export.uri,
            export_checksum=export.sha256,
            expires_at=datetime.now(UTC) + timedelta(days=self.retention_days),
        )

    @staticmethod
    async def _storage_records(
        completed: list[BulkItemRecord],
        read_report: Callable[[BulkItemRecord], WardWeeklyReport],
    ) -> AsyncIterator[WeeklyReportStorageRecord]:
        for offset in range(0, len(completed), _STORAGE_ARTIFACT_BATCH_SIZE):
            item_batch = completed[offset : offset + _STORAGE_ARTIFACT_BATCH_SIZE]

            def load_batch(
                items: list[BulkItemRecord],
            ) -> list[WeeklyReportStorageRecord]:
                return [
                    WeeklyReportStorageRecord.from_report(read_report(item))
                    for item in items
                ]

            records = await asyncio.to_thread(load_batch, item_batch)
            for record in records:
                yield record

    @staticmethod
    def _validate_source(
        request: WeeklyReportRequest, source: WeeklyReportSourceResponse
    ) -> None:
        if (
            source.week_start != request.week_start
            or source.timezone != request.timezone
        ):
            raise ValueError("weekly-report source returned a mismatched period")
        ward_ids = [item.ward_id for item in source.items]
        if ward_ids != sorted(set(ward_ids)):
            raise ValueError(
                "weekly-report source returned duplicate or unordered wards"
            )


async def cleanup_weekly_report_exports(
    store: BulkJobStore, artifacts: LocalBulkArtifactStore
) -> int:
    """Keep the five newest terminal exports; preserve reports and active work."""
    removed = 0
    for job in await store.export_cleanup_jobs(WEEKLY_REPORT_BULK_JOB_KIND, keep=5):
        # Delete first: failed filesystem operations remain eligible for retry.
        removed += await asyncio.to_thread(
            artifacts.remove_file, job.job_id, "weekly-reports.zip"
        )
        if job.export_uri is not None:
            await store.clear_export(job.job_id, job.export_uri)
    return removed


async def bulk_job_status(
    store: BulkJobStore, job_id: UUID
) -> WeeklyReportBulkJobStatus:
    job = await store.get_job(job_id)
    request = WeeklyReportBulkJobRequest.model_validate(job.request)
    counts = await store.item_counts(job_id)
    return WeeklyReportBulkJobStatus(
        job_id=job.job_id,
        status=job.status,
        week_start=request.week_start,
        timezone=request.timezone,
        max_reports=request.max_reports,
        discovered_count=sum(
            counts.get(name, 0)
            for name in ("pending", "leased", "completed", "failed", "cancelled")
        ),
        pending_count=counts.get("pending", 0),
        running_count=counts.get("leased", 0),
        completed_count=counts.get("completed", 0),
        fallback_count=counts.get("fallback", 0),
        failed_count=counts.get("failed", 0) + counts.get("cancelled", 0),
        producer_done=job.producer_done,
        selection_truncated=job.selection_truncated,
        next_cursor=job.next_cursor,
        warnings=list(job.warnings),
        export=(
            ArtifactRef(
                uri=job.export_uri,
                artifact_type="application/zip",
                checksum=job.export_checksum,
                version="1",
            )
            if job.export_uri
            else None
        ),
        created_at=job.created_at,
        updated_at=job.updated_at,
        expires_at=job.expires_at,
    )


def _error_code(exc: BaseException) -> str:
    if isinstance(exc, WeeklyReportStorageUnavailable):
        return "report_storage_error"
    if isinstance(exc, ValidationError):
        return "invalid_contract"
    if isinstance(exc, (OSError, ValueError, json.JSONDecodeError)):
        return "artifact_or_data_error"
    return "report_generation_error"


def _model_name(model: Any) -> str | None:
    settings = getattr(model, "settings", None)
    value = getattr(settings, "model", None)
    return str(value)[:256] if value else None
