from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.persistence import ArtifactStore, ReportValidationError

VALID_REPORT = """# Scout Report

## Topic

Example topic

## Summary

A concise summary.

## Key Findings

- A supported finding.

## Sources

- [Example](https://example.com/article)
"""


def test_report_persistence_and_append_only_execution_log(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    run_id = store.create_run()
    store.append_event(run_id, "search_completed", result_count=2)
    store.append_event(run_id, "fetch_completed", page_count=1)

    artifact = store.save_report(
        run_id,
        VALID_REPORT,
        fetched_urls={"https://example.com/article"},
    )

    report_path = tmp_path / artifact.report_artifact
    log_path = tmp_path / artifact.log_artifact
    assert report_path.read_text(encoding="utf-8") == VALID_REPORT
    assert not (report_path.parent / ".report.md.tmp").exists()
    records = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert [record["phase"] for record in records] == [
        "run_started",
        "search_completed",
        "fetch_completed",
        "report_saved",
    ]
    assert all(record["run_id"] == run_id for record in records)


def test_report_validation_rejects_unfetched_source(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    run_id = store.create_run()

    with pytest.raises(ReportValidationError, match="not fetched"):
        store.save_report(run_id, VALID_REPORT, fetched_urls=set())

    assert not (tmp_path / "runs" / run_id / "report.md").exists()


def test_report_validation_rejects_empty_required_section(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    run_id = store.create_run()
    report = VALID_REPORT.replace("A concise summary.", "   ")

    with pytest.raises(ReportValidationError, match="non-empty"):
        store.save_report(
            run_id,
            report,
            fetched_urls={"https://example.com/article"},
        )


def test_report_validation_rejects_unfetched_url_outside_sources(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    run_id = store.create_run()
    report = VALID_REPORT.replace(
        "A supported finding.",
        "Unsupported link: https://not-fetched.example/item",
    )

    with pytest.raises(ReportValidationError, match="not fetched"):
        store.save_report(
            run_id,
            report,
            fetched_urls={"https://example.com/article"},
        )
