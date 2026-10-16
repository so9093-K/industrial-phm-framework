# 0029. Preserve explicitly reviewed outlooks with axis-aware evidence and compare later observations

Status: Proposed (2026-10-16)

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

## Proposed decision

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
   availability status. Only this evidence record owns the archived outlook's
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
5. **Honest restoration and retention:** Preserve the captured fact payload and
   provenance digest even if the original raw history is no longer available. Mark
   `input_recheck_unavailable` explicitly; never fabricate data, look up a different
   signal identity or silently replace the captured calculation with a new one.
   Register the durable repository in the workspace state/backup inventory and
   add restart/restore coverage. Honor ADR-0023's protected evidence rules where
   source evidence can still be pinned.
6. **Comparable reobservation:** A comparison is only labelled `same settings,
   new observation` when asset/source/point/kind/series, axis/time basis, limits,
   direction, forecast settings and interpretation match while measurement versions
   differ. Compare archived server-computed states, central estimates and ranges;
   do not convert between acquisition counts and duration unless a verified recorded
   interval exists. Changes to settings are reported separately as assumption
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

## Acceptance gates before Accepted

- A real, authorized capture is reconstructed from server-owned measurements,
  not browser-supplied figures; stale versions/conflicting requests fail closed.
- Same evidence and action are idempotent; different versions/settings are distinct.
- Time-only and acquisition-only evidence store their original axis honestly.
- Restart, stopped-workspace backup/restore, source-history loss and read-only mode
  preserve truthful behavior.
- Existing AnalysisRun/Evidence/Review contracts and historical records remain readable.
- Browser acceptance covers capture → evidence → explicit review note/acknowledge →
  new observation → same-settings comparison, plus wrong asset and unavailable provenance.
- Accepted state is recorded **only after the implementation and checks pass**.
