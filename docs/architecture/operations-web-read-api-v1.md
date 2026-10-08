# Operations Web Read API v1 (initial slice)

This document owns the new **read-only API transport contract**. The installed Operations
product **still launches marimo**. An explicitly started, same-origin **Web monitor
preview** now uses this API to read actual saved evidence; the preview does not yet replace
the production UI, supervise collection/analysis, or offer mutations.

## Endpoint and lifecycle

- `create_operations_web_read_server(workspace_root: Path, *, port=0)` returns an
  unstarted `ThreadingHTTPServer`. The caller owns `serve_forever()`, `shutdown()`
  and `server_close()`.
- The listener **always binds 127.0.0.1**. Read routes are `GET /api/v1/monitor`,
  `GET /api/v1/history/channels`, and `GET /api/v1/history/trend`.
  **Only** `/web/`, `/web/app.js`, and `/web/styles.css` serve packaged static
  assets from the installed Python wheel. No arbitrary file path may be requested.
  POST/PUT/DELETE/OPTIONS are rejected (405). There is no mutation command, Node runtime
  or dev server, repository file proxy, or remote exposure.
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

## Explicit opt-in Web monitor preview

For an initialized, existing Operations workspace, start the **read-only preview
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
`industrial-phm operations up` retain their current behavior.

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

This is **not** a completed production web cutover: first-run/source setup,
write-side CSRF/origin hardening, URL/deep-linked evidence screens,
locale switching, accessibility audit, independent supervision, and
full operational lifecycle/browser acceptance remain in [Issue #449](https://github.com/so9093-K/industrial-phm-framework/issues/449).

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
