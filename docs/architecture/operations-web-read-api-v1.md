# Operations Web Read API v1 (initial slice)

This document owns the new **read-only API transport contract**. The installed Operations
product **still launches marimo**; this API server is a programmatic opt-in read boundary
and is not yet the production user interface or a completed dashboard.

## Endpoint and lifecycle

- `create_operations_web_read_server(workspace_root: Path, *, port=0)` returns an
  unstarted `ThreadingHTTPServer`. The caller owns `serve_forever()`, `shutdown()`
  and `server_close()`.
- The listener **always binds 127.0.0.1**. Read routes are `GET /api/v1/monitor`,
  `GET /api/v1/history/channels`, and `GET /api/v1/history/trend`.
  POST/PUT/DELETE/OPTIONS are rejected (405). There is no static UI, mutation command,
  node-server dependency, repository file proxy, or remote exposure.
- Host must be `127.0.0.1:<bound-port>` or `localhost:<bound-port>`. Optional
  `Origin` must be the same allowed HTTP origin, and `Sec-Fetch-Site: cross-site`
  is rejected. No wildcard CORS headers are emitted. This is the **initial GET-only**
  security boundary, not final write-side CSRF/authentication readiness.
- Replies use `application/json`, `Cache-Control: no-store`, `nosniff`,
  anti-frame and restrictive content security headers; 403/404/405/503 errors carry
  **coded, path-free** JSON, not exception detail or repository paths. Invalid
  history query parameters return 400; an uninitialized/unreadable history returns 503.
- Caller must pass one existing workspace directory. Read composition uses only
  `INDUSTRIAL_PHM_OPERATIONS_WORKSPACE` and does not honor granular repository
  environment overrides. The API does not supervise collection/analysis.

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
