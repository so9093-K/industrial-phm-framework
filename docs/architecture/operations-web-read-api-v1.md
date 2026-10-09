# Operations Web Read API v1 (initial slice)

This document owns the opt-in, loopback-only **Operations Web API v1 contract**. The installed
Operations product **still launches marimo**. The Web preview reads saved evidence and
permits only explicitly listed, protected source mutations. It does not replace the
production UI or supervise collection/analysis.

## Endpoint and lifecycle

- `create_operations_web_read_server(workspace_root: Path, *, port=0)` returns an
  unstarted `ThreadingHTTPServer`. The caller owns `serve_forever()`, `shutdown()`
  and `server_close()`.
- The listener **always binds 127.0.0.1**. Read routes are `GET /api/v1/monitor`,
  `GET /api/v1/history/channels`, `GET /api/v1/history/trend`,
  `GET /api/v1/sources` and `GET /api/v1/session`.
  **Only** `/web/`, `/web/app.js`, and `/web/styles.css` serve packaged static
  assets from the installed Python wheel. No arbitrary file path may be requested.
  Only `POST /api/v1/sources/file`, `POST /api/v1/sources/file/receive`,
  `POST /api/v1/sources/file/backfill`, `POST /api/v1/sources/lifecycle`,
  `POST /api/v1/sources/opcua/browse`, `POST /api/v1/sources/opcua`,
  `POST /api/v1/sources/opcua/diagnose`, and `POST /api/v1/sources/collection` are allowed
  under the protected write contract;
  other mutations return 405. There is no arbitrary mutation command, Node runtime,
  dev server, repository file proxy, or remote exposure.
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
analysis, or the existing supervised marimo child. Existing `make up` and
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
file edits or an unsupported manually launched marimo process remain outside
this contract. The preview does not become the collector/analysis lifecycle owner.

The static HTML/CSS/JavaScript live inside `industrial_phm/apps/web/`, are
shipped with the **Python wheel**, and use the same-origin, explicit
`GET /api/v1/monitor`, `GET /api/v1/history/channels`, and
`GET /api/v1/history/trend` endpoints. Browser requests are **manual
refresh/selection**, never a live subscription. The HTML uses native form
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

This is **not** a completed production web cutover: isolated first-run sample,
complete OPC UA setup/diagnostics, URL/deep-linked evidence screens,
locale switching, accessibility audit, independent supervision, and
full operational lifecycle/browser acceptance remain in [Issue #449](https://github.com/so9093-K/industrial-phm-framework/issues/449).

## Supervised Web preview pilot (read-only, opt-in)

The **default** `make up`, `operations up`, and `operations start` still
launch the packaged marimo Operations UI. For local engineering acceptance only,
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
review editing. The unchanged default marimo path remains the writer
through the old UI. Never bypass this boundary by disabling the lock or using
an environment variable as write authorization.

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
up`, and unflagged `operations start` continue to launch marimo.

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
The default marimo Operations remains the production onboarding owner
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

The Web displays these facts on manual refresh, without continuously supervising
collectors, starting subscriptions, or inventing a fleet-wide green health status.
The existing source lifecycle, backend telemetry and accepted history semantics
are unchanged.

## Explicit FILE DuckLake history backfill (opt-in preview only)

`POST /api/v1/sources/file/backfill` accepts only `{"source_id":"..."}` under
the same exact Host/Origin/Sec-Fetch-Site, CSRF, JSON body, and single-process
mutation lock as registration/receipt. Only an ACTIVE registered FILE snapshot
CSV within the workspace is eligible; its canonical path, symlink boundary,
file type, size and max 12 channels are checked again. A source must have a
**separately persisted accepted receipt** and an explicit timestamp column.
The first browser iteration limits backfill input to **1 MiB** to bound
synchronous event materialization; larger prepared FILE history requires an
existing non-Web workflow. Times must be timezone-aware; invalid input does
not imply that any history was accepted.

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
constraints; legacy and Web writers must not mutate the workspace concurrently.

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
routes. Old marimo Operations/supervisor processes and research notebooks
remain the default product.

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
Each collection has `items`, `total`, `truncated` and up to **100 entries**;
analyses/skips are newest first. `total` describes the snapshot's loaded
population (which is already bounded for phase results), **not a universal
database-wide count**. Results are **not** an auto-refresh/live subscription.
A caller must explicitly request another snapshot.

The monitor response itself does **not** embed the full time series; it offers
asset and evidence identities to select a bounded follow-up history query.
FILE vibration capability details, source credentials, source paths,
arbitrary history paging, and mutation APIs remain excluded. The existing
marimo product continues to read its established runtime composition until cutover.

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
