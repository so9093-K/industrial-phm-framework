# Operations Web-next read-only vertical slice

This is an **isolated technical acceptance slice**, not the default product.
It exercises real `GET /api/v1/monitor` observations without importing models or
recalculating health verdicts. The current `/web/` UI remains authoritative.
This slice is intended to test Svelte + TypeScript + Vite, selected asset
context, error vs empty states, token-based styles and packaged static assets.

```sh
cd frontend
npm ci
npm run check
npm run build
```

The build outputs `src/industrial_phm/apps/web_next` and an explicit
`asset-manifest.json` read by the Python HTTP server. The package is served
on the **same loopback origin** under `/web-next/` only after building it.
No Node process is required to serve the compiled output; the runtime does
not install Node dependencies.

The build must be performed before `uv build` for a wheel that includes this
preview. Default `make up` and `/web/` work without a Node toolchain.
This preview is not a capability-complete replacement, does not modify data,
and must not be called a UX acceptance or field-validation result.
