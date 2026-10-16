# 0029. Preserve explicitly reviewed outlooks with axis-aware evidence and compare later observations

Status: Accepted (2026-10-16)

Related: [ADR-0023](0023-retain-live-evidence-for-a-bounded-period.md),
[ADR-0025](0025-run-versioned-model-packages-over-ordered-asset-steps.md),
[ADR-0026](0026-retire-remaining-life-estimation.md),
[ADR-0027](0027-condition-and-remaining-life-outlook-from-stored-analyses.md),
[ADR-0028](0028-bind-forecast-and-outlook-to-one-measurement-projection.md).

## Context

Operations Web follows observed measurement → change → conditional outlook → evidence →
human review → reobservation. The existing `GET /api/v1/outlook` is an on-demand numerical
projection and deliberately does not persist every request. Its `measurement_version`
identifies a bounded numerical input projection, **not** a durable raw snapshot.
`data_version` additionally covers anomaly evidence for AI briefing. The
`outlook-briefings.sqlite` repository stores model explanations; it is not a human decision
ledger and does not preserve the full reviewed computation.

Existing operational Findings require an actual persisted AnalysisRun/Evidence pair, and
AnalysisRun uses timezone-aware observation bounds. An acquisition-only signal may have
an ordered acquisition number but no recorded clock interval. Inventing times or
manufacturing an unrelated AnalysisRun just to reuse the Review button would falsify
provenance. Linking to the same asset's unrelated 3-phase/FILE AnalysisRun would do likewise.

Reviewable evidence must survive service restart and supported stopped-workspace
backup/restore; it must not silently reinterpret retained data after a history compaction
or retention action. It must distinguish **the archived computation's truth** from whether
the original input is still retrievable and independently reproducible.

## Decision

1. **Explicit capture:** Ordinary outlook queries and AI questions remain ephemeral.
   Only a user-initiated, authorized `capture for review` command creates a reviewed
   outlook candidate. The supervisor re-reads and recomputes the selected forecast and
   condition outlook under the same exact validated conditions, rejects mismatched
   measurement/data versions, and stores the values it actually computed. The Web
   never submits authoritative numerical results.
2. **Capability-specific immutable evidence:** A persisted condition-outlook evidence
   record has a schema version, stable content digest/ID, asset/source/measurement
   point/kind/series, observation axis and bounded positions, measurement and anomaly
   evidence versions, complete validated selection, prediction settings and interval,
   actual calculated facts/scenarios/meaning, creation time, and provenance
   availability status on re-read. Only this evidence record owns the archived outlook's
   numerical truth. An idempotent replay of the same capture identity must not overwrite
   its bytes. New observations/settings create a distinct record.
3. **Axis-aware observation:** For time history, store actual timezone-aware timestamps.
   For acquisition-only observations, store the original integer acquisition positions
   and the `recorded/assumed/ordinal` time basis separately. An assumed duration or
   synthetic Prophet time axis is never claimed to be a real observed instant.
4. **Human action owner:** Keep Review's existing status transitions
   `open → acknowledged → closed` and append-only human note/action semantics,
   but extend its *validated subject* boundary to support one exact persisted
   outlook evidence identity as well as an existing AnalysisRun/Evidence pair.
   Each human action must be validated against its precise subject and authorized
   through the existing single-writer/CSRF/supervisor boundary. No duplicate
   independent review-status implementation or reinterpretation of a transient
   outlook as an unrelated PHM finding. A review close is not completed maintenance,
   diagnosis, or a safety assessment.
5. **Honest restoration and retention:** Persist the computed fact payload, the
   exact input identity and its digest even if raw history is no longer available.
   On each archived read, calculate a separately labelled `source_recheck`
   (`same_measurement_projection`, `changed`, `different_source`,
   `unavailable`). A matching measurement projection does **not** attest to
   unchanged anomaly/model evidence; a missing source never triggers a fallback
   to a different stream or overwrites the captured facts. Register the new
   repository in the stopped-workspace backup inventory. This capture is a
   **persisted derived numerical projection**, not a pinned raw input snapshot:
   raw live input continues under ADR-0023's bounded retention and is **not**
   kept indefinitely while an outlook review is open. ADR-0023's protection
   of actual AnalysisRun/Evidence reviews is unchanged. The product must not
   claim that it can independently reproduce a captured outlook once its raw
   inputs have expired.
6. **Comparable reobservation:** A comparison is only labelled `same settings,
   new observation` when asset/source/point/kind/series, axis/time basis, limits,
   direction, forecast settings and interpretation match while measurement versions
   differ. Compare archived server-computed reach states and expected/earliest
   offsets without converting acquisition counts and durations unless a verified
   recorded interval exists. Changes to settings are reported separately as assumption
   changes, not observed deterioration. A missing or invalid older record is an
   explicit unavailability result, never a fallback to the newest computation.
7. **Consumer responsibilities:** The Web shows one clear flow to inspect exact
   current evidence, capture/confirm a review, find that saved decision again,
   and compare it with a later recorded observation. AI text may describe the
   stored facts but does not create review notes or change review status.

## Alternatives rejected

- Browser localStorage or in-memory `previous`: not an auditable, restart-safe record.
- Reusing an AI briefing row: answer quality, question and model are not a human
  review decision or source snapshot.
- Reusing a different AnalysisRun by asset ID: breaks exact evidence identity.
- Writing an invented timestamp for ordinal acquisition: false observation claim.
- Automatically saving every GET/AI query: confuses exploration with explicit
  human review and creates unbounded durable artifacts.
- Defining an all-capability generic workflow framework: current two real subjects
  need an axis-aware, narrowly scoped review subject contract instead.

## Acceptance and verified boundaries

- Supervisor re-computation rejects stale measurement/anomaly versions; the Web
  submits no numerical calculation as authoritative input.
- Content-addressed capture IDs, saved-byte digest validation and append-only
  review event IDs prevent accidental overwrites and duplicate human actions.
  Concurrent writes serialize state transitions.
- Unit/API/Chromium tests cover acquisition-axis capture and new observations;
  the existing forecast-history projection preserves timezone-aware instants.
  A made-up timestamp is never introduced for an ordinal acquisition.
- Stopped-workspace backup/restore and view-only read tests exercise durable facts;
  missing/changed source and wrong-asset access are distinguished from a valid
  archived computation. Existing AnalysisRun/Evidence/Review remains unchanged
  except for sharing the same human status transition function.
- Chromium 390/1280px covers capture → review note/acknowledge/close →
  later observation comparison; the integrated #590/#591/#592 branch passes
  baseline CI and Chromium user-flow regression tests.
- **Conscious limitation:** the captured fact snapshot is durable, but raw-input
  pinning and future independent replay after retention are not included.
  The UI exposes this limitation via source re-check. Separately measuring
  screen-reader usability, 200% zoom and longer-term live-history retention
  remains a product evaluation responsibility, not an implicit capability claim.
