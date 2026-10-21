# Operations Web

The Operations Web, organised by user task, is served at **`/web/`**. The former
`/web-next/` address redirects to it on the same origin. It reads the existing APIs
and never recalculates measured values or health verdicts in the browser.
See [migration and verification boundaries](../docs/product/web-migration.md).

## Verification

```sh
cd frontend
npm ci
npm run check
npm test
npm run build
```

The build outputs `src/industrial_phm/apps/web_next` and an explicit
`asset-manifest.json` read by the Python HTTP server. The package is served
on the **same loopback origin** under `/web/` only after building it.
Screens follow the task menus of `docs/product/overview.md`:
`/web/` (관측 현황), `?page=assets&monitor_asset=…` (설비·신호, with
`tab=summary|anomaly|signals|change|outlook`, optional `method` and `data=history|vibration`),
`?page=investigations`, `?page=maintenance` and `?page=system`. Former `?view=…` addresses are
replaced by their new place with the workflow's own parameters kept. Screen words follow
[Web 화면 용어 기준](../docs/terminology.md#web-화면-용어-기준).
No Node process is required to serve the compiled output; the runtime does
not install Node dependencies.

## Component and design boundaries

- `src/design/tokens.css`: role-based colors, surface/ink, action, focus,
  spacing, typography and panel/control radius. Tokens describe UI meaning;
  they do **not** encode a physical asset's health or a validated alarm.
- `src/styles.css`: shell, accessible shared controls and responsive layout
  used across the new frontend; a page should not invent its own unrelated
  colors, fields or button treatment.
- `src/routes.ts`: task pages, asset tabs, analysis methods and data kinds; former
  addresses map to their new place. Only the route, the asset and a chosen signal travel
  between screens; another asset's conditions or review identities never do.
- `src/App.svelte`: top task menu, read-only/operating mode, same-document navigation.
- `src/components/AssetWorkspace.svelte`: one asset's header, tabs, method/data choice and
  the workflow for that choice. The default data kind comes from the asset's stored data.
- `src/asset-data.ts`: which stored data an asset has (from `/api/v1/forecast/options`);
  it picks a default analysis and says nothing about the asset's condition.
- `src/components/AssetList.svelte`: assets with something to check first, last
  measurement and receive state words shared with `/web/`.
- `src/components/AssetSummary.svelte`: the asset's first screen: record facts and next actions.
- `src/components/CautionNote.svelte`: the single interpretation caution under a result.
- `src/format.ts`: display-only number text (6 significant digits); stored values are never rounded.
- `src/reach.ts`: one wording for a server-computed limit reach; acquisition counts are never turned into durations.
- `model-evidence.ts` `scoreSummary()`/`loadLatestScores()`: stored score, threshold and exceedance only; the asset summary's anomaly section.
- `relation.ts` `strength()`: words for a server-computed correlation shown next to the coefficient.
- `src/components/PageHeading.svelte`: page title, context and optional reload action.
- `src/components/StatusNotice.svelte`: information, uncertainty and
  failure with explicit message/action; an unknown or failed read is not empty.
- `src/components/SignalExplorer.svelte`: read-only asset/channel/range/anchor
  selection and bounded, unconnected mean-bucket dots with a quality table.
- `src/components/DepartureExplorer.svelte`: read-only, model-free baseline
  deviation exploration (stored bucket means, not trained model outputs).
- `src/components/AcquisitionOutlook.svelte`: acquisition-ordinal forecast and
  conditional limits with honest recorded/assumed/ordinal spacing semantics.
  Only server-provided values on an identical asset/source/binding/measurement-version
  are shown. Acquisition AI explanations use the existing supervisor CSRF route
  and must revalidate the exact source/binding/time basis/settings/data version.
  No made-up acquisition timestamps, diagnosis or implicit capture.
- `src/acquisition-outlook.ts`: strict paired acquisition DTO and count horizon
  validation. Read-only GET /forecast/options, /forecast and /outlook.
- `src/components/OutlookBriefings.svelte`: the result's AI explanation, placed right after the
  limit tiles. Shows the latest checked answer with its cited facts, or a single ‘해설 만들기’
  request; custom questions are folded. The last record anchors every explanation; its question
  stays visible, and a pending question labels an earlier answer as such. `data_version`, settings and recalculated
  `measurement_version` are verified before and after reading; a change clears the joined result.
- `src/outlook-briefings.ts`: strict server echo, answer/evidence citation and
  read/write capability boundaries without client-side calculations.
- `src/components/ProjectionExplorer.svelte`: read-only paired history
  forecast/conditional-outlook view; only the same measurement hash and exact
  source/point are displayed together. Condition edits invalidate previous results.
  AI explanations and review requests live in their own components below.
- `src/projections.ts`: separate `measurement_version` and `data_version`,
  exact server meaning/axis/limits verification, bounded table DTO.
- `src/components/ModelRunEvidence.svelte`: read-only model binding, recent
  persisted step, AnalysisRun and exact input-reference verification. Excluded
  steps remain distinct from scored steps. The PHM model store has no separate
  Operational Evidence ID: none is synthesized by the UI.
- `src/model-evidence.ts`: strict asset/source/measurement point, binding,
  position, run, stored input SHA-256 or window digest validation across existing
  /phm/bindings, /phm/trace and /phm/result APIs.
- `src/components/AcquisitionRelation.svelte`: server-owned two-feature correlations
  and acquisition-ordinal scatter evidence. Exact selected source/binding/ordinal
  contracts are validated; uncomputed coefficients remain absent rather than zero.
- `src/acquisition-relation.ts`: read-only same-acquisition response boundary.
- `src/components/AcquisitionFeatureProfile.svelte`: read-only saved acquisition
  feature A/B ordinal comparison, separating delivered/analyzed/unanalyzed/missing
  counts from potentially sampled feature statistics. No time-axis inference.
- `src/acquisition-profile.ts`: strictly bound source/binding/feature/ordinal
  profile DTO; unknown metrics never become zero or a health assertion.
- `src/components/AcquisitionSpectrum.svelte`: server-owned verified original
  waveform Welch PSD, separate ordinal A/B ranges, equal per-channel linear
  frequency/power axes, missing raw-waveform and storage failures distinguished.
- `src/spectrum.ts`: acquisition binding/sampling rate/ordinal and PSD channel/
  frequency/band consistency contracts. Ordinal positions are not clock times.
- `src/components/ReviewRequest.svelte`: the outlook's ‘검토 요청’. It names the shown selection,
  versions and source/binding/time-basis provenance; the supervisor recomputes and stores every
  number (ADR-0029). A changed recomputation discards the shown result; an unknown outcome is safe to retry.
- `src/components/ReviewQueue.svelte`: the maintenance queue of analysis, model-result and requested
  outlook reviews, filtered by status and kind, with exact `capture_id`/`finding_id` links. The item
  just acted on stays open when its new status leaves the filter.
- `src/components/OutlookReviewDetail.svelte`: one requested outlook: the archived result, source
  re-check and ‘지금 데이터로 다시 계산해 비교’.
- `src/components/FindingReviewDetail.svelte`: one requested analysis or model-result review: its
  exact evidence (or the stored model result's binding/position) and its history.
  `src/review-evidence.ts` joins the reviewed measurement's interval, feature changes, AI answer
  and other models with the same complete input identity. Each failed part stays unread with a retry;
  a later confirmed interval cannot make an earlier measurement appear confirmed already.
- `src/components/ReviewActions.svelte`: the shared append-only note/acknowledge/close for every
  review subject (a retried uncertain action reuses its event ID; a 409 re-reads; close asks once more).
  Confirm and close record the person's inspect/observe/no-action decision. Older events without
  a decision remain readable and do not acquire an invented one.
- `src/components/ModelExplanation.svelte`, `src/components/ModelReviewRequest.svelte`: the selected
  model result's AI explanation against an earlier analyzed measurement (only answers of the same run,
  shown with the comparison the server stored and checked) and its review request.
  `src/model-explanations.ts`: their DTOs and writes.
- `src/components/InvestigationRecords.svelte`: the ‘분석 기록’ page. Stored 3-phase and file
  feature analyses, applied models and analyses that did not run, per asset, each result with its
  review request. `src/analysis-records.ts`: their strict DTOs; a malformed list is reported as
  unreadable without hiding the asset list.
- `src/components/OperationsPage.svelte`: the ‘운영 관리’ page with two sections, ‘데이터 연결’
  (`CsvStart`, `ConnectionList`) and ‘시스템 상태’ (`SystemStatus`: local service readiness and store
  read state; it opens even when the store read fails). `src/operations-status.ts`: their DTOs, with
  the same receipt words as `/web/` (registration, file read and live receipt kept apart).
- `src/components/CsvStart.svelte`: one CSV to stored measurements. The browser preview
  (`src/csv-preview.ts`) applies the selected time zone only to naive timestamps, including mixed
  files; the chart keeps elapsed time gaps and shows the record period in KST.
  It shows columns, blocking problems, a summary and a chart; the server checks
  without saving; then register → use → read once → store history as visible steps. A retry resumes
  from the server's state and never registers or stores twice.
- `src/components/ConnectionList.svelte`: each registered connection with its one next step and other
  actions (`src/connections.ts`). Pause and collection stop ask once more.
- `src/components/ConnectionRegistration.svelte`: a CSV in the workspace or with declared 3-phase roles
  (checked before registering) and a local OPC UA server's variables. `src/components/SampleWorkspace.svelte`:
  the isolated synthetic sample; an unknown start or stop is checked again, never resent.
- `src/components/ModelConnect.svelte`, `src/model-connect.ts`: anomaly detection packages whose
  declared input fits this asset's streams, and connecting one; why nothing fits is said plainly.
- `src/components/ScoreTrend.svelte`, `src/components/ModelInput.svelte`, `src/model-trend.ts`: a model's
  stored scores in input order with its threshold and exceedance intervals (skipped steps stay gaps),
  and the selected measurement's raw waveform envelope or window values. The first stored exceedance
  is marked by a vertical line and a link to its measurement, including isolated exceedances outside
  sustained intervals. Its label uses measured time or the same source's recorded acquisition interval.
- `src/components/ModelScoreOverlay.svelte`: every model on one measurement stream on one axis, each
  score divided by that model's own stored threshold; a row opens that model (keeping the measurement in
  view), a point opens that measurement. A measurement inside an over-threshold interval is compared by
  default with the last analyzed one before the interval (`beforeInterval` in `src/model-trend.ts`).
- `src/components/MonitorAttention.svelte`, `src/monitor-attention.ts`: what needs a look per asset (model
  over threshold, refused or waiting input, model that cannot run, review in progress, a requested
  collection without recent receipt), each opening the exact place; read again every 3 seconds while
  visible, and a failed read hides earlier items. The monitor, asset list and summary distinguish
  complete counts from loading, partial and failed reads; an unread part never means zero items.
  Sustained model intervals lead the threshold notice; isolated recent crossings are separate.
- `src/components/ElectricalCondition.svelte`, `src/electrical-condition.ts`: 3-phase load, unbalance and
  reference-pattern score of a recent period against an earlier one (`/api/v1/condition`), times to check
  first and per-phase values; KST inputs travel as the same instant and lines never cross missing data.
- `src/components/AnalysisOptions.svelte`, `src/capabilities.ts`: what an asset's stored data supports
  (`/api/v1/explore/capabilities`), each analysis opening for that asset and data kind, a fitting model one
  link away, and what cannot be done listed once with its reason.
- `src/writes.ts`: the supervisor-session POST every write uses; it reads both error body shapes and
  tells a refused, forbidden or unknown outcome apart.
- `src/review-writes.ts`: one status policy, note rule and write-failure mapping for every review.
  `src/finding-reviews.ts`: `GET /api/v1/reviews` DTOs with history replay and `/api/v1/reviews/action`.
- `src/outlook-captures.ts`: strict capture/identity/review DTOs, status replay, today's recomputation
  under the saved conditions and same-axis comparison. `src/session.ts`: supervisor write session and
  CSRF token shared by AI explanation and review writes.
- `src/reviews.ts`: exact asset/run/evidence joins; partial/truncated/missing
  read evidence remains explicit and never turns into a missing or closed review.
- `src/components/RelationExplorer.svelte`: read-only paired signal correlation
  grouped by exact source/point/interpretation and observed timestamp. A correlation
  is not a causal explanation or an equipment-health conclusion.
- `src/relation.ts`: strict pairing, asset/channel, group, timestamp and nullable
  correlation validation; no arbitrary timestamp interpolation.
- `src/components/PeriodComparison.svelte`: editable two-period (KST) read-only
  stored-history profile comparison with source/point/interpretation-separated
  evidence rows, missingness and quality. A is a user-chosen period, not a
  validated normal period. Editing a period immediately invalidates earlier evidence;
  valid selected times persist in the URL, while incomplete dates block recalculation.
  A bookmarked selection is not a saved or validated analysis result.
- `src/comparison.ts`: bounded two-period history API DTO contract. The server
  owns quantile values; an inverted percentile sequence fails closed instead of
  being reordered in the client.
- `src/departures.ts`: strict asset/channel/baseline and server-meaning DTO
  validation; missing evidence, no threshold departures and failed reads differ.
  The endpoint does not expose the underlying source/point/interpretation identity.
  Use stored signal investigation to inspect provenance; do not infer fault health.
- `src/history.ts`: typed boundary for existing stored-history APIs; source,
  measurement-point and interpretation identities are never merged.

- `src/time-axis.ts`, `src/components/XAxis.svelte`: responsive time ticks. Timestamped records use KST;
  acquisitions use elapsed time from #1 only with a recorded or explicitly assumed interval, otherwise
  measurement order. Receipt/replay speed never supplies an interval. `src/reach.ts` also names past
  expected reach times relative to the last timestamped record without asserting an observed crossing.

New workflow components must reuse these meanings and preserve keyboard
focus, labels and screen-reader reading order. A status token is not evidence
of equipment condition. Actual operator usability must be observed
separately from CI and browser layout tests.

Standard `uv build` rebuilds the frontend with `npm ci` and includes it in both
the sdist and wheel. A wheel rebuilt from the sdist uses those same locked sources.
Missing Node/npm or an incomplete manifest fails the distribution build; an old local
bundle is never accepted instead. `make up` and `make demo` also prepare these assets.
Python editable setup (`uv sync`) skips the frontend build, so use `make frontend`
before opening `/web/` directly. Node.js >=22.12 and npm are needed for these
source builds; installing and serving a prebuilt wheel needs neither.
패키징을 변경할 때에는 `uv build`의 sdist → wheel 재빌드와 설치된 wheel에서
Node 없이 정적 자산이 제공되는지 별도로 확인합니다. 일반 PR의 Source CI는 이를 자동 검증하지 않습니다.
This frontend is the default `/web/` UI; the previous direct-DOM assets are removed.
Automated checks do not establish UX acceptance or field validation.
