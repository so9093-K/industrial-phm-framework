# Operations Web Read API v1 (initial slice)

This document records the initial loopback-only **Operations Web API v1 contract**. Since
ADR-0024 and #480 the packaged supervised Web is the default and only Operations UI.
Standalone Web preview reads the same saved evidence and does not supervise collection/analysis.
For current capability claims, use [status](../status.md); older cutover history below is not a live rollout gate.

## Endpoint and lifecycle

- `create_operations_web_read_server(workspace_root: Path, *, port=0)` returns an
  unstarted `ThreadingHTTPServer`. The caller owns `serve_forever()`, `shutdown()`
  and `server_close()`.
- The listener **always binds 127.0.0.1**. Read routes are `GET /api/v1/monitor`,
  `GET /api/v1/history/channels`, `GET /api/v1/history/trend`,
  `GET /api/v1/sources` and `GET /api/v1/session`.
  The packaged static paths `/web/`, `/web/app.js`, and `/web/styles.css` serve
  assets from the installed Python wheel. No arbitrary file path may be requested.
  Protected POST routes use the explicit `WEB_SOURCE_ACTION_ROUTES` allowlist
  in `src/industrial_phm/runtime/operations_web_actions.py`. The **current**
  supervised product supports bounded FILE/OPC UA registration, receipt/backfill,
  source lifecycle, evidence-linked analysis/Review and isolated demo actions;
  routes in `WEB_SUPERVISOR_ONLY_ACTION_ROUTES` require the supervisor command
  broker. Unknown POST routes return 405 and unsupported preview actions return
  403. This initial API document is not an exhaustive current route catalog.
  There is no arbitrary mutation command, Node runtime, dev server, repository
  file proxy or remote exposure.
- Host must be `127.0.0.1:<bound-port>` or `localhost:<bound-port>`. Optional
  `Origin` must be the same allowed HTTP origin, and `Sec-Fetch-Site: cross-site`
  is rejected. No wildcard CORS headers are emitted. Mutations require an exact
  browser same-origin request, bounded JSON, and a per-process CSRF token; this is
  **not** remote or multi-user authentication.
- Replies use `application/json`, `Cache-Control: no-store`, `nosniff`,
  anti-frame and restrictive content security headers; 403/404/405/503 errors carry
  **coded, path-free** JSON, not exception detail or repository paths. Invalid
  history query parameters return 400; an uninitialized/unreadable history returns 503.
- Caller must pass one existing workspace directory. Read composition uses only
  `INDUSTRIAL_PHM_OPERATIONS_WORKSPACE` and does not honor granular repository
  environment overrides. The API does not supervise collection/analysis.

## Explicit opt-in Web monitor preview

For an initialized, existing Operations workspace, start the **opt-in preview
as a separate foreground process**, for example:

```bash
uv run --locked --extra history python -m industrial_phm.runtime.operations_web_preview \
  artifacts/operations --port 8765
```

Open `http://127.0.0.1:8765/web/`. Press Ctrl+C to stop. The same process
serves both static frontend assets and API data, so **no CORS, Node, bundled npm
dependencies, or separate browser auth exception** is required. A nonstandard
port may be selected with `--port` (`0` selects an ephemeral local port);
a nonexistent workspace is rejected. It does not run or stop collection,
analysis, or the existing supervised Web child. `make up` and
`industrial-phm operations up` retain their current behavior. The preview is a
single-user local tool. The HTTP process mutex serializes its own requests, and
each authorized Web mutation additionally acquires the same nonblocking POSIX
`supervisor.lock` file lease held by the supported `make up` supervisor.
While the supervisor owns a workspace, the preview **remains readable** but all
Web POST routes return a path-free HTTP 409 conflict without mutation. Concurrent
Web preview processes also cannot mutate that workspace at the same time.
The lease is held until each accepted mutation completes, never used to
rewrite/truncate the supervisor PID marker, and then released. This is an
interlock only for cooperating Web previews and the normal supervisor; direct
file edits or an unsupported directly mutating process remain outside
this contract. The preview does not become the collector/analysis lifecycle owner.

The static HTML/CSS/JavaScript live inside `industrial_phm/apps/web/`, are
shipped with the **Python wheel**, and use the same-origin, explicit
`GET /api/v1/monitor`, `GET /api/v1/history/channels`, and
`GET /api/v1/history/trend` endpoints. Monitor summary and PHM detail use 3-second polling of saved facts; signal/history and
manual operating-change inspection remain explicit selections. This is not a live subscription.
The default Monitor reads stored Asset History for the selected asset independently of PHM bindings: the channel list once per
asset (re-read after 30 s) and a `anchor=latest` trend only when the selection changes, the asset's live history commit
or source-less recorded end changes, or 30 s pass. Each history read loads a full snapshot, so it is not part of the 3-second
poll. A failed read clears the stored values instead of keeping an earlier reading. The HTML uses native form
labels, semantic controls, keyboard focus and responsive layout. Dynamic
IDs, evidence and source fields are assigned via `textContent`, never
`innerHTML`; browser content security policy only allows self-hosted
scripts/styles/connections, denies framing and form actions.

The first screen provides **per-asset observed data-flow context**, up to
six selected stored signals with bounded, **unconnected time-bucket dots**
(no interpolated gaps), per-source last stored values and quality/conflict
flags, persisted phase-unbalance numeric evidence and persisted review
requests. All counts and timestamps come from current API responses.
There are **no fallback demo numbers, prognostic predictions, fault
alarms or local browser-only review mutations**. When the history store
is not initialized, the Web preview displays a distinct read failure
rather than inventing zero-valued measurements.

The Web-only Operations product cutover (#480) is complete. Synthetic first-run and
bounded OPC UA / FILE / Review journeys have landed, but whole-workflow parity,
locale switching, accessibility, and the recorded full fault-replay matrix remain
outside the current pilot support boundary.
This historical initial-slice section is not a current feature-completeness claim.

## Supervised Web preview pilot (read-only, opt-in)

The **default** `make up`, `operations up`, and `operations start` now
launch the packaged supervised Web Operations UI. For local engineering acceptance only,
an initialized workspace can opt into the existing Web static client under the
same collection/analysis/UI supervisor:

```bash
industrial-phm operations init /var/lib/industrial-phm/plant-a
industrial-phm operations start /var/lib/industrial-phm/plant-a --ui web-preview
```

The printed `operations_url` ends with `/web/`. The Web preview becomes the
supervised UI **process** (loopback, readiness, stop order, log target), but the
normal supervisor owns the lifetime `supervisor.lock` and all Web POST
mutations **continue to return 409 `workspace_writer_busy`**. This is a
strictly **read-only pilot**, not a usable replacement for registration or
review editing. The supervised Web command broker remains the writer
through the current supervised Web. Never bypass this boundary by disabling the lock
or using an environment variable as write authorization.

The supervisor-owned mutation command bridge is tracked in
[Issue #465](https://github.com/so9093-K/industrial-phm-framework/issues/465);
only a subsequent reviewed and tested implementation may enable supervised Web
writes. The pilot does not independently start a collector, provide user auth,
or authorize shared/remote access.

## Explicit supervised Web command pilot (opt-in)

A separate `web-controlled` UI choice is available **only** from the existing
Operations supervisor:

```bash
industrial-phm operations start /var/lib/industrial-phm/plant-a --ui web-controlled
```

The supervisor keeps the lifetime `supervisor.lock` and starts a bounded
local Unix command server in a private ephemeral directory (0700; socket
0600). It issues a fresh unpredictable per-generation token only to its
launched Web child, and checks the caller's Linux peer PID/UID against
that child process. Browser requests still require exact same-origin
Host/Origin, Fetch-Site and CSRF evidence. Validated POSTs delegate to the
supervisor, which serializes the exact existing eight source-action routes
through the established `OperationsAppActions` facade. The Web HTTP
child does not independently acquire or bypass the workspace lifetime lease.

A standalone Web preview still runs with its original lease-based POST
authorization: while another supervisor owns the workspace, GET remains
available and POST returns `409 workspace_writer_busy`. Explicit supervised
`--ui web-preview` remains read-only. Default `make up`, `operations
up`, and unflagged `operations start` launch supervised Web.

The IPC reply body has a strict size/time bound and never returns raw
paths, stack traces or credentials. Within one supervisor generation, a
request ID can replay its stored response without re-executing the action,
but the bounded in-memory replay map is **not persistent across supervisor
crashes**. A lost command response is `command_outcome_unknown` and the
client does not automatically retry it. This is a **local single-user
Linux engineering pilot**, not an HA, remote, authenticated multi-user or
fully accepted production Web migration. Review actions, First-run and
full Operations screen parity remain separate acceptance work.

## First-run source inventory and workspace FILE registration

The opt-in Web preview now has a first-run/source panel. It uses durable source
registry state, source lifecycle and **accepted receipt** evidence. Its source list
does **not** expose configured FILE paths, OPC UA endpoint URLs, credentials or
raw connector errors.

- `GET /api/v1/sources` returns `schema_version: 1`, UTC assessed time,
  `sources.items` (max 100) and `sources.total/truncated`, and bounded
  `read_error_scopes`. Each row includes source/asset/point/channel IDs, source
  family, lifecycle, `receipt_confirmed` and the last accepted observed/received
  timestamps. `registered` or `active` is **not** real-time connection status.
  A missing receipt is not displayed as accepted data.
- `GET /api/v1/session` returns a **per-preview-process unpredictable CSRF
  token** for same-origin UI requests. The token must be sent as
  `X-CSRF-Token` on registration; it is never included in source inventory.
  The local preview remains a **single-user loopback** capability; it is not
  multi-user authentication or a general-purpose remote API.
- `POST /api/v1/sources/file` registers **one prepared CSV already located
  inside the active workspace** using the existing
  `OperationsAppActions.register_source` facade. The browser requires a
  same-origin `Origin`, `Sec-Fetch-Site: same-origin`, an exact session
  CSRF token, JSON content type, and `Content-Length` 1–4096 bytes.
  There is no CORS exception, credential-bearing remote write path, path
  proxy or browser-based file upload. Unknown JSON keys, nested/absolute/
  escaping paths, symlink escapes, duplicate channels and more than 12
  channels are rejected. CSV must be no larger than 20 MiB, be UTF-8,
  and pass the existing prepared-FILE parser/registration validation.
  A duplicate source ID returns 409; malformed input 400; denied writes
  403. Error JSON carries **stable codes only**, never the filesystem
  path or source bytes.
- A successful registration returns HTTP **201** with
  `registration_state: registered`, `receipt_confirmed: false` and
  explicit `validated-registration-only-not-collected` meaning.
  This neither activates a source, requests collection, creates an
  accepted receipt, backfills DuckLake, nor runs PHM analysis.
  Operators must use the existing Operations runtime and collector to
  obtain actual data; then refresh this preview to see accepted receipts
  and stored signal history.

Remote OPC UA browse/configuration, credential/certificate handling, FILE uploads,
an isolated first-run synthetic sample and protected human-review writes remain
**out of scope**. Local anonymous OPC UA browse and one-shot diagnostics are
specified separately below; neither operation constitutes a live collector.
Source lifecycle and OPC UA collection desired-state requests are described below;
those requests do not start a collector or prove actual receipt.
The supervised Web product now owns the supported onboarding flow
until the staged Web transition acceptance gates pass.

## Explicit FILE validated receipt (opt-in preview only)

`POST /api/v1/sources/file/receive` accepts only `{"source_id":"..."}` and
uses the same bounded same-origin, CSRF-protected JSON request as the other
write routes. It accepts only an ACTIVE, registered FILE snapshot CSV that is
currently located inside the workspace, unchanged as an absolute canonical
path, and at most 20 MiB. A missing, escaped, replaced-by-symlink, oversized,
inactive, or non-FILE source is rejected. This is a single explicit iteration
through the existing `OperationsAppActions.run_diagnostic(kind=CYCLE)` and
`JsonSourceRuntimeRepository`, **not** a scheduler, historical DuckLake
backfill, FILE upload, live stream, analysis run, or sensor-transport proof.

A successful one-shot cycle returns `cycle_state: succeeded`,
`accepted_new_receipt: true`, and persisted accepted/observed UTC timestamps.
A source/runtime failure returns `cycle_state: failed` with a bounded
`failure_scope` and no new accepted receipt; any older receipt remains
historical evidence. Raw filesystem paths and error details are not exposed.
`GET /api/v1/sources` projects the persisted receipt separately from source
registration and the collection desired state. The browser never turns an
accepted FILE receipt into an assertion that DuckLake signal history is stored.
The current JSON source/runtime repositories are single-writer only; legacy
and new Web source actions must not write the same workspace concurrently.

## Web collection evidence (read-only; opt-in preview)

`GET /api/v1/sources` includes **independent** evidence for each OPC UA source:

- `collection_desired_state`: saved intent only; never interpreted as collector started.
- `collection_service_state`, `collection_service_heartbeat_at`, and
  `collection_service_heartbeat_fresh`: last durable process-level collection
  telemetry. A `running` row with heartbeat older than 20 seconds is stale,
  not a current live service. The heartbeat is **not per-source** and cannot
  establish that any particular source is connected.
- `opcua_session_last_state` and `opcua_session_state_changed_at`: the
  worker's last stored session transition (which may be historical).
  `recent_connected_evidence` can only be true when the process heartbeat
  is recent, its state is `running`, and a `CONNECTED` session transition
  belongs to the current service start generation. It is evidence at the
  assessment time, **not** a guaranteed live network socket.
- `last_live_received_at`, `last_live_receive_age_seconds`,
  `last_live_receive_fresh`: callback receipt facts persisted from the
  continuous worker, with a 30-second freshness reference. Absence or stale
  time never proves the source is unhealthy; clocks in the future are treated
  as unverified. This is separate from `receipt_confirmed`, which reflects
  the separately persisted one-shot source diagnostic receipt.
- `last_live_history_committed_at`, `last_live_history_snapshot_id`,
  `last_live_history_batch_event_count`: the last durable OPC UA spool
  history batch per source. It may lag a newer receive; an old committed
  batch is not confirmation of current source activity. FILE backfill is
  deliberately not inferred from this field: use history channels/trend
  reads to confirm actual stored FILE events.
- `live_telemetry_read_error` and `live_evidence_error_scopes` preserve corrupt
  or inaccessible telemetry as an **unknown read**, not "never received".
  `read_error_scopes` remains limited to source/control repositories: a broken
  optional telemetry or history store must not hide otherwise readable source
  registrations. Empty live facts do not establish health or connectivity.

The Monitor polls the saved transport facts; Sources/System retain manual inspection.
These reads do not supervise collectors, start subscriptions or assign fleet-wide health status.
The existing source lifecycle, backend telemetry and accepted history semantics
are unchanged.

## Explicit FILE DuckLake history backfill (opt-in preview only)

`POST /api/v1/sources/file/backfill` accepts only `{"source_id":"..."}` under
the same exact Host/Origin/Sec-Fetch-Site, CSRF, JSON body, and single-process
mutation lock as registration/receipt. Only an ACTIVE registered FILE snapshot
CSV within the workspace is eligible; its canonical path, symlink boundary,
file type, size and max 12 channels are checked again. A source must have a
**separately persisted accepted receipt** and an explicit timestamp column.
This synchronous route keeps a **1 MiB** input limit because one bounded supervisor
command waits at most 5 s; measured FILE history writes take about 7–8 s per MiB of
three-channel CSV. Times must be timezone-aware; invalid input does not imply that any
history was accepted.

`POST /api/v1/sources/file/backfill/start` (supervised Web only) applies the same checks
with a **20 MiB** limit, then writes the same batch on a supervisor-owned background
thread and returns `state: "running"` immediately. At most one such job runs per workspace;
another source's request is refused with `source_control_conflict` while one is running.
The status of the last job per FILE source is ephemeral runtime state in
`runtime/web-file-history.json`, exposed as the additive `file_history_job` object on
`GET /api/v1/sources` FILE items (`state` running/succeeded/failed/interrupted,
`started_at`, `finished_at`, `event_count`, `history_snapshot_id`, `recovered_segment_count`, bounded `failure`
code). It is not history evidence: the committed DuckLake batch is. A supervisor restart
marks a running job `interrupted`; restarting the job recovers or completes the
content-addressed batch without duplicating it. Supervisor shutdown waits for an
in-flight history write before releasing the workspace lease, and refuses new jobs once closing starts.
Client status reads are matched by source and started_at. Lost status and interrupted jobs mean
unconfirmed storage, not a failed commit. Same-source retries verify current bytes and configuration
through upload preflight; a receipt without a content digest is revalidated.

The command delegates to the existing `backfill_registered_file_source` and
`DuckLakeAssetHistory`. It returns actual `event_count`,
`segment_count`, `recovered_segment_count`, and
`history_snapshot_id` with meaning
`persisted-file-history-not-live-collection-or-analysis`. Repeating the
unchanged CSV recovers its existing content-addressed batch rather than
duplicating events. A changed CSV can produce new history with a new batch
identity; a prior FILE receipt does not prove that it covered the same bytes.
Check `GET /api/v1/history/channels` and `/trend` to verify the stored
measurement evidence. The response contains no CSV path or raw exceptions.
This is historical import, **not** a collector, an analysis run, or a claim
about machine condition. Failed/partial imports are not treated as success;
the next explicit import may recover already committed segments.
The JSON source/runtime state and DuckLake catalog have distinct writer
constraints; different Web preview and supervisor writers must not mutate the workspace concurrently.

## Local anonymous OPC UA first-run diagnostics (opt-in preview only)

The first OPC UA Web setup slice **only accepts literal `127.0.0.1` endpoints**
such as `opc.tcp://127.0.0.1:4840/`. URL credentials, remote DNS, IPv6 aliases,
queries, and fragments are rejected before any outbound network connection.
This is intentionally local-first; it is **not** a safe/complete remote asset
connector, certificate negotiation, authentication, credential storage, or
unbounded discovery UI.

- `POST /api/v1/sources/opcua/browse` with `{"endpoint_url":"..."}` runs
  the existing anonymous bounded Objects browse (2-second client timeout;
  connector maximum of 256 visited nodes), returning up to 24 safe candidate
  variable names and NodeIds. Browse connectivity is **not accepted source
  receipt**, registration, or continuous session readiness.
- `POST /api/v1/sources/opcua` with exactly `source_id`, `name`,
  `asset_id`, `measurement_point_id`, `endpoint_url`, and `node_mappings`
  (1–12 explicit `{"channel_id","node_id"}` entries) delegates to the existing
  `OperationsAppActions.register_source` and `OpcUaSourceConfig` validation.
  A `201` response means persisted mapping only. It never connects or records
  observations. There is no arbitrary browse start node or remote address.
- After explicitly activating the source, `POST /api/v1/sources/opcua/diagnose`
  with only `source_id` performs one existing `OperationsDiagnosticKind.CYCLE`
  snapshot read. The Web boundary rechecks the source's local URL, type, mapping
  bound, and ACTIVE lifecycle on every request. A successful cycle persists
  existing connection-attempt and accepted receipt evidence with exact UTC
  timestamps; an unsuccessful cycle reports a narrow failure scope and
  `accepted_new_receipt:false`. Older receipts remain historical evidence
  and must never be represented as the result of a failed attempt.

All three POSTs share exact Host/Origin/Sec-Fetch-Site, CSRF, bounded JSON,
and single-process mutation serialization. Responses contain no original URL,
credentials, raw connector exceptions, data values, live health classification,
or implicit DuckLake history writes. OPC UA desired-state `running` still
requires a separately running collector; a successful one-shot diagnostic
does **not** prove continuous subscription or collection supervision.

## Web source control requests (opt-in preview only)

The source inventory adds `continuous_collection_supported`,
`collection_desired_state`, `collection_request_generation`, and
`collection_requested_at`. These expose **persisted requested control state**,
not collection service readiness or accepted measurements. FILE sources have
`continuous_collection_supported: false`; current continuous collection only
supports OPC UA sources.

- `POST /api/v1/sources/lifecycle` with `{"source_id":"...","target_state":"active"}`
  or `"paused"` transitions via the existing `OperationsAppActions.transition_source`
  facade. Only legal lifecycle transitions are accepted; 409 means rejected
  transition. `active` is administrative permission, **not a live connection**.
- `POST /api/v1/sources/collection` with `target_state: "running"` or
  `"stopped"` requests the existing durable collection-control desired state.
  `running` requires an OPC UA source whose lifecycle is `active`. The
  collector service must already be running separately. A successful
  `200` records the request, **not** that data has been accepted or that
  a session is connected.
- Both actions require the same exact Host/Origin/Sec-Fetch-Site + per-process
  CSRF token and bounded JSON body as FILE registration. Missing sources
  return 404; forbidden transitions and unsupported source types return
  409; unknown target values/malformed input 400; unauthorized requests 403.
  Raw exception messages and source credentials never leave the server.

A successful control response does **not** alter `receipt_confirmed`. Operators
must verify accepted receipt and current stored history independently before
claiming working monitoring. No diagnostic connector cycle is launched by these
routes. The supervised Web is the operator product; research notebooks are separate.

## GET /api/v1/monitor response

The response is a **versioned projection** of one
`load_operations_app_snapshot()` read, not a second persistence owner.
The explicit `schema_version: 1`, `assessed_at` (UTC), and
`meaning: observations-and-review-evidence-not-asset-health` apply to the
whole response.

| JSON field | Contract |
| --- | --- |
| `assets` | Sorted asset identity, **data-flow status** (not asset condition), latest observed data/analysis times and pending review count |
| `attention` | Factual typed destinations/status/IDs and occurrence time; no raw system error detail |
| `phase_unbalance_analyses` | **Persisted phase-unbalance only**: run/asset/source/point/evidence/capability/algorithm IDs, observed range, completion time, source quality issue codes, historical snapshot ID or finalized-window input reference |
| `phase_unbalance_analyses[*].quantities` | Voltage/current **unbalance percent** with sample counts, source-specific exclusions, median/p95/max, channel IDs and selection, nullable unavailable values |
| `skipped_analysis_attempts` | SKIPPED reason, window/asset/source/point IDs and observed range. **No fabricated result number or `analysis_run_id`** |
| `review_requests` | Persisted human review-request finding identity, source `analysis_run_id`, evidence references and workflow status; not maintenance execution |
| `system_error_scopes` | Repository areas that failed to read; sorted scope identifiers only, **no exception strings or local filesystem paths** |

All timestamps use UTC ISO-8601 with `Z`; missing times/numeric results are JSON `null`.
The Korean Web displays these instants in KST (fixed UTC+09:00) through one shared formatter and
sends KST date-time inputs with an explicit `+09:00` offset. Display never rewrites a stored instant,
and original measurement, receipt, history commit, analysis completion and read times keep distinct labels.
Each collection has `items`, `total`, `truncated` and up to **100 entries**;
analyses/skips are newest first. `total` describes the snapshot's loaded
population (which is already bounded for phase results), **not a universal
database-wide count**. Results are **not** an auto-refresh/live subscription.
A caller must explicitly request another snapshot.

The monitor response itself does **not** embed the full time series; it offers
asset and evidence identities to select a bounded follow-up history query.
FILE vibration capability details, source credentials, source paths,
arbitrary history paging, and mutation APIs remain excluded. The existing
supervised Web product reads the existing runtime composition.

## GET /api/v1/history/channels

Request: `?asset_id=<URL-encoded asset identity>`. The response contains
`schema_version`, `assessed_at`, `asset_id`, explicit stored-history
`meaning`, and a `channels` collection with up to 100 channel IDs and
`total`/`truncated`. A stored channel is **not** evidence of a connected
OPC UA session or of current data receipt. If Asset History is not initialized
or cannot be read, return 503, **not a misleading successful zero count**.

## GET /api/v1/history/trend

Query: `asset_id=<id>&channel_id=<id>&channel_id=<id>&range=1h&buckets=60`.
IDs are URL-encoded. Allow **1 to 6 distinct channel_id parameters**, each
identifier up to 128 characters, and no extra query keys/duplicate scalar keys.
Choose one of `15m`, `1h` (default), `24h`, `7d`; `buckets`
is 1–120 (default 60). The server also limits URL size and parsed field count.
Input contract violation is HTTP 400 without raw error text.

The response includes `assessed_at`, selected asset/channel IDs,
range/UTC `start_at`/`end_at`, `snapshot_id`, `bucket_seconds`,
`buckets` and `latest_stored`. Source/point/channel/interpretation identity
is never collapsed, aligned across unlike units, or converted into an
asset-health/fault score.

- `buckets` contains **only buckets with actual stored observations**. A
  missing bucket is a gap, not `0`. Each row contains the exact
  `channel_id`, `source_id`, `source_type`, `measurement_point_id`,
  `interpretation_id` (digest), allowlisted `semantics` (observed property,
  scope, unit or `null`), start/end and first/last event times, and
  `observation_count`, `usable_count`, `null_count`,
  `non_good_count`, `conflict_count`, min/max/mean for usable
  observations. The mean is **observation-weighted** and not a live reading.
  The response refuses overly dense histories rather than returning an
  incomplete graph silently (up to 1,000 grouped rows per request).
- `latest_stored` contains at most 100 per-(channel/source/point)
  historically latest records **independently queried** from stored history.
  These are not necessarily from the trend's `snapshot_id` under concurrent
  ingestion. Each row carries original event time/basis, source type,
  ingestion mode, provenance evidence ID, numeric value (nullable), source
  quality, conflict marker and `usable_for_display`. A non-good quality or
  conflicting value is **not** safely displayable. FILE protocol quality
  remains `unknown` even when a numeric value exists.
- The last stored value can be older than the selected trend period or even
  bear a future timestamp; never silently relabel it as a current/safe
  equipment condition. The API does not infer received-at timestamps
  from stored event time, translate physical units, or invent connectivity.
- Unknown/missing history and storage failures return 503; no local
  source file or raw semantic metadata is included in the JSON response.
  Actual input semantics are whitelisted, not sent as arbitrary history JSON.

The aggregated read is the repository's established
`query_operations_multi_signal_measurement_aggregation` and
`query_operations_latest_measurements`, **not a second analysis engine**.

## Safety and acceptance

- No client should interpret data-flow `running`/`waiting` or good source
  quality as asset health, a fault, an alarm, risk score, RUL or maintenance need.
- An unavailable repository is distinguishable from empty data through
  `system_error_scopes`. A skipped computation is **not** 0% unbalance.
- Frontend must render all server-supplied text as text, not trusted HTML.
- Native browser security, UI/static packaging, deployed process lifecycle,
  actual FILE/OPC UA data traces, and end-to-end human-review mutations are
  deferred to the next independently reviewed implementation stages.
- Tests use an initialized real workspace for the HTTP GET and a constructed
  exact phase-result fixture for numerical evidence. API contract tests,
  Ruff, mypy and CI must pass before the PR is merged.

## View navigation and recorded-history time basis

The packaged Web selects Monitor, Connect, Signals, Evidence, Review, Research and System
content by hash route. Titles and navigation follow the selected view; browser back/forward
and deep links use the same routes. Asset/channel/range selection is retained within the
page session. Connection guidance belongs to Connect; an empty Monitor exposes three start
choices only after both source and monitor reads establish a readable empty workspace.
A failed or partial read cannot establish emptiness.

`GET /api/v1/history/trend` accepts `anchor=now` (API default) or `anchor=latest`.
`now` uses the snapshot assessment time. `latest` ends one second after the greatest stored
observation timestamp for the selected signals; original event times are unchanged.
The response includes `time_anchor` independently of `assessed_at`. The UI defaults to
last recorded history so old recordings remain explorable without moving them into the present.
Existing channel/bucket/group limits and quality/interpretation separation apply to both anchors.

## Electrical operating-condition analysis

Monitor consumes `GET /api/v1/condition?asset_id=...&period=1h|6h|24h`.
An optional `source_id` and `point_id` select one context when an asset has several;
the response does not merge sources or measurement points. `end_at` selects the recorded
analysis end. `reference_start` and `reference_end` must be supplied together, with an explicit
timezone, before the target window and spanning at most 24 hours. Omitted reference bounds
select the preceding equal-length window. Invalid or cross-source selections return 400;
history read failures remain distinct from missing or unsupported measurements.

`operations_web_condition` owns bounded snapshot reads and semantic role resolution.
`application/electrical_condition` owns strict phase alignment, descriptive load/unbalance
changes and reference-pattern scoring. It reuses the phase unbalance definition and the
existing dataset-neutral Isolation Forest. Reference-only training/calibration, fixed random
seed, deterministic sampling of at most 2,048 fit observations, and separate target scoring
prevent target values from entering the comparison baseline. Each period is limited to
3,600 timestamps and 22,000 retrieved channel groups. Source labels are not model features.

The current-duration estimate uses only consecutive valid current observations whose gap
is at most 1.5 times the observed cadence and no more than 120 seconds. It does not fill
missing intervals or extend the final observation. Low-current unbalance is unavailable,
not zero. Insufficient/constant reference data cannot produce a pattern score or a healthy
verdict. Sensor quality of FILE recordings remains unconfirmed.

The result is a read-only exploratory analysis at an identified history snapshot. It creates
no AnalysisRun, review entry, model deployment or alarm. Existing persisted analysis/review
APIs retain their own writes. The primary screen shows quantities, comparison periods,
time-series and candidate timestamps; exact storage identifiers and calculation details are
secondary information.


## Asset Monitor PHM reads

`GET /api/v1/phm/monitor` is an additive bounded projection of PHM bindings, input progress,
last successful output, previous successful output, latest processed/refused input and review status. It returns at most
100 binding rows, total/limit/truncated, and a separate review-read error. It never loads full
step histories, waveform files or estimator payloads, and never fits or scores a model.
The previous successful output is an indexed position-bounded read from the same binding;
refused inputs are excluded and the browser labels nonconsecutive comparisons explicitly.
Selected anomaly scores and reconstruction-error deltas remain visible without opening details.

The detail view uses the selected record for its summary, model delta, original input and
bookmark. Subsequent polling retains a selected record; explicit latest-follow mode updates
the displayed record and bookmark together. Error and signal trends share a default contiguous
range around that selection, with an explicit full-history choice. Independent units are never
overlaid. Original phase signals use one same-unit group (A, V or Hz) at a time; unavailable
observations remain gaps. These are presentations of existing stored quantities, not new inference.
Transport evidence comes from the existing `/api/v1/monitor` and `/api/v1/sources` contracts;
the browser makes three overview requests per cycle. Missing inputs do not prove a stopped sensor.

`GET /api/v1/phm/result?binding_id=...&position=...` returns one exact saved step for a Monitor
handoff. An unavailable binding/position fails explicitly, never substitutes another asset or
latest result. Existing series, window and snapshot endpoints retain their contracts.
The static `/web/` page accepts URL query context for these bookmarks; query content is not
interpolated into the HTML. Model/source/asset/measurement-point identities remain distinct.

Polling runs only for visible active Monitor or PHM detail views. Overview failures clear
previous model values and automatically retry; independent transport/review read failures remain
visible. Manual condition fitting is excluded from overview refresh. These reads do not own
collection, inference, deployment approval or asset-health semantics.

`GET /api/v1/phm/trace?binding_id=...` returns at most 64 saved steps in ascending position
order, including skipped steps. It reads the existing binding/position index without loading
the full series. The browser renders saved input RMS features separately from model scores;
it never joins missing/refused positions or treats an ordinal gap as a transport outage.
The latest contiguous input segment is the default, with an explicit whole-range option.
Magnitude changes compare the latest two available saved features, with an explicit distinction
between consecutive and nonconsecutive positions. The earlier record is not a normal baseline.

`GET /api/v1/phm/window-input?binding_id=...&position=...` provides the same quality-aware
original window preview as `/phm/window`, including before scoring. The pending path requires
the exact source/asset/measurement-point and encoded window-end position. It never substitutes
another window and does not create analysis state. Original window/series/snapshot contracts
are unchanged. These selected-input reads run only when the selection or input position changes.

## CSV entry identity and isolated examples

Upload preflight adds registration_match (absent/matching/conflict/unchecked). A reusable registration
requires the same file SHA-256, name, asset, measurement point, ordered channels, timestamp layout and
semantic configuration. A conflict is blocked without changing the registered file. Registration itself
still refuses duplicate IDs; only the verified browser recovery flow reuses completed stages.

History trend accepts one optional source_id. Latest anchoring and returned groups use that source, so
an older imported file is not hidden by newer data for the same asset. Existing queries and response
fields retain their meaning. CSV handoff preserves asset, source, channel and range in URL context.

Synthetic first-run exploration uses the existing isolated demo lifecycle. The demo declares its
purpose through runtime/web-context.json; session adds workspace_kind and gives that workspace
read-only-synthetic-demo write scope. Its Web POSTs are forbidden even with a valid CSRF token.
Parent Operations workspaces retain their existing scope. Bundled synthetic CSV content is blocked
from ordinary Web registration/storage; browser-only previews remain available.
