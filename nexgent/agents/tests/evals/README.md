# Evaluation tests

Place behavioral datasets, trajectory regressions, safety checks, latency/cost
thresholds, and release-gate scenarios here.

`test_web_quality.py` is an opt-in live smoke evaluation for the private
SearXNG-backed research tools. Run it only with a reachable service:

```bash
AX_RUN_LIVE_WEB_EVALS=1 SEARXNG_BASE_URL=http://searxng:8080 \
  uv run pytest tests/evals/test_web_quality.py -s
```

It covers current, technical, multilingual, and domain-filtered discovery and
reports result diversity, duplicates, latency, and fetch success. It is skipped
in deterministic CI because no-key upstream engines can throttle or change.

`test_weekly_report_quality.py` is deterministic and always runs. It checks the
ward-risk prototype's danger-day grounding, Korean report structure,
personalization, fallback disclosure, and release-gate failure behavior.
