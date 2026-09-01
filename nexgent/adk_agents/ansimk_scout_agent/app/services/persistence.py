from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.tools.web import UnsafeUrlError, _canonicalize_url_syntax

RUN_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
URL_PATTERN = re.compile(r"https?://[^\s)>\]}]+")
REQUIRED_HEADINGS = (
    "# Scout Report",
    "## Topic",
    "## Summary",
    "## Key Findings",
    "## Sources",
)


class ReportValidationError(ValueError):
    """Raised when the agent's Markdown output violates the report contract."""


@dataclass(frozen=True, slots=True)
class ReportArtifact:
    report_artifact: str
    log_artifact: str
    sources: list[str]


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.runs_root = self.root / "runs"

    def create_run(self, *, started_at: datetime | None = None) -> str:
        run_id = uuid.uuid4().hex
        run_dir = self.runs_root / run_id
        run_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.append_event(run_id, "run_started", timestamp=started_at)
        return run_id

    def append_event(
        self,
        run_id: str,
        phase: str,
        *,
        timestamp: datetime | None = None,
        **metadata: object,
    ) -> None:
        run_dir = self._run_dir(run_id)
        run_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        log_path = run_dir / "execution.jsonl"
        occurred_at = timestamp or datetime.now(UTC)
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("event timestamp must be timezone-aware")
        record = {
            "timestamp": occurred_at.astimezone(UTC).isoformat(),
            "run_id": run_id,
            "phase": phase,
            **metadata,
        }
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
        os.chmod(log_path, 0o600)

    def save_report(
        self,
        run_id: str,
        report: str,
        *,
        fetched_urls: set[str] | list[str],
    ) -> ReportArtifact:
        sources = self.validate_report(report, fetched_urls=set(fetched_urls))
        run_dir = self._run_dir(run_id)
        report_path = run_dir / "report.md"
        temporary_path = run_dir / ".report.md.tmp"
        temporary_path.write_text(report, encoding="utf-8")
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, report_path)
        self.append_event(
            run_id,
            "report_saved",
            artifact=f"runs/{run_id}/report.md",
            source_count=len(sources),
        )
        return ReportArtifact(
            report_artifact=f"runs/{run_id}/report.md",
            log_artifact=f"runs/{run_id}/execution.jsonl",
            sources=sources,
        )

    def validate_report(self, report: str, *, fetched_urls: set[str]) -> list[str]:
        heading_matches = list(
            re.finditer(
                r"(?m)^(# Scout Report|## Topic|## Summary|## Key Findings|## Sources)\s*$",
                report,
            )
        )
        headings = [match.group(1) for match in heading_matches]
        if headings != list(REQUIRED_HEADINGS):
            raise ReportValidationError("report is missing required ordered Markdown sections")

        for index, heading in enumerate(REQUIRED_HEADINGS[1:], start=1):
            section_start = heading_matches[index].end()
            section_end = (
                heading_matches[index + 1].start()
                if index + 1 < len(heading_matches)
                else len(report)
            )
            if not report[section_start:section_end].strip():
                raise ReportValidationError(f"report section {heading} must be non-empty")

        sources_section = report[heading_matches[-1].end() :]
        sources: list[str] = []
        for match in URL_PATTERN.findall(sources_section):
            try:
                source = _canonicalize_url_syntax(match.rstrip(".,;:"))
            except UnsafeUrlError:
                continue
            if source not in sources:
                sources.append(source)
        if not sources:
            raise ReportValidationError("report Sources section must contain a fetched URL")
        canonical_fetched = {_canonicalize_url_syntax(url) for url in fetched_urls}
        all_report_urls: list[str] = []
        for match in URL_PATTERN.findall(report):
            try:
                url = _canonicalize_url_syntax(match.rstrip(".,;:"))
            except UnsafeUrlError:
                continue
            if url not in all_report_urls:
                all_report_urls.append(url)
        if unfetched := [url for url in all_report_urls if url not in canonical_fetched]:
            raise ReportValidationError(f"report cites URL that was not fetched: {unfetched[0]}")
        return sources

    def _run_dir(self, run_id: str) -> Path:
        if not RUN_ID_PATTERN.fullmatch(run_id):
            raise ValueError("invalid run ID")
        return self.runs_root / run_id
