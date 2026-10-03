# 0019. Keep the Operations UI out of write-repository composition

Status: Accepted

## Context

ADR-0018 moved Operations V2 read-side repository construction and snapshot assembly out of the marimo
application. The app still directly constructed write-side JSON/SQLite repositories for Setup lifecycle
changes, collection intent, FILE analysis persistence, review requests and Maintenance review events. It
also bridged async OPC UA diagnostics through its own worker thread.

Those are local runtime composition responsibilities rather than presentation concerns. Keeping them in
reactive UI cells makes persistence and connector execution details part of the view graph and forces
storage/runtime changes to edit the app.

The UI still needs to own user interaction state and map validated form inputs into domain values such as
RegisteredSource, SourceLifecycleState and FindingReviewAction.

## Decision

- Concrete Operations V2 write/action composition lives in
  `industrial_phm.runtime.operations_app_actions`.
- `OperationsAppActions` is created from the same resolved `OperationsAppPaths` used by the read
  snapshot.
- The facade owns construction of source registry/runtime, collection-control, FILE analysis, finding and
  review repositories.
- The facade delegates domain rules to the existing application use cases. It does not reimplement
  lifecycle, collection, analysis, finding or review semantics.
- Bounded OPC UA diagnostic coroutines are bridged to a worker thread inside the runtime facade so the
  marimo view graph does not own event-loop mechanics.
- Action methods return the minimal persisted state needed for the UI to refresh its local state after a
  successful action.
- The marimo app continues to construct domain input objects from user forms and continues to own success/
  error presentation. It does not construct concrete persistence adapters.
- A contract test prevents concrete read or write repository constructors from returning to the packaged
  Operations V2 app.

## Consequences

Operations V2 can change local persistence adapters and diagnostic execution plumbing without rewriting
presentation cells. Read and write concrete composition are both testable as ordinary Python modules.

This does not create a second source of truth: repositories remain authoritative and the facade performs
the same existing application commands against those repositories.

This decision does not move form validation or view state into the runtime layer. A later UI decomposition
may split form-to-domain mapping further only when that improves a concrete workflow or reuse boundary.
