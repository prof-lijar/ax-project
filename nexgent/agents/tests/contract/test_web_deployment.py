from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
IMAGE_DIGEST = "sha256:252cfb5b348809167f5519970ca3457711e723afc76179a662b1c720cbbc1dd3"


def test_all_compose_topologies_keep_searxng_private_and_health_gated() -> None:
    compose_files = [
        ROOT / "compose.yaml",
        ROOT.parent / "compose.yaml",
        ROOT / "infra/compose/docker-compose.yml",
    ]

    for path in compose_files:
        compose = yaml.safe_load(path.read_text(encoding="utf-8"))
        services = compose["services"]
        searxng = services["searxng"]
        agent_server = services["agent-server"]

        assert searxng["image"].endswith("@" + IMAGE_DIGEST)
        assert "ports" not in searxng
        assert searxng["user"] == "977:977"
        assert searxng["cap_drop"] == ["ALL"]
        assert searxng["healthcheck"]
        assert agent_server["environment"]["SEARXNG_BASE_URL"] == (
            "http://searxng:8080"
        )
        assert agent_server["depends_on"]["searxng"]["condition"] == (
            "service_healthy"
        )


def test_searxng_configuration_enables_json_and_only_no_key_engines() -> None:
    settings = yaml.safe_load(
        (ROOT / "infra/searxng/settings.yml").read_text(encoding="utf-8")
    )

    assert "json" in settings["search"]["formats"]
    assert settings["search"]["safe_search"] == 1
    assert settings["server"]["public_instance"] is False
    assert settings["use_default_settings"]["engines"]["keep_only"] == [
        "bing",
        "brave",
        "duckduckgo",
        "google",
    ]


def test_development_agent_server_accepts_concurrent_graph_runs() -> None:
    dockerfile = (ROOT / "apps/agent_server/Dockerfile.dev").read_text(
        encoding="utf-8"
    )

    assert '"--n-jobs-per-worker", "4"' in dockerfile


def test_weekly_report_stacks_include_private_bulk_runtime_and_scheduler() -> None:
    compose_paths = [
        ROOT / "compose.yaml",
        ROOT.parent / "compose.yaml",
        ROOT.parent / "compose.prod.yaml",
    ]
    for path in compose_paths:
        services = yaml.safe_load(path.read_text(encoding="utf-8"))["services"]

        assert "weekly-report-jobs-db" in services
        assert "weekly-report-worker" in services
        assert "weekly-report-bulk-api" in services
        assert "weekly-report-scheduler" in services
        assert "profiles" not in services["weekly-report-worker"]
        assert "ports" not in services["weekly-report-bulk-api"]
        assert services["weekly-report-bulk-api"]["depends_on"][
            "weekly-report-jobs-db"
        ]["condition"] == "service_healthy"

        scheduler = services["weekly-report-scheduler"]
        assert "ports" not in scheduler
        assert scheduler["depends_on"]["weekly-report-bulk-api"]["condition"] == (
            "service_healthy"
        )
        assert scheduler["environment"]["WEEKLY_REPORT_BULK_API_URL"] == (
            "http://weekly-report-bulk-api:8090"
        )
        assert not any(
            "DATABASE" in name or "MODEL" in name
            for name in scheduler["environment"]
        )
        if path == ROOT.parent / "compose.prod.yaml":
            assert "profiles" not in scheduler
        else:
            assert scheduler["profiles"] == ["scheduled"]


def test_weekly_report_scheduler_image_fixes_cron_to_seoul_time() -> None:
    scheduler_root = ROOT / "apps/weekly_report_scheduler"
    dockerfile = (scheduler_root / "Dockerfile").read_text(encoding="utf-8")
    crontab = (scheduler_root / "crontab").read_text(encoding="utf-8")

    assert "/usr/share/zoneinfo/Asia/Seoul" in dockerfile
    assert "TZ=Asia/Seoul" in dockerfile
    assert any(line.startswith("0 3 * * 1 ") for line in crontab.splitlines())
