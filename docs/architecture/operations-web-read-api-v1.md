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
  Only `POST /api/v1/sources/file`, `POST /api/v1/sources/lifecycle`, and
  `POST /api/v1/sources/collection` are allowed under the protected write contract;
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
single-user local tool, **not a second concurrent writer** for a workspace being
mutated by the legacy Operations UI. The HTTP mutation lock serializes requests
within one preview server only; the JSON source registry does not provide
cross-process write coordination. Do not perform legacy and Web source mutations
against the same workspace simultaneously.

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

OPC UA browse, credential handling, FILE uploads, an isolated first-run
synthetic sample and protected human-review writes remain **out of scope**.
Source lifecycle and OPC UA collection desired-state requests are described below;
those requests do not start a collector or prove actual receipt.
The default marimo Operations remains the production onboarding owner
until the staged Web transition acceptance gates pass.

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
