"""Agent notification clients read the unified env, independently of backend env."""

from pathlib import Path

import yaml

from apps.weekly_report_scheduler.notification import AGENT_ENV_FILE

ROOT = Path(__file__).parents[2]
CONTAINER_ENV = "/app/.env"


def unified_mount(consumer, source):
    mounts = consumer.get("volumes", [])
    return any(
        (isinstance(mount, str) and mount == f"{source}:{CONTAINER_ENV}:ro")
        or (
            isinstance(mount, dict)
            and mount.get("source") == source
            and mount.get("target") == CONTAINER_ENV
            and mount.get("read_only") is True
        )
        for mount in mounts
    )


def test_workspace_clients_share_root_configuration():
    assert AGENT_ENV_FILE == ROOT / ".env"
    services = yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]
    for name in ("weekly-report-scheduler", "weekly-report-monitor"):
        assert unified_mount(services[name], "./.env")
        assert "playground/weekly-reporter/.env" not in str(services[name])
    monitor = yaml.safe_load(
        (ROOT / "compose.weekly-report-monitor.prod.yaml").read_text()
    )["services"]["weekly-report-monitor"]
    assert unified_mount(monitor, "./agents/.env")


def test_parent_production_scheduler_clients_use_unified_file():
    services = yaml.safe_load((ROOT.parent / "compose.prod.yaml").read_text())[
        "services"
    ]
    for name in ("daily-risk-scheduler", "weekly-report-scheduler"):
        assert unified_mount(services[name], "./agents/.env"), (
            "Apply the reviewed docs/unified-env-parent-compose.patch after approval"
        )
        assert "/run/ax-notifications/prod.env" not in str(services[name])
        assert "playground/weekly-reporter/.env" not in str(services[name])
    # Backend and its sender remain outside the agents/ configuration boundary.
    assert (
        services["notification-worker"]["env_file"] == services["backend"]["env_file"]
    )


def test_parent_development_scheduler_clients_use_unified_file():
    services = yaml.safe_load((ROOT.parent / "compose.yaml").read_text())["services"]
    for name in ("daily-risk-scheduler", "weekly-report-scheduler"):
        assert unified_mount(services[name], "./agents/.env"), (
            "Apply the reviewed docs/unified-env-parent-compose.patch after approval"
        )
