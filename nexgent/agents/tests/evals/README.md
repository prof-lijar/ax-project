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

`test_ax768_information_chat.py` is an opt-in live-model regression using only
synthetic/anonymized chat OCR. It checks sender/subject separation, two-person
contact ownership, guardian-add intent, noise/timestamp exclusion, empty results,
and preservation of valid Latin identifiers, business times and meaningful OCR
typos. It also checks that distinct labeled records survive chunking instead
of being collapsed as duplicate OCR. Run from `agents/` with the existing configured model:

```bash
AX768_LIVE_EXTRACTION_EVAL=1 uv run --env-file .env pytest tests/evals/test_ax768_information_chat.py -q
```

No spreadsheet, device or member-admin tools are available to this graph. The
eval is skipped by default and does not use real customer data.

## AX768 information-update intent

`AX768_LIVE_INFORMATION_EVAL=1 uv run --env-file .env pytest tests/evals/test_ax768_information_update_intent.py` exercises synthetic birthday, subscriber/guardian phone separation, and ambiguity against the configured local model. It invokes no Sheets/member tools and makes no business-record changes.
