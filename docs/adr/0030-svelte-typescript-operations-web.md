# 0030. Build the next Operations Web UI with Svelte, TypeScript and a packaged static bundle

Status: Accepted (2026-10-16) — technical foundation only; production UI cutover is not accepted.

Extends: [ADR-0024](0024-separate-operations-web-ui-from-marimo.md). Does not change
the existing Python Operations API, local supervisor, read/write/CSRF contracts,
[ADR-0028](0028-bind-forecast-and-outlook-to-one-measurement-projection.md) or
[ADR-0029](0029-axis-aware-reviewed-outlook-and-reobservation.md).

## Context

The standalone Web product has grown through direct DOM manipulation in a shared HTML
document, many direct UI states and an expanding monolithic CSS file. Module splitting and
menu reduction were meaningful improvements but did not create a single owner for screen
state, navigation context, reusable components or semantic design tokens.
The backend already owns analysis values, their input identities and review transitions.
Rewriting that backend for a frontend framework would only multiply data/integrity risk.

The product baseline defines independent tasks for Sources, Monitor, Assets,
Investigations, human Review and System. These are **target responsibilities**, not an
assertion that all dedicated screens, review queues or multi-user workflows exist.

## Decision

1. Use **Svelte 5 + TypeScript + Vite** as the preferred compiled frontend for the
   new Operations product, without SvelteKit/SSR or a Node process in the running product.
   React and Lit remain possible replacements if later usability/performance evidence
   contradicts the choice; changing the accepted choice requires a successor ADR.
2. Continue using the existing `/api/v1/` browser-safe, bounded DTOs. The frontend may
   validate their shapes and represent load/empty/stale/failure separately, but
   cannot become an alternative owner of measured values, PHM scores, forecasts,
   retained evidence or review commands. Do not infer a healthy/faulty asset from
   source connectivity, missing data or an anomaly score.
3. Establish **workflow-owned components** and role-based design tokens: display the
   observation and timestamps first, interpretation and conditional assumptions second,
   and a clear next action last. Move from a large static DOM to local reusable
   components and explicit application/route/selection state.
4. Build static JS/CSS in development/CI with `npm ci` and a committed lockfile.
   Include generated assets in the Python wheel **only when built**. The Python
   loopback server serves the requested asset only when its path is in the compiled
   manifest and has an allowed extension. Keep CSP, Host/Origin, no-store,
   anti-frame, same-origin and CSRF contracts. Installing/running the current
   Operations product must not need Node.
5. First exercise the read-only `GET /api/v1/monitor` path on isolated
   `/web-next/`. Build complete workflow slices against the current API and
   exact asset/source/point/channel/time/version/review identity. Never share a
   second unverified write path with the existing UI. The current `/web/`
   remains the default until meaningful functional equivalence and user
   acceptance, including empty/error and accessibility behavior, are verified.
6. Require TypeScript/Svelte checks, reproducible static build, Python wheel
   contents, safe static routing, actual Chromium user interactions at 390,
   1024 and 1440px, plus existing runtime/Python/forecast tests. Automated
   tests do not substitute for actual user observation or field-model validation.

## Alternatives considered

- **Keep direct DOM + incremental CSS cleanup:** minimal dependency change, but
  screen/selection/data state ownership and navigation remain coupled. Does not
  address the accepted product-contract problem.
- **Lit/Web Components:** good progressive enhancement and small runtime, but
  less direct benefit for the planned cross-view workflow/state replacement;
  choose it only if a later measured vertical comparison wins.
- **React + TypeScript + Vite:** mature component/ecosystem choice, but larger
  architectural surface for the current local product without a demonstrated
  advantage in its specific user journey. This is qualitative, not a measured
  performance verdict.
- **Use SvelteKit/Node/SSR in production:** conflicts with local static
  wheel/supervisor deployment without a demonstrated product requirement.
- **Replace all views at once:** breaks the ADR-0024 adoption/rollback policy
  and makes exact evidence/permission regressions difficult to isolate.

## Consequences and verification boundary

The first Svelte slice is deliberately **read-only and not feature-complete**.
It proves a compiled client can consume an existing real API, preserve a selected
asset in the URL and distinguish failed reads from empty observations while
remaining separately packaged. It does not deliver a new Review queue,
condition forecast, source control, `en-US` localization, full screen-reader
acceptance or field performance. These require separate workflow migration
and measured acceptance under the existing product/status owners.

The additional npm/Vite toolchain, locked dependency maintenance and
cross-language CI are accepted build costs. The normal local node and
research marimo remain unchanged.
