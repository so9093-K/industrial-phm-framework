# Operations Web-next

The next Operations Web, organised by user task. It is **not yet the default
product**: the current `/web/` UI stays authoritative until every workflow, permission
and recovery path is accepted here. It reads the existing APIs and never recalculates
measured values or health verdicts in the browser.

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
on the **same loopback origin** under `/web-next/` only after building it.
Screens follow the task menus of `docs/product/overview.md`:
`/web-next/` (관측 현황), `?page=assets&monitor_asset=…` (설비·신호, with
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
- `src/components/OutlookBriefings.svelte`: existing supervisor's persisted
  AI explanations, exact server-selected settings, `data_version` and recalculated
  `measurement_version` verification, CSRF-protected explicit question.
  A changed version clears the joined projection and all stale answers.
- `src/outlook-briefings.ts`: strict server echo, answer/evidence citation and
  read/write capability boundaries without client-side calculations.
- `src/components/ProjectionExplorer.svelte`: read-only paired history
  forecast/conditional-outlook view; only the same measurement hash and exact
  source/point are displayed together. Condition edits invalidate previous results.
  Does not submit reviews, store outlook captures, or call AI for explanations.
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
- `src/components/ReviewInbox.svelte`: the maintenance page's one-snapshot review list for
  every asset, exact Finding/AnalysisRun/Evidence identities under 기술 상세. Review actions
  stay in `/web/` until migrated.
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
  validated normal period; model/acquisition/relation/PSD workflows remain in /web/.
- `src/comparison.ts`: bounded two-period history API DTO contract.
- `src/departures.ts`: strict asset/channel/baseline and server-meaning DTO
  validation; missing evidence, no threshold departures and failed reads differ.
  The endpoint does not expose the underlying source/point/interpretation identity.
  Use stored signal investigation to inspect provenance; do not infer fault health.
- `src/history.ts`: typed boundary for existing stored-history APIs; source,
  measurement-point and interpretation identities are never merged.

New workflow components must reuse these meanings and preserve keyboard
focus, labels and screen-reader reading order. A status token is not evidence
of equipment condition. Actual operator usability must be observed
separately from CI and browser layout tests.

The build must be performed before `uv build` for a wheel that includes this
preview. Default `make up` and `/web/` work without a Node toolchain.
This preview is not a capability-complete replacement, does not modify data,
and must not be called a UX acceptance or field-validation result.
