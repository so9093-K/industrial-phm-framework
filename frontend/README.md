# Operations Web-next read-only vertical slice

This is an **isolated technical acceptance slice**, not the default product.
It exercises real `GET /api/v1/monitor` observations without importing models or
recalculating health verdicts. The current `/web/` UI remains authoritative.

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
Open `/web-next/` for asset observation and `/web-next/?view=signals&monitor_asset=...`
for stored signal exploration. The latter is a partial workflow migration: one
channel at a time, original semantics and bucket quality preserved, no model
results or review writes.
No Node process is required to serve the compiled output; the runtime does
not install Node dependencies.

## Component and design boundaries

- `src/design/tokens.css`: role-based colors, surface/ink, action, focus,
  spacing, typography and panel/control radius. Tokens describe UI meaning;
  they do **not** encode a physical asset's health or a validated alarm.
- `src/styles.css`: shell, accessible shared controls and responsive layout
  used across the new frontend; a page should not invent its own unrelated
  colors, fields or button treatment.
- `src/components/PageHeading.svelte`: page title, context and reload action.
- `src/components/StatusNotice.svelte`: information, uncertainty and
  failure with explicit message/action; an unknown or failed read is not empty.
- `src/components/AssetSelector.svelte`: semantic asset selection.
- `src/components/ObservationDetails.svelte`: measured fact, quality/flow
  distinction and evidence navigation.
- `src/components/SignalExplorer.svelte`: read-only asset/channel/range/anchor
  selection and bounded, unconnected mean-bucket dots with a quality table.
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
