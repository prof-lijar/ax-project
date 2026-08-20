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
