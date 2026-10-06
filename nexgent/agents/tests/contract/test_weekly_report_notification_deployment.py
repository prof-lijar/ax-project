"""Scheduler and monitor share the production backend's notification settings."""

from pathlib import Path

import yaml

from apps.weekly_report_scheduler.notification import PRODUCTION_NOTIFICATION_ENV

ROOT = Path(__file__).parents[2]


def test_production_consumers_share_one_read_only_backend_config():
    services = yaml.safe_load((ROOT.parent / "compose.prod.yaml").read_text())["services"]
    monitor = yaml.safe_load(
        (ROOT / "compose.weekly-report-monitor.prod.yaml").read_text()
    )["services"]["weekly-report-monitor"]
    backend_env = services["backend"]["env_file"][0]
    assert services["notification-worker"]["env_file"] == [backend_env]
    for consumer in (services["weekly-report-scheduler"], monitor):
        mounts = [mount for mount in consumer["volumes"] if isinstance(mount, dict)
                  and mount.get("target") == str(PRODUCTION_NOTIFICATION_ENV)]
        assert len(mounts) == 1
        assert mounts[0]["source"] == backend_env
        assert mounts[0]["read_only"] is True
        assert mounts[0]["bind"]["create_host_path"] is False
        assert not any(key.startswith("WEEKLY_REPORT_NOTIFICATION_")
                       for key in consumer.get("environment", {}))


def test_development_does_not_mount_production_notification_credentials():
    for path in (ROOT / "compose.yaml", ROOT.parent / "compose.yaml"):
        services = yaml.safe_load(path.read_text())["services"]
        for name in ("weekly-report-scheduler", "weekly-report-monitor"):
            if name in services:
                assert str(PRODUCTION_NOTIFICATION_ENV) not in str(services[name])
