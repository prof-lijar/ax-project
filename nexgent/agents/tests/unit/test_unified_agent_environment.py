"""Exercise file selection and SSH routing without databases or real SSH."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from apps.daily_risk_scheduler import run as daily
from apps.daily_risk_scheduler.notification import AGENT_ENV_FILE as DAILY_ENV
from apps.weekly_report_scheduler.notification import AGENT_ENV_FILE as WEEKLY_ENV

ROOT = Path(__file__).resolve().parents[2]
WRAPPERS = [
    "weekly-reporter/migrate.sh",
    "fix-oct5-previous-counts/run.sh",
    "fix-oct12-counts/run.sh",
    "migrate-guardian-template-ids/run.sh",
]


def executable(path, body):
    path.write_text(f"#!{sys.executable}\n" + body)
    path.chmod(0o700)


@pytest.mark.parametrize("wrapper", WRAPPERS)
@pytest.mark.parametrize("invalid_host", [None, "bad;host", "5432"])
def test_wrappers_use_unified_settings_and_configurable_remote_endpoint(
    tmp_path, wrapper, invalid_host
):
    workspace = tmp_path / "agents"
    source = ROOT / "playground" / wrapper
    script = workspace / "playground" / wrapper
    script.parent.mkdir(parents=True)
    shutil.copyfile(source, script)
    # Preflight may import this helper; no real migration or DB code is run.
    (script.parent / "migrate.py").write_text(
        "from types import SimpleNamespace\n"
        "def source_database_dsn():\n    return 'local-source'\n"
        "def parse_args(args):\n    return SimpleNamespace(target='live')\n"
    )
    # Nested files must never override or supply missing unified values.
    (script.parent / ".env").write_text("LIVE_PROD_DB_HOST=wrong.example\n")
    host = invalid_host or "production-db.example"
    (workspace / ".env").write_text(
        "LIVE_PROD_DB_USER=test-user\nLIVE_PROD_DB_PASSWORD=test-db-password\n"
        "LIVE_PROD_SSH_HOST=bastion.example\nLIVE_PROD_SSH_ID=test-ssh-user\n"
        "LIVE_PROD_SSH_PASSWORD=test-ssh-password\n"
        f"LIVE_PROD_DB_HOST={host}\nLIVE_PROD_DB_PORT=5439\n"
        "LIVE_PROD_TUNNEL_PORT=16543\n"
    )
    binary = tmp_path / "bin"
    binary.mkdir()
    python = binary / "python-wrapper"
    executable(
        python,
        """import json, os, sys
if sys.argv[1] == '-':
    code = sys.stdin.read()
    sys.argv = sys.argv[1:]
    exec(compile(code, '<preflight>', 'exec'))
else:
    with open(os.environ['MIGRATION_CAPTURE'], 'w') as output:
        json.dump(sys.argv[1:], output)
""",
    )
    executable(
        binary / "sshpass",
        """import json, os, sys
assert os.read(3, 1024).decode().strip() == 'test-ssh-password'
with open(os.environ['SSH_CAPTURE'], 'w') as output:
    json.dump(sys.argv[1:], output)
""",
    )
    executable(binary / "ssh", "")
    result = subprocess.run(
        ["bash", str(script), "--write"],
        cwd=tmp_path,
        env={
            "PATH": f"{binary}:/usr/bin:/bin",
            "PYTHON_BIN": str(python),
            "SSH_CAPTURE": str(tmp_path / "ssh.json"),
            "MIGRATION_CAPTURE": str(tmp_path / "migration.json"),
        },
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert "test-ssh-password" not in result.stdout + result.stderr
    assert "test-db-password" not in result.stdout + result.stderr
    if invalid_host:
        assert result.returncode != 0
        assert not (tmp_path / "ssh.json").exists()
        assert not (tmp_path / "migration.json").exists()
    else:
        assert result.returncode == 0, result.stderr
        arguments = json.loads((tmp_path / "ssh.json").read_text())
        assert arguments[arguments.index("-L") + 1] == (
            "127.0.0.1:16543:production-db.example:5439"
        )
        assert arguments[-1] == "test-ssh-user@bastion.example"
        assert json.loads((tmp_path / "migration.json").read_text())[-1] == "--write"


def test_notification_clients_share_the_root_file():
    assert DAILY_ENV == WEEKLY_ENV == ROOT / ".env"


def test_daily_dsn_reads_root_override_and_ignores_nested_file(tmp_path, monkeypatch):
    (tmp_path / "playground").mkdir()
    (tmp_path / "playground/.env").write_text("SOURCE_DATABASE_DSN=obsolete\n")
    (tmp_path / ".env").write_text(
        "SOURCE_DATABASE_DSN=unified\nANSIMK_DATABASE_DSN=source\n"
    )
    monkeypatch.setattr(daily, "ROOT", tmp_path)
    for key in (
        "SOURCE_DATABASE_DSN",
        "WEEKLY_REPORT_STORAGE_DATABASE_DSN",
        "ANSIMK_DATABASE_DSN",
    ):
        monkeypatch.delenv(key, raising=False)
    assert daily.database_dsn() == "unified"
    monkeypatch.setenv("SOURCE_DATABASE_DSN", "explicit-process-override")
    assert daily.database_dsn() == "explicit-process-override"
