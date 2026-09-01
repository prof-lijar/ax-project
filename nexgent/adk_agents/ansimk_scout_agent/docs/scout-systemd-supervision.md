# Scout systemd supervision

Date: 2026-08-31

## Deployment status

The AnsimK Scout API and standalone Scout Scheduling API are installed,
enabled, active, and functionally verified under systemd:

| Unit | Responsibility | Binding | Verified state |
| --- | --- | --- | --- |
| `nexgent-scout.service` | AnsimK Scout API | `0.0.0.0:8091` | enabled, active |
| `nexgent-scout-scheduler.service` | Standalone Scout Scheduling API | `0.0.0.0:8092` | enabled, active |

Both units are enabled through `multi-user.target`, run as
`nextor-ai-02:nextor-ai-02`, and invoke their project virtualenv's `uvicorn`
binary directly. Each uses exactly one Uvicorn worker and no reload process.

The Scout health checks returned:

```text
GET http://127.0.0.1:8091/health/live   -> {"status":"ok"}
GET http://127.0.0.1:8091/health/ready  -> {"status":"ready"}
```

The Scheduling API successfully returned persisted schedules from
`GET http://127.0.0.1:8092/v1/scout/schedules`.

## Units and process ownership

The version-controlled unit templates are:

```text
nexgent/adk_agents/ansimk_scout_agent/deploy/systemd/nexgent-scout.service
scheduling-agent-poc/scheduling-agent/deploy/systemd/nexgent-scout-scheduler.service
```

They are installed at:

```text
/etc/systemd/system/nexgent-scout.service
/etc/systemd/system/nexgent-scout-scheduler.service
```

Scout starts with:

```text
/home/nextor-ai-02/nextor_ai/ax-project/nexgent/adk_agents/ansimk_scout_agent/.venv/bin/uvicorn app.fast_api_app:app --host 0.0.0.0 --port 8091 --workers 1
```

Scheduling starts with:

```text
/home/nextor-ai-02/nextor_ai/ax-project/scheduling-agent-poc/scheduling-agent/.venv/bin/uvicorn app.fast_api_app:app --host 0.0.0.0 --port 8092 --workers 1
```

The Scheduling unit declares `Wants=` and `After=` on
`nexgent-scout.service`. Its `ExecStartPre` calls
`http://127.0.0.1:8091/health/ready`, so Scheduling starts only after Scout is
HTTP-ready. This provides ordering and a readiness gate without using a hard
`Requires=` dependency.

Scheduling must remain single-worker. The process owns APScheduler execution,
its persistent SQLAlchemy job store, and schedule reconciliation; multiple API
workers would create multiple scheduler owners. Scout is also installed with
one worker, matching the validated topology.

## Runtime configuration and secrets

Secrets are not stored in Git or in the unit files. Runtime configuration is
held in these host-only files:

```text
/etc/nexgent/internal-openai.env
/etc/nexgent/nexgent-scout.env
/etc/nexgent/nexgent-scout-scheduler.env
```

The directory and files have these verified permissions:

| Path | Owner | Mode |
| --- | --- | ---: |
| `/etc/nexgent` | `root:nextor-ai-02` | `0750` |
| `/etc/nexgent/internal-openai.env` | `root:nextor-ai-02` | `0640` |
| `/etc/nexgent/nexgent-scout.env` | `root:nextor-ai-02` | `0640` |
| `/etc/nexgent/nexgent-scout-scheduler.env` | `root:nextor-ai-02` | `0640` |

`internal-openai.env` contains the final application variable names
`OPENAI_API_BASE` and `OPENAI_API_KEY`. The existing configuration's
`OPENAI_BASE_URL` value was mapped to `OPENAI_API_BASE` for these services.
`nexgent-scout.env` supplies `SCOUT_MODEL` and the Scout output root.
`nexgent-scout-scheduler.env` supplies the Scheduling API's non-secret runtime
settings, including the frontend origin, local Scout URL, 180-second callback
timeout, persistent database path, concurrency one, and 300-second misfire
grace period.

Never copy the actual `OPENAI_API_KEY`, model endpoint, or other secret values
into source-controlled files, commands, logs, or documentation.

## Persistence and backup

Scheduling and Scout persistence remain separate:

```text
Scheduling SQLite:
/home/nextor-ai-02/nextor_ai/ax-project/scheduling-agent-poc/scheduling-agent/var/scout_schedules.sqlite3

Scout run artifacts:
/home/nextor-ai-02/nextor_ai/ax-project/nexgent/adk_agents/ansimk_scout_agent/var/runs/<run_id>/report.md
/home/nextor-ai-02/nextor_ai/ax-project/nexgent/adk_agents/ansimk_scout_agent/var/runs/<run_id>/execution.jsonl
```

Existing `succeeded`, `cancelled`, and `failed` schedule records were
preserved and successfully reconstructed after systemd startup. No database
reset or migration was performed.

A consistent pre-install SQLite backup exists under:

```text
scheduling-agent-poc/scheduling-agent/var/backups/
```

The backup is runtime data and is not a source-controlled artifact.

## Functional verification

### Run Now

A Run Now request was executed successfully from the Nexgent Scout frontend
while Scout was systemd-managed:

- completed: `2026-08-31 10:05:09 KST`;
- authoritative duration: `01:07`;
- sources: `3`; and
- `report.md` and `execution.jsonl` were generated.

### Scheduled Scout

The frontend created a new one-time schedule for
`2026-08-31 10:08:00 KST`. It progressed through the Scheduling API and
completed successfully:

- status: `Succeeded`;
- completed: `2026-08-31 10:08:56 KST`;
- authoritative duration: `00:57`;
- sources: `2`; and
- `report.md` and `execution.jsonl` were generated.

This verified the complete supervised path:

```text
Nexgent frontend
  -> systemd Scheduling API :8092
  -> persistent one-time dispatch
  -> systemd Scout API :8091
  -> Scout research execution
  -> persisted result
  -> frontend reconstruction and display
```

## Operations

Inspect service state with:

```bash
systemctl status nexgent-scout.service --no-pager
systemctl status nexgent-scout-scheduler.service --no-pager
```

Inspect current-boot logs with:

```bash
journalctl -u nexgent-scout.service -b -n 100 --no-pager
journalctl -u nexgent-scout-scheduler.service -b -n 100 --no-pager
```

After checking that no Scout or scheduled run is active, an authorized
operator can restart the services with:

```bash
sudo systemctl restart nexgent-scout.service
sudo systemctl restart nexgent-scout-scheduler.service
```

Restarting either service during an active Scout or scheduled run can interrupt
that run. The Scheduler checks Scout readiness at startup, so start or restart
Scout before Scheduling when operating both units together.

Both units use `Restart=on-failure`, a 15-second restart delay, SIGTERM for
shutdown, and a 240-second stop timeout. Scheduling's FastAPI lifespan owns
APScheduler startup and shutdown. Exactly one Scheduling service process must
remain the scheduler owner.

No manual restart or failure-injection test was performed after the final
functional verification. The real Run Now and scheduled executions had already
confirmed systemd-managed operation, and unnecessary disruption to the shared
server was intentionally avoided.

## Scope and non-impact

The systemd installation added deployment/support files and host supervision;
it did not change Scout or Scheduling application logic. It also did not modify
the existing RAG service, frontend service or configuration, firewall rules,
or unrelated Nexgent and Weekly Reporter work. Existing persisted Scout
scheduling records were preserved.

Systemd supervision does not add recurring or cron schedules, schedule updates,
automatic retries, Slack notifications, or multi-process scheduler leader
election. Scout callback concurrency remains one and exactly one Scheduling
process owner is supported.

Systemd deployment completed and functionally verified on 2026-08-31.
