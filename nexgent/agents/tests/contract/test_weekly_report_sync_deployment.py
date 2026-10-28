"""Production-only composition, credentials, and transport boundaries."""

from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]


def test_sync_overlay_limits_eligibility_and_credentials():
    overlay = yaml.safe_load(
        (ROOT / "compose.weekly-report-sync.prod.yaml").read_text()
    )
    services = overlay["services"]
    generator = services["weekly-report-worker"]
    assert generator["environment"] == {
        "WEEKLY_REPORT_DEPLOYMENT": "production",
        "WEEKLY_REPORT_SYNC_ENQUEUE": "true",
    }
    tunnel = services["weekly-report-sync-tunnel"]
    worker = services["weekly-report-sync"]
    assert "env_file" not in tunnel
    assert not any("DSN" in key for key in tunnel["environment"])
    assert "ports" not in tunnel and "ports" not in worker
    assert set(tunnel["networks"]) == {"weekly-report-sync-transport"}
    assert worker["networks"] == ["default", "weekly-report-sync-transport"]
    assert worker["env_file"] == ["./agents/.env"]
    assert tunnel["environment"]["WEEKLY_REPORT_TARGET_HOST"] == "${LIVE_PROD_DB_HOST:?required}"
    assert "ssh_key" not in str(worker["volumes"])
    for path in (ROOT / "compose.yaml", ROOT.parent / "compose.yaml"):
        if path.exists():
            development = yaml.safe_load(path.read_text())
            assert "weekly-report-sync" not in development["services"]
            assert "weekly-report-sync-tunnel" not in development["services"]


def test_tunnel_pins_host_key_and_has_no_command_or_agent_forwarding():
    script = (ROOT / "apps/weekly_report_tunnel/entrypoint.sh").read_text()
    assert "ssh -NT" in script
    assert "StrictHostKeyChecking=yes" in script
    assert "BatchMode=yes" in script
    assert "ExitOnForwardFailure=yes" in script
    assert "ServerAliveCountMax=3" in script
    assert '-- "$WEEKLY_REPORT_SSH_HOST"' in script
