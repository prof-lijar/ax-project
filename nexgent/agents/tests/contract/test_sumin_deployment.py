"""Sumin must start with the default root Compose command and agents environment."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_root_compose_includes_sumin_without_extra_flags():
    root = yaml.safe_load((ROOT / "compose.yaml").read_text())
    include = next(
        entry
        for entry in root["include"]
        if entry["path"] == "./agents/compose.sumin.yaml"
    )
    assert root["name"] == "nexgent"
    assert (ROOT / include["env_file"]).resolve() == ROOT / "agents/.env"
    definition = ROOT / include["path"]
    services = yaml.safe_load(definition.read_text())["services"]
    assert set(services) == {"sumin-migrate", "sumin-events", "sumin-worker"}
    for service in services.values():
        assert not service.get("profiles")
        assert (
            definition.parent / service["build"]["context"]
        ).resolve() == ROOT / "agents"
        assert (
            definition.parent / service["env_file"]
        ).resolve() == ROOT / "agents/.env"
        assert service["network_mode"] == "host"
        assert not service.get("ports")
    for name in ("sumin-events", "sumin-worker"):
        assert (
            services[name]["depends_on"]["sumin-migrate"]["condition"]
            == "service_completed_successfully"
        )
