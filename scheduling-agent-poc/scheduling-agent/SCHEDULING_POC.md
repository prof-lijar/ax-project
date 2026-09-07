# Scheduling Agent POC

This document records the implementation and verification state through
2026-08-28, with a clearly dated Scout systemd supervision update from
2026-08-31. It describes current code and observed tests, not intended future
features.

## 1. Objective

This POC validates two separate concerns:

1. A deterministic scheduling layer can register known recurring interval
   tasks and a one-time workflow at an exact date/time, then execute them
   automatically.
2. An ADK/LLM layer can interpret a natural-language request and return
   validated scheduling parameters.

The LLM does not perform scheduling and does not report scheduling success.
After structured extraction finishes, ordinary Python application code calls
the scheduling service and returns the service's actual result.

Both the recurring interval flow and the one-time exact-date flow have been
verified end to end. The one-time flow was confirmed by a real overnight
execution at
`2026-08-27 03:28 Asia/Seoul`. The in-memory scheduler process remained alive
in detached tmux after the SSH client disconnected, reached the requested
wall-clock time, executed the calculator workflow, and retained its artifacts
and SUCCESS history entry. This does not demonstrate persistence across a
process or server restart. Integration with the Nexgent AX Chat UI and backend
has not been implemented.

A new experiment adds an independent `calculator_worker_agent` that performs
WHAT work only after APScheduler fires. In addition to controlled automated
tests, a real `2026-08-27 10:40:00 KST` execution verified this complete
scheduled invocation path. This is not a parent-agent/sub-agent design.

## 2. Project Structure

```text
scheduling-agent-poc/
├── tasks.py
├── scheduler.py
└── scheduling-agent/                 # Current project root
    ├── agents-cli-manifest.yaml
    ├── app/
    │   ├── __init__.py
    │   ├── agent.py
    │   ├── scheduler_service.py
    │   ├── scout_schedule_models.py
    │   ├── scout_schedule_repository.py
    │   ├── scout_api_client.py
    │   ├── scout_schedule_service.py
    │   ├── worker_agent.py
    │   ├── fast_api_app.py
    │   └── app_utils/
    ├── tests/
    │   ├── unit/test_dummy.py
    │   ├── unit/test_scheduling_agent.py
    │   ├── integration/
    │   └── eval/
    ├── pyproject.toml
    ├── uv.lock
    ├── SCHEDULING_POC.md
    ├── generated/                       # Runtime; created by workflow
    │   ├── calculator.py
    │   ├── README.md
    │   └── worker_result.json           # Created after Worker Agent success
    └── logs/                            # Runtime; created by workflow
        └── history.log
```

Relevant files:

- `../tasks.py` contains the original Task A, B, and C functions. Each prints
  timestamped `START` and `END` messages around a three-second simulated task.
- `../scheduler.py` contains the original interactive scheduler experiments,
  including parallel jobs, a sequential queue, overlap behavior, and Ctrl+C
  handling.
- `app/scheduler_service.py` owns the current process-local
  `BackgroundScheduler`, defines the deterministic multi-step Task A/B/C
  interval workflows, defines the sequential calculator workflow, and exposes
  both interval and one-time scheduling functions.
- `app/agent.py` defines the one ADK Agent, the `ScheduleRequest` schema, and
  the plain Python application orchestration that consumes the structured
  result and calls the scheduling service.
- `app/worker_agent.py` defines the independent tool-free
  `calculator_worker_agent`, its validated `WorkerResult`, and its invocation
  boundary. It is not a sub-agent of `scheduling_agent`.
- `tests/unit/test_scheduling_agent.py` contains focused controlled scheduler
  and workflow tests. An automatic cleanup fixture verifies that no
  module-level scheduler jobs remain.
- `agents-cli-manifest.yaml`, `pyproject.toml`, and `uv.lock` record scaffold
  and dependency information.

The manifest specifies in-memory sessions. Separately, a standard local ADK
development server used `app/.adk/session.db` during earlier verification.
Those are distinct runtime configurations.

## 3. Phase 1 — Basic Scheduling Experiments

The original command-line POC used Task A, B, and C to make scheduling behavior
visible in terminal output.

- **Parallel execution:** A, B, and C can run concurrently as separate
  APScheduler jobs.
- **Sequential execution:** scheduler callbacks enqueue work and one daemon
  worker processes the FIFO queue one item at a time.
- **Overlap control:** `max_instances=1` prevents concurrent instances of the
  same long-running parallel job. When a task takes longer than its interval,
  later firings of that same job are skipped.
- **Queue backlog:** in sequential mode, `max_instances=1` applies to the short
  enqueue callback. Items can therefore accumulate faster than the single
  worker can process them.
- **Shutdown:** the Ctrl+C handler was verified. It calls scheduler shutdown
  with `wait=False`, but queue draining is not implemented. Running and queued
  work are not guaranteed to finish before process exit.

These experiments explain execution policy; they are not additional features
of the current ADK scheduling service. The current Agent path supports a
recurring interval in seconds and two specific one-time workflows: calculator
and Worker Agent. Cron scheduling is not implemented.

## 4. APScheduler

The ADK project resolves APScheduler 3.11.3 in `uv.lock`; `pyproject.toml`
requires `apscheduler>=3.11.3`.

`app/scheduler_service.py` creates a module-level `BackgroundScheduler` without
starting it at import time. FastAPI lifespan starts and stops that legacy
scheduler. `schedule_interval_task(task_name, seconds)`:

- accepts Task A, B, or C;
- requires an interval greater than zero;
- registers an APScheduler interval job;
- uses stable job IDs `task_A`, `task_B`, and `task_C`;
- uses `replace_existing=True`; and
- keeps `max_instances=1`.

No persistent job store is configured. Jobs exist only in the process that
owns this scheduler and are lost when that process exits or restarts.
Distinct jobs can remain active at the same time and run concurrently when
their schedules overlap. `max_instances=1` applies per job, so it prevents a
task from overlapping with itself without preventing Task A, B, and C from
running concurrently with one another. If a firing occurs while the previous
instance of the same scheduled job is still running, that firing is skipped
rather than queued.

`schedule_calculator_workflow(run_at, timezone_name)` uses a `DateTrigger` to
register one job with stable ID `calculator_workflow`. The request's date/time
is treated as an Asia/Seoul local wall-clock value and converted to a
timezone-aware KST trigger. The trigger fires once and is then removed. The
registered job executes the complete calculator A -> B -> C workflow, rather
than registering three independent jobs.

`schedule_worker_agent_workflow(run_at, timezone_name)` registers a separate
`DateTrigger` job with stable ID `worker_agent_workflow`,
`replace_existing=True`, and `max_instances=1`. Registration only stores the
scheduled callback. The independent Worker Agent is invoked later by
`run_worker_agent_workflow()` only after APScheduler fires the job.

## 5. Phase 2 — Single ADK Scheduling Agent

The project was scaffolded with Google Agents CLI 1.4.1 and resolves Google
ADK 2.7.1.

### Structured request

`ScheduleRequest` is a Pydantic model with:

```text
schedule_type: interval | date
task_name: A | B | C | null
seconds: positive integer | null
workflow_name: calculator | worker_agent | null
run_at: local date/time | null
timezone: Asia/Seoul | null
```

Cross-field validation requires `task_name` and `seconds` for interval
requests. Date requests require a supported workflow (`calculator` or
`worker_agent`), a local date/time, and `Asia/Seoul`; interval-only fields must
be null. `run_at` is normalized as a local wall-clock value, and the scheduling
service attaches the explicit Seoul timezone before registration.

### Single Agent

`app/agent.py` defines one ADK `Agent`, named `scheduling_agent`, which is also
the app's `root_agent`. It:

- uses `output_schema=ScheduleRequest`;
- writes structured output to `schedule_request`;
- has `tools=[]`;
- has no parent Agent and no sub-agents; and
- only interprets the user message.

It does not call APScheduler or claim that registration succeeded.

This single-Agent design replaced the previous custom parent
`SchedulingOrchestrator` plus extraction sub-agent structure. The current
`root_agent` has no parent/sub-agent relationship.

### Deterministic application orchestration

After the Agent run, the plain Python function `run_scheduling_request()` reads
the `schedule_request` state delta and passes it to
`schedule_extracted_request()`. Application code revalidates the value as a
`ScheduleRequest`, then `execute_schedule_request()` explicitly calls one of:

```python
schedule_interval_task(request.task_name, request.seconds)       # interval
schedule_calculator_workflow(request.run_at, request.timezone)    # one-time
schedule_worker_agent_workflow(request.run_at, request.timezone)  # one-time
```

The return value is the exact string returned by `scheduler_service`; it is not
generated by the LLM.

The current flow is:

```text
User natural-language request
  -> single tool-free ADK scheduling agent
  -> validated ScheduleRequest
  -> plain deterministic Python application orchestration
  -> interval task, calculator workflow, or Worker Agent registration
  -> APScheduler
  -> repeated interval execution or one exact-date callback
```

Calling the ADK Agent by itself only performs extraction. A caller must use the
application orchestration boundary to register a schedule.

### Deterministic scheduled task workflows

Each Task A/B/C function is one APScheduler job execution, even though the
function performs multiple internal steps:

- **Task A — item batch:** sequentially processes items `[1, 2, 3, 4]`. Each
  item is prepared, calculated/transformed, and converted into a result report.
  The verified order within one batch is:

  ```text
  1-A -> 1-B -> 1-C
  2-A -> 2-B -> 2-C
  3-A -> 3-B -> 3-C
  4-A -> 4-B -> 4-C
  ```

  The complete 12-step sequence is one scheduled batch execution; item batches
  do not create separate scheduler jobs.
- **Task B — customer aggregation:** loads local customer records, filters
  active customers, aggregates values by region, and produces a deterministic
  summary.
- **Task C — report processing:** loads local report records, calculates
  variance, classifies each result, and generates deterministic report output.

All data and processing are local and deterministic. No external API or
database is used.

### One-time sequential calculator workflow

One `DateTrigger` job runs this dependency chain:

```text
Task A: deterministically write generated/calculator.py
  -> Task B: import and execute it; verify add, subtract, multiply, divide,
             and division-by-zero ValueError behavior
  -> Task C: write generated/README.md using Task B's verification result
  -> append logs/history.log
```

Task C runs only after Tasks A and B succeed. If a step fails, later dependent
steps do not run, and the final history entry records the failed task, concise
error, completion time, and `FAILURE` status. History is append-only; generated
calculator and README artifacts may be replaced by a later run. All paths are
resolved from the project root rather than the shell's current directory.

### Real overnight DateTrigger verification — 2026-08-27

The following natural-language request was submitted:

```text
Run the calculator workflow on August 27, 2026 at 3:28 AM Korea time.
```

The Agent extracted a validated date request, and deterministic application
code registered job `calculator_workflow` with an APScheduler `DateTrigger`.
Before leaving, its `next_run_time` was verified as
`2026-08-27 03:28:00+09:00` (`Asia/Seoul`). The scheduler process remained
alive in a detached tmux session on the nextor-ai-02 server while the SSH
client and local laptop were disconnected.

The verified operational flow was:

```text
Natural-language request
  -> single tool-free ADK scheduling_agent
  -> validated date ScheduleRequest
  -> deterministic Python dispatch
  -> APScheduler DateTrigger
  -> process remains alive in detached tmux
  -> scheduled time reached
  -> Task A: generate calculator.py
  -> Task B: execute and validate calculator.py
  -> Task C: generate README.md
  -> append logs/history.log
```

The following morning, `logs/history.log` showed:

```text
Scheduled workflow: calculator
Scheduled time: 2026-08-27 03:28:00 Asia/Seoul
Actual start: 2026-08-27 03:28:00 KST
Task A: SUCCESS - generated/calculator.py created
Task B: SUCCESS - 5/5 calculator checks passed
Task C: SUCCESS - generated/README.md created
Duration: 0.00 seconds
Final status: SUCCESS
Completed: 2026-08-27 03:28:00 KST
```

The retained artifacts verified that `generated/calculator.py` implements
`add()`, `subtract()`, `multiply()`, and `divide()`, with division by zero
raising `ValueError`. `generated/README.md` documents those operations, basic
usage, division-by-zero behavior, and the actual Task B result, `5/5 calculator
checks passed`. The approximately 11-line history entry records the scheduled
time, actual start, A/B/C results, displayed duration, final status, and
completion time. The observed `0.00 seconds` duration means completion was
below the logger's two-decimal display precision.

This verifies automatic later execution while the owning server process stays
alive without an active SSH connection. tmux was only the mechanism used to
keep that POC process alive; it is not part of the Scheduling Agent architecture
and does not provide schedule persistence or restart recovery.

### Separate scheduled Worker Agent experiment

`calculator_worker_agent` is a second, independent ADK Agent. It has
`tools=[]`, is not present in `scheduling_agent.sub_agents`, and is never
called by `scheduling_agent`. Its responsibility is WHAT work to describe;
the Scheduling Agent only extracts WHEN the work should run.

The Worker Agent returns a validated `WorkerResult` containing:

```text
implementation_description: non-empty string
required_operations: add, subtract, multiply, divide (each exactly once)
test_plan: at least five test descriptions
readme_summary: non-empty string
```

When the `worker_agent_workflow` DateTrigger fires, deterministic Python calls
`run_worker_agent()`, validates the structured result, and writes
`generated/worker_result.json`. The JSON contains the Agent name, scheduled
time, actual invocation time, structured result, final status, and completion
time. The Agent itself has no filesystem access and does not write the file.
The callback also appends a clearly identified Worker Agent entry to the
existing `logs/history.log`; failures are recorded without claiming artifact
success.

Controlled automated tests verified that registration does not invoke the
Worker Agent, a near-future DateTrigger later enters the invocation boundary,
the validated result is written by deterministic Python, prior history is
preserved, and invocation failure produces a FAILURE history entry without an
artifact. The scheduled test used a controlled Agent result. Separately, a
bounded real-model smoke check verified that `calculator_worker_agent` returns
a valid `WorkerResult`, and a bounded Scheduling Agent extraction check parsed
the exact 10:10 request without registering a job.

The real combined path was then verified successfully:

```text
Natural-language request
  -> scheduling_agent
  -> validated ScheduleRequest
  -> deterministic schedule_worker_agent_workflow()
  -> APScheduler DateTrigger
  -> wait until 2026-08-27 10:40:00 KST
  -> run_worker_agent_workflow()
  -> run_worker_agent()
  -> independent calculator_worker_agent invoked
  -> LLM inference
  -> validated WorkerResult
  -> deterministic generated/worker_result.json write
  -> append logs/history.log
  -> SUCCESS
```

Before execution, job `worker_agent_workflow` had
`next_run_time=2026-08-27 10:40:00+09:00`. Registration caused no Worker Agent
invocation, artifact write, or history change. At 10:40:00 KST, retained tmux
output showed `WORKER AGENT STARTED`, followed by completion, artifact writing,
and history appending.

`generated/worker_result.json` records actual invocation at
`2026-08-27T10:40:00.000848+09:00`, completion at
`2026-08-27T10:40:14.307374+09:00`, and `final_status: SUCCESS`. Its validated
result contains an implementation description, exactly add/subtract/multiply/
divide, five test-plan items including division-by-zero `ValueError`, and a
README summary. The appended history entry independently records successful
Agent invocation, structured-output validation, artifact creation, final
status, and completion at `10:40:14 KST`.

This extends the earlier 03:28 proof rather than replacing it: 03:28 verified
scheduled deterministic Python A -> B -> C execution, while 10:40 verified
that a scheduled callback can later invoke an independent ADK Worker Agent and
deterministically consume its validated structured output.

### Weekly Report relevance

The batch-style verification is closer to a future Weekly Report use case: one
scheduler job can trigger one batch, and that batch can process multiple items
through multiple internal steps. It does **not** mean Weekly Reporter is
connected, and it does not add cron scheduling.

### Multiple simultaneous interval jobs

The following requests were verified through `run_scheduling_request()` rather
than by bypassing the Agent and registering jobs directly:

```text
"Schedule Task A every 10 seconds."
"Schedule Task B every 15 seconds."
"Schedule Task C every 20 seconds."
```

All three jobs remained registered and active together. Each repeated at its
own extracted interval, all internal workflows completed successfully, and
Task A and Task B were observed running concurrently during an overlap. No job
overlapped with another instance of itself because `max_instances=1`; a firing
that occurred while its previous instance was running was skipped rather than
queued. The manual scheduler process was then stopped cleanly with Ctrl+C.

## 6. Internal LLM Integration

Both ADK Agents use the same configured model pattern:

```text
Google ADK
  -> LiteLLM
  -> configured OpenAI-compatible API base
  -> model openai/gemma-4-31b
  -> structured JSON-schema response
```

`app/agent.py` reads:

```text
OPENAI_API_BASE=<configured internal endpoint>
OPENAI_API_KEY=<redacted>
```

Bounded runtime tests verified that this path returned `task_name="A"` and
`seconds=5` for an interval request and registered the calculator workflow for
exactly `2026-08-27 03:28:00 KST` for the one-time request. The new Worker
Agent separately returned a valid structured calculator plan. A bounded
Scheduling Agent check parsed the Worker Agent request as local
`2026-08-27 10:10:00`, `Asia/Seoul`, while a recorder prevented job
registration. No shared model-server configuration was changed.

Native LLM tool/function calling is not part of this flow.

## 7. Tests Performed and Results

| Test | Result | Notes |
|------|--------|------|
| Task A/B/C direct execution | Pass | All three deterministic multi-step workflows completed with timestamped start/end output. |
| Interval registration | Pass | The service registers stable recurring interval jobs. |
| Task A batch order | Pass | Verified `1-A -> 1-B -> 1-C` through `4-A -> 4-B -> 4-C`; the full sequence was one job execution. |
| Task A batch recurrence | Pass | At a two-second interval, complete ~1.44-second batches repeated without skipped executions or interleaving. |
| Task A shorter interval | Pass | At a one-second interval, intervening firings were skipped while the current ~1.44-second batch ran. |
| Separate per-task intervals through Agent | Pass | Natural-language requests registered A=10 seconds, B=15 seconds, and C=20 seconds through `run_scheduling_request()`. |
| Simultaneously active jobs | Pass | Stable jobs `task_A`, `task_B`, and `task_C` remained registered together. |
| Cross-task concurrency | Pass | Different task workflows were observed executing concurrently when schedules overlapped. |
| Same-task overlap prevention | Pass | With `max_instances=1`, no task overlapped with itself; a firing that occurred while the same job was still running was skipped rather than queued. |
| Sequential queue execution | Pass, Phase 1 experiment | One worker processed queued tasks one at a time. |
| Overlap behavior | Pass | `max_instances=1` suppressed overlapping instances of the same long-running job. |
| Queue backlog behavior | Pass, Phase 1 experiment | Work accumulated when enqueue cadence exceeded worker throughput. |
| Ctrl+C handler | Pass | Handler verified; it does not drain queued work or guarantee running-job completion. |
| Scheduling Agent root configuration | Pass | Root is one `scheduling_agent`, with no sub-agents and `tools=[]`; the independent Worker Agent is not attached to it. |
| Structured extraction | Pass | `Schedule Task A every 5 seconds.` produced A and 5. |
| Schema validation | Pass | Task is restricted to A/B/C; zero and negative intervals are rejected. |
| Deterministic service invocation | Pass | Application code called `schedule_interval_task("A", 5)`. |
| Service-owned confirmation | Pass | Application return value was `Task A scheduled every 5 seconds.` from the service. |
| Repeated end-to-end execution | Pass | A, B, and C repeatedly executed at their independently configured intervals; observed bounded counts were A=4, B=2, C=2. |
| Manual shutdown | Pass | The long-running manual process remains active until Ctrl+C and then stops the scheduler cleanly. |
| One-time natural-language registration | Pass | The configured model path plus deterministic orchestration registered one `calculator_workflow` job for `2026-08-27 03:28:00 KST`. The bounded verification process then removed the test job. |
| DateTrigger and timezone | Pass | Controlled tests verified one automatic firing and preserved the Asia/Seoul-aware run date. |
| Calculator Task A | Pass | Created a working calculator with add, subtract, multiply, divide, and explicit division-by-zero handling. |
| Calculator Task B | Pass | Imported and executed the generated program; all 5/5 checks passed. |
| Calculator Task C | Pass | Created a README describing the actual calculator and Task B result. |
| Sequential dependencies | Pass | Verified A -> B -> C; a Task B failure prevented C and produced a FAILURE history entry. |
| Append-only execution history | Pass | Controlled runs appended concise SUCCESS/FAILURE evidence without overwriting earlier entries. |
| Independent Worker Agent | Pass | `calculator_worker_agent` is tool-free, has no sub-agents, and is not a sub-agent of `scheduling_agent`. |
| Worker registration boundary | Pass | Registering `worker_agent_workflow` did not invoke the Worker Agent. |
| Scheduled Worker callback | Pass, controlled | A near-future real DateTrigger later entered the callback and invoked a controlled Worker Agent boundary exactly once. |
| Worker structured validation | Pass | Valid `WorkerResult` data was accepted; invalid operation data was rejected. |
| Worker artifact and history | Pass, controlled | Deterministic Python wrote the required JSON fields, preserved prior history, and appended SUCCESS evidence. |
| Worker failure history | Pass, controlled | Invocation failure appended FAILURE and `Artifact: NOT WRITTEN`; no artifact was fabricated. |
| Real Worker Agent structured output | Pass, bounded smoke check | The configured model returned a validated four-operation plan with five required tests. No schedule or artifact was created. |
| Worker scheduling extraction | Pass, bounded smoke check | The exact 10:10 request dispatched local `2026-08-27 10:10:00`, `Asia/Seoul`, to a recorder; no job was registered. |
| Unit suite | Pass | Focused file: 26 passed. Complete unit suite: 27 passed on 2026-08-27. No module-level scheduler jobs remained after tests. |
| Native tool/function calling | Bypassed | Not registered or used. |
| Real overnight DateTrigger execution | Pass | Registered for 2026-08-27 03:28 KST, remained active after SSH disconnect via detached tmux, automatically executed A -> B -> C, generated both artifacts, and recorded SUCCESS in `history.log`. |
| Real 10:40 scheduled Worker execution | Pass | Registration produced `worker_agent_workflow` for `2026-08-27 10:40:00+09:00` without invoking the Worker. At trigger time the independent Agent ran, returned a validated `WorkerResult`, wrote `worker_result.json`, and appended SUCCESS history. |
| Cron through the Agent/service | Not implemented | Current structured request supports interval seconds and the two specific date workflows only. |
| AX Chat integration | Not implemented | Nexgent does not route AX Chat requests to this POC. |
| Weekly Reporter integration | Not implemented | Batch behavior was simulated locally; Weekly Reporter is not connected. |

## 8. Previous Native Tool-Calling Approach — Bypassed

An earlier version exposed the scheduling function as an LLM tool. Automatic
tool selection failed before the function was invoked because the serving
configuration rejected automatic tool choice and reported that
auto-tool-choice and tool-call-parser support were required.

That failed approach is historical context, not the current architecture. The
working implementation avoids it by using tool-free structured extraction and
an explicit Python call to the scheduler service. No shared vLLM flags,
model-specific tool parser, or native ADK function calling is required.

## 9. Current Status

**POC objective achieved:** The Scheduling Agent has verified three scheduling
paths: multiple independent recurring interval jobs; one-time deterministic
calculator workflow execution; and one-time natural-language scheduling that
later invokes an independent ADK Worker Agent at the requested Asia/Seoul
wall-clock time. Both real one-time proofs required their owning in-memory
scheduler process to remain alive; neither demonstrates restart persistence.

### VERIFIED / WORKING

- The single `scheduling_agent` extracts a validated `ScheduleRequest`.
- Task names are limited to A/B/C and seconds must be a positive integer.
- Plain Python application code deterministically invokes the scheduling
  service.
- The scheduler service returns the confirmation shown to the caller.
- APScheduler registers and repeatedly executes interval jobs with
  `max_instances=1`.
- Task A executes its complete four-item, 12-step batch sequentially and
  repeats the whole batch at the configured interval.
- Task A firings were skipped when its interval was shorter than its complete
  batch duration; completed batches did not overlap or interleave.
- Natural-language requests registered Task A, B, and C together at 10-, 15-,
  and 20-second intervals.
- All three complex workflows completed, different tasks ran concurrently,
  and no task overlapped with itself. With `max_instances=1`, a firing that
  occurred while the same job was still running was skipped rather than queued.
- The unit suite passes without requiring changes for the task-body updates.
- One-time natural-language extraction and deterministic registration produced
  a `DateTrigger` for exactly `2026-08-27 03:28:00 KST`.
- A controlled DateTrigger test fired once automatically; the complete
  calculator workflow separately executed A -> B -> C successfully.
- Task A generated a working calculator, Task B executed and passed all five
  required checks, and Task C generated matching documentation.
- SUCCESS and FAILURE workflow runs appended concise entries without
  overwriting prior entries in controlled temporary-root tests.
- The real overnight `DateTrigger` remained active in detached tmux after the
  SSH client disconnected and automatically started at exactly
  `2026-08-27 03:28:00 KST`.
- The real execution completed A -> B -> C successfully, generated
  `calculator.py` and `README.md`, and appended a SUCCESS entry to the
  project-root `logs/history.log` with the observed duration `0.00 seconds`.
- The independent `calculator_worker_agent` returned a validated structured
  result in a bounded real-model smoke check. It is not a sub-agent and has no
  filesystem tools.
- Controlled tests verified `APScheduler -> scheduled callback -> Worker Agent
  invocation boundary`, JSON persistence by deterministic Python, append-only
  history, and failure reporting.
- Registration and execution are separate: registering the Worker DateTrigger
  did not invoke the Worker Agent.
- The real Worker job remained dormant after registration, then APScheduler
  fired it at exactly `2026-08-27 10:40:00 KST` and independently invoked
  `calculator_worker_agent`.
- The Agent returned a validated `WorkerResult`; deterministic Python wrote
  `generated/worker_result.json` and appended a SUCCESS entry to
  `logs/history.log`, completing at `10:40:14 KST`.

### BYPASSED

- Native LLM tool/function calling.
- Automatic tool choice and server-side tool parsing.

### NOT IMPLEMENTED / REMAINING LIMITATIONS

- Legacy calculator and Worker Agent APScheduler jobs remain process-local and
  in memory.
- The API process must remain alive for both legacy and Scout jobs to fire;
  persistent Scout jobs reload after a process restart, while legacy jobs do
  not.
- No persistent job store or restart recovery for legacy calculator/Worker
  schedules. The Scout scheduling API has both.
- No cron scheduling.
- No job listing, cancellation, or update API.
- No multi-process scheduler coordination or duplicate-scheduler prevention.
- No AX Chat UI/backend integration.
- No Weekly Reporter integration.
- No production scheduler lifecycle management.
- No scheduling-specific ADK evaluation datasets.

## 10. Next Steps

The recurring interval path, real calculator DateTrigger execution, and real
scheduled Worker Agent invocation have been verified. Possible follow-up work
includes:

1. AX Chat integration through an application service boundary, if required.
2. Weekly Reporter integration after defining its service contract, if
   required.
3. Cron scheduling if required.
4. Persistent job storage, restart recovery, job management, and
   single-scheduler ownership.

Further integration steps, such as AX Chat, Weekly Reporter, cron scheduling,
and persistence, remain pending and should be implemented based on confirmed
requirements.

## 11. Architecture Summary

```text
CURRENT STANDALONE POC

User natural-language interval or date request
  |
  v
[VERIFIED / WORKING] Single ADK scheduling_agent
                     tools=[]
                     output_schema=ScheduleRequest
  |
  v
[VERIFIED / WORKING] Validated ScheduleRequest
                     interval: {task_name, seconds}
                     date: {calculator | worker_agent, local run_at, Asia/Seoul}
  |
  v
[VERIFIED / WORKING] Plain Python run_scheduling_request()
                     revalidate structured result
                     deterministic service invocation
  |
  v
[VERIFIED / WORKING] Deterministic dispatch
  |
  +--> schedule_interval_task(task_name, seconds)
  |      -> APScheduler interval job
  |         stable ID, replace_existing=True, max_instances=1
  |         -> recurring Task A / B / C workflow
  |
  +--> schedule_calculator_workflow(run_at, "Asia/Seoul")
  |      -> one APScheduler DateTrigger job
  |         -> owning process remains alive until scheduled time
  |         -> Task A: create generated/calculator.py
  |         -> Task B: execute and verify 5/5 behaviors
  |         -> Task C: create generated/README.md
  |         -> append logs/history.log
  |
  +--> schedule_worker_agent_workflow(run_at, "Asia/Seoul")
         -> one APScheduler DateTrigger job (worker_agent_workflow)
         -> wait until scheduled time; no Agent invocation at registration
         -> deterministic run_worker_agent_workflow() callback
         -> independent calculator_worker_agent (tools=[])
         -> validated WorkerResult
         -> deterministic generated/worker_result.json write
         -> append logs/history.log

[VERIFIED] All three jobs active and repeating simultaneously
[VERIFIED] Different tasks may execute concurrently
[VERIFIED] max_instances=1 prevents same-job overlap
           a firing while that job is running is skipped, not queued
[VERIFIED] Exact one-time job registered for 2026-08-27 03:28 KST
[VERIFIED] Controlled DateTrigger fired once automatically
[VERIFIED] Full calculator A -> B -> C workflow and history behavior
[VERIFIED] Real overnight DateTrigger fired at 03:28:00 KST
           process stayed alive in detached tmux after SSH disconnect
           artifacts generated and SUCCESS appended to history.log
[VERIFIED / CONTROLLED] Worker registration did not invoke the Worker Agent
[VERIFIED / CONTROLLED] DateTrigger later entered the Worker invocation boundary
[VERIFIED] Real Worker Agent returned a validated WorkerResult in a bounded run
[VERIFIED] Full natural-language -> wait until 10:40 -> Worker Agent path
           registered without Worker invocation or file/history side effects
           fired at 10:40:00 KST and invoked calculator_worker_agent
           validated WorkerResult, wrote worker_result.json, appended SUCCESS

[NOT A SUB-AGENT RELATIONSHIP]
scheduling_agent finishes after deterministic registration
APScheduler callback independently invokes calculator_worker_agent later


[BYPASSED] Native tools -> automatic tool choice -> server tool parser


[NOT IMPLEMENTED] Nexgent AX Chat -> Scheduling Agent POC
[NOT IMPLEMENTED] Weekly Reporter -> Scheduling Agent POC
[NOT IMPLEMENTED] Natural-language cron scheduling
[NOT IMPLEMENTED] Persistent legacy calculator/Worker scheduled jobs
[IMPLEMENTED] Persistent Scout jobs and conservative restart recovery
[IMPLEMENTED] Single-worker systemd supervision for the Scout Scheduling API
```

The POC has verified recurring interval scheduling with multiple independent
jobs, the calculator's one-time deterministic wall-clock execution, and a
one-time natural-language schedule that later invoked an independent ADK
Worker Agent. The two Agents are independent execution stages, not a
parent/sub-agent graph: `scheduling_agent` finishes registration, and
APScheduler's deterministic callback invokes `calculator_worker_agent` later.
Native tool calling remains bypassed. tmux can keep the owning process alive
but is not Agent architecture or persistence. AX Chat, Weekly Reporter, cron
scheduling, legacy-schedule restart recovery, and production durability for
the legacy calculator/Worker path remain unimplemented.

## 12. Phase 2 — Persistent Scout Scheduling API (Current)

Date: 2026-08-28

### Architecture

```text
Client
  -> POST /v1/scout/schedules
  -> ScoutScheduleService
       -> SQLite Scout schedule repository
       -> persistent APScheduler DateTrigger (job ID = schedule UUID)
  -> at requested Asia/Seoul local time
       -> atomic pending -> running claim
       -> ScoutApiClient
       -> POST /v1/scout/runs on the existing Scout service
       -> copy Scout result/timing metadata unchanged
       -> SQLite succeeded/failed audit history
```

This path is application-owned and contains no ADK agent delegation. It never
invokes the calculator workflow or `calculator_worker_agent`. Scout remains the
only research implementation and remains authoritative for `run_id`, status,
`started_at`, `completed_at`, `duration_seconds`, `source_count`, sources, and
artifact references. The scheduler does not derive replacement Scout timing
from HTTP dispatch duration.

`app/fast_api_app.py` owns lifecycle for both schedulers. The legacy in-memory
scheduler and persistent Scout scheduling service start during FastAPI lifespan
startup and stop during teardown. Importing `app.scheduler_service` no longer
starts threads. Teardown checks whether each scheduler was actually started,
and a Scout startup failure still shuts down any legacy scheduler started by
that lifespan. Legacy job definitions and calculator/Worker semantics are
unchanged.

### API contract

`POST /v1/scout/schedules` accepts:

```json
{
  "topic": "고독사 예방 AI IoT 서비스 최근 동향",
  "keywords": ["고독사 예방", "AI 돌봄", "IoT 모니터링"],
  "run_at": "2026-08-29T09:00:00",
  "timezone": "Asia/Seoul"
}
```

`run_at` is a timezone-naive ISO local wall-clock value. Offsets, `Z`, malformed
values, past times, and timezones other than `Asia/Seoul` are rejected. Topic
and keyword bounds match the Scout request contract. Every accepted schedule
receives a UUID. An identical still-pending payload is rejected as an accidental
duplicate; independent payloads coexist.

`GET /v1/scout/schedules` returns `{ "schedules": [...] }`, including terminal
audit records. `DELETE /v1/scout/schedules/{schedule_id}` changes only a pending
record to `cancelled` and removes its pending APScheduler job. Running,
succeeded, failed, cancelled, or missed records cannot be cancelled and are
never deleted.

### Persistence, recovery, and concurrency

The default database is `var/scout_schedules.sqlite3`. The repository table and
APScheduler SQLAlchemy job store coexist in that SQLite file. Persisted states
are `pending`, `running`, `succeeded`, `failed`, `cancelled`, and `missed`.

Startup reconciles database records and jobs:

- stale `running` records become safely `failed` with
  `stale_running_recovery`; they are not retried because a previous Scout HTTP
  request may have completed externally;
- future pending records are registered exactly once by UUID;
- pending records no more than 300 seconds late execute under the configured
  misfire grace;
- older pending records become `missed` without invoking Scout; and
- orphan or terminal persistent jobs are removed.

The default APScheduler executor has one worker, enforcing a global Scout
callback concurrency limit of one while safely queueing simultaneous due jobs.
The limit is configurable, but this phase assumes exactly one scheduling API
process owns the database and scheduler. Multi-process leader election is not
implemented.

### Scout callback and failures

The synchronous Scout request timeout defaults to 180 seconds. A successful
Scout response, including its report and authoritative terminal metadata, is
validated and stored. A Scout HTTP 502 containing safe failed-run metadata is
stored unchanged and the schedule becomes `failed`. Preflight errors,
unreachable Scout, timeouts, malformed responses, and unexpected callback
failures store only bounded scheduling error codes/messages; they do not
fabricate a Scout run ID or Scout timing.

### Configuration

```text
SCOUT_API_BASE_URL=http://127.0.0.1:8091
SCOUT_API_TIMEOUT_SECONDS=180
SCOUT_SCHEDULE_DB_PATH=var/scout_schedules.sqlite3
SCOUT_SCHEDULER_CONCURRENCY=1
SCOUT_SCHEDULER_MISFIRE_GRACE_SECONDS=300
SCHEDULING_API_HOST=0.0.0.0
SCHEDULING_API_PORT=8092
```

Run and verify locally:

```bash
uv run uvicorn app.fast_api_app:app --host 0.0.0.0 --port 8092
uv lock --check
uv run --extra lint ruff format --check app/fast_api_app.py app/scout_*.py \
  tests/unit/test_scout_*.py tests/integration/test_scout_schedule_api.py
uv run --extra lint ruff check app/fast_api_app.py app/scout_*.py \
  tests/unit/test_scout_*.py tests/integration/test_scout_schedule_api.py
uv run pytest tests/unit tests/integration
```

Verification performed on 2026-08-28:

- the focused Scout scheduling suite passed `43` tests;
- the unchanged legacy scheduler regression file passed `26` tests;
- focused Ruff format and lint checks passed for every Phase 2 Python file;
- `uv lock --check` resolved the locked `291` packages without changes; and
- an alternate-port live server verification returned HTTP 200 for the A2A
  agent card, 57 `/run_sse` events, and a completed five-chunk A2A stream.

The combined `tests/unit tests/integration` run reached `70` passing tests, but
its three existing `test_server_e2e.py` cases could not bind their hard-coded
port 8000 because another process already owned that port. No existing process
was stopped. The same unchanged server surfaces passed on temporary port 18092.
A bare repository-root `pytest` also collects the historical
`overnight_test.py`, whose import-time script assumes the legacy scheduler was
already started; that unrelated historical script remains unchanged.

### Recurring Scout schedules — 2026-08-31

The Scout Scheduling API now accepts `recurrence` values `once`, `daily`,
`weekly`, and `monthly`. Omitting the field preserves the original one-time
contract and its `DateTrigger`. Recurring rules use an APScheduler
`CronTrigger` with `Asia/Seoul` as the trigger timezone:

- Daily requires `schedule_time`.
- Weekly requires `schedule_time` and a lowercase English `day_of_week`.
- Monthly requires `schedule_time` and `day_of_month` from 1 through 31.

The repository performs an idempotent additive SQLite migration for recurrence
columns. Existing rows receive the database default `once`, keeping their
stored local and UTC trigger values. A recurring row stores its next local and
UTC occurrence in the existing `run_at_local` and `trigger_at_utc` columns.

After a recurring callback succeeds or fails, its state returns to `pending`
and the next occurrence advances. The existing `scout_run_json` field retains
the latest available Scout run, and safe error fields describe the latest
failed or missed occurrence; this small change does not introduce a separate
per-occurrence history table. Cancellation still uses the existing pending to
cancelled transition and preserves the latest result metadata.

On restart, a stale recurring callback is not retried. It records
`stale_running_recovery` and advances to the first future occurrence. A missed
recurring occurrence also advances instead of terminating the schedule.
Monthly cron rules skip months that do not contain the selected day. The same
single FastAPI process remains the only scheduler owner; deployment and systemd
configuration are unchanged.

Validation performed on 2026-08-31:

- focused recurrence model, repository, service, and API tests passed (`68`);
- focused Ruff formatting and lint checks passed; and
- all non-live backend unit/integration tests passed (`95`), excluding the
  existing live ADK/model and hard-coded-port server files; and
- the full frontend suite (`205` tests) and production build passed.

### Current limitations and follow-up

Systemd status update (2026-08-31):

- The single-worker unit in
  `deploy/systemd/nexgent-scout-scheduler.service` is installed, enabled, and
  functionally verified on the host as `nexgent-scout-scheduler.service`.
- Only one scheduler process owner is supported.
- There is no update/reschedule endpoint, retry policy, per-occurrence history
  table, or idempotency-key subsystem.
- Slack notification remains future work and is not connected to scheduled
  Scout completion.
- A live future-time call to the real Scout service is not part of the
  deterministic automated suite.
