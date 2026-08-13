"""Regression tests for invoking the weekly-report runner as a file."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_weekly_report_runner_resolves_workspace_imports() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "playground" / "weekly_report.py"),
            "--help",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--week-start" in result.stdout
