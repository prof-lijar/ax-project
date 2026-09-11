# Documentation map

- [Weekly Reporter Selected-Ward Tests](../../docs/08-implementation/weekly-reporter-selected-ward-tests.md): comma-separated ward selection, ZIP-only output, validation, and rollout.

- [Weekly Report Five-ZIP Retention](../../docs/08-implementation/weekly-report-five-zip-retention.md): automatic ZIP cleanup, preserved report data, manual command, and rollout checks.

- [Weekly Reporter UI ZIP-only tests](../../docs/08-implementation/weekly-reporter-ui-zip-only.md): per-job persistence control for browser test exports.

- [Weekly-report database recovery](weekly-report-database-recovery.md): verified artifact recovery without regeneration, including explicit insert timestamps, opt-in NOT NULL row skipping, and partial-write results.

- [Weekly-report bulk polling reliability](weekly-report-bulk-polling.md): serialized browser polling, request deadlines, failure backoff, and regression validation.

- [AX agents architecture](ax-agents-architecture.md): authoritative modular
  package, runtime, API, security, deployment, and verification design.
- [AX agents module guide](ax-agents-module-guide.md): responsibilities,
  boundaries, interfaces, and current status of each package.
- [Scalable agent platform structure](scalable-agent-platform-structure.md):
  implemented apps/workflows/packages layout, dependency rules, performance
  decisions, validation, and extension guidance.
- [LangGraph environment setup](langgraph-environment-setup.md): greenfield
  Python/uv setup, graph-entry import requirements, local Agent Server
  validation, trusted-LAN binding, and production follow-up guidance. Read the
  architecture document before extending this setup.
- [OpenAI-compatible LLM integration](llm-integration.md): vLLM environment
  configuration, chat graph usage, retry behavior, and secret handling.
- [Chat response streaming](chat-response-streaming.md): provider-token to
  LangGraph custom-event contract, cancel-on-disconnect behavior, validation,
  and deployment.
- [Chat attachments](chat-attachments.md): transient reference contract,
  secure file reader, document/image provider payloads, safe errors, and
  runtime limits.
- [RAG Chat Agent](rag-chat-agent.md): dedicated streamed RAG orchestration API,
  vector Top-5 grounding, deterministic no-context and source behavior,
  configuration, offline/live validation, and Phase 1 capability boundaries.
- [Reusable web research tools](web-research-tools.md): provider-neutral
  `web_search`/`web_fetch` contracts, private SearXNG deployment, reuse, source
  evidence, SSRF controls, and retrieval limits.
- [MCP development and integration](mcp-integrations.md): declarative remote
  server registry, environment-backed headers, discovery CLI, namespaced tool
  adapters, risk classification, and the configured read-only database MCP.
- [Ansimk weekly reporter](../workflows/weekly_report/README.md): private
  FastAPI/raw-PostgreSQL metadata source, deterministic current/prior metrics,
  deterministic section evaluations, and an LLM-authored one-paragraph
  `한주 총평` generated from report-facing weekly data rather than a
  Python-selected sentence formula. Validation enforces body-only warm 해요체,
  material-issue coverage, no digits, no `움직임`/`리모컨`, no English status
  values, no repeated findings/actions, no unsupported safety reassurance, no
  stable close that contradicts an attention signal, and whole-report sleep
  and dispatch exclusions. It also excludes `위험`, rushed or alarm-amplifying
  wording, and exclamation marks from `한주 총평`. Risk-management and
  separate-record data are omitted from the model payload and summary in all
  cases, while the deterministic detail section remains unchanged. The renderer
  recombines the paragraph with deterministic detail sections and guardian
  actions; bounded correction and disclosed fallback remain.
  The writer addresses an adult child living apart from a parent who lives
  alone, puts all observations before one practical final action, and rejects
  emotional-attitude directions such as `다정하게`.
  The summary prompt omits report `기본 정보` and overall score-band results,
  retaining only a summary-opening name plus the four lifestyle areas and
  approved actions. Its first sentence contains the core activity/lifestyle
  flow, and related findings are joined into two to four natural sentences.
  The fixed `[이름]님은` opening avoids an immediate second `은/는` topic
  particle by using forms such as `활동이`; correction and fallback enforce
  the same natural Korean grammar.
  Guardian cards use observation-style titles, and directional environment
  CAUTION or RISK states share the approved `ENV_CAUTION_01`–`04` mappings;
  summary closing actions remain grounded in deterministic section copy.
  Known subscriber names replace generic honorifics. Complete lifestyle-data
  reception absence produces only the approved two-sentence information and
  power-check summary, without an unsupported overall lifestyle assessment.
  Each result retains guardian-facing `markdown` and adds a strict
  `weekly-report-v5` `template_data` JSON object with stable keys and
  paired raw/display metric values for direct frontend rendering. The
  interactive compatibility graph remains non-writing; the durable bulk finalizer persists generated
  frontend JSON before completing its job.
  Bulk ZIP downloads include one `json/<ward_id>.json` template beside the
  existing per-ward Markdown paths. Activity detection and remote-control use
  now render as children of one `생활 활동` section with combined descriptions
  and one worst-status tag. Missing environment displays use `-` with
  temperature/humidity-specific copy, while missing count-based device metrics
  display `0` without replacing their null raw values. Detail sections use `태그` instead
  of `요약`; stable and empty guardian-action states output `GUI_GOOD_01`.
  Device detail uses covered days for normal reception and the remaining days
  in the selected week for power checks; the old power-pattern count is not
  rendered. The bulk finalizer populates the
  `ansimk.resources_ward_weekly_report` JSONB store through a dedicated,
  atomic upsert writer without changing the read-only source boundary. The bulk
  worker admits four jobs per process by default while enforcing one shared
  report/model concurrency ceiling across them. Compose can reuse the currently
  configured
  `ANSIMK_DATABASE_DSN` for local compatibility; production should set the
  dedicated writer DSN and least-privilege role explicitly.
- [Ansimk weekly reporter implementation specification](ansimk-weekly-reporter-implementation.md):
  implemented FastAPI source boundary, calculation rules, inclusive year-round
  indoor-environment recommended ranges, special cool-humid/cold-humid daily
  maximum counters, and exact environment copy,
  weekly-total activity and `기기 상태` presentation with transparent
  unmatched-row counts,
  actionable power-check copy only for zero-reception weeks without synthetic
  event counts or false missing-data claims,
  weekly-average risk-score presentation, personalized deterministic summary
  openings, qualitative sensor evidence, deterministic guardian action guides
  with internal conditions, descriptions, approved tags, and template IDs,
  connected sparse-data insights, non-urgent summary wording, deterministic
  device-power guardian guidance, fixed report-topic exclusions, LLM safety contract,
  100-ward bulk paging, in-flight cancellation, terminal queue-failure
  recovery, a bounded per-report model deadline, capacity targets,
  configuration, and verification gates.
- [Frontend weekly reporter workbench](../../docs/08-implementation/weekly-reporter-test-route.md):
  bulk-only `/agents/1` execution with durable 1–10,000 report job control,
  throughput monitoring, cancellation, verified export, an explicitly
  non-persistent schedule editor preview, and a fixed Monday 01:00
  `Asia/Seoul` cron service that idempotently submits the previous completed
  week through the private bulk API; the former Quick Preview and Chat
  execution paths are retired.
- [Outbound Slack messaging](slack-outbound-messaging.md): approved-channel
  configuration, reusable async delivery, safe failures, Slack app setup, and
  human-approved weekly-report verification.
- [Workspace README](../README.md#docker-development-server): license-free
  Docker development startup, parent Nexgent Compose integration, and
  trusted-LAN publishing.
- [Root production-server stack](../../docs/08-implementation/docker-production-stack.md):
  separate stable server for tested releases, with isolated ports and volumes,
  immutable web/backend containers, and the currently shared application-level
  Agent Server implementation.

- [Weekly-report production delivery](weekly-report-production-sync.md):
  transactional local outbox, production-only sync worker, private SSH transport,
  conservative conflict handling, retries, read-only readiness checks, deployment,
  and recovery.

- [Historical weekly-report migration](../playground/weekly-reporter/README.md):
  manual local-to-production preview and atomic ward/week upserts, updating all
  matches while preserving production creation timestamps.
