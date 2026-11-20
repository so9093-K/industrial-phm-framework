import assert from "node:assert/strict";
import {test} from "node:test";
import {parseHistoryStreams} from "./history.ts";
import {buildPayload, parseBuildResult, referencePeriod} from "./history-model.ts";
import {modelNames, parseModelBindings, parseModelRun, parseModelTrace} from "./model-evidence.ts";

const facts = {schema_version: 1, asset_id: "pump-01", acquisition: null,
  history: {channels: ["vibration", "temperature", "current"],
    start_at: "2026-10-01T00:00:00+00:00", end_at: "2026-10-18T00:00:00+00:00", measurement_count: 8640,
    streams: [
      {source_id: "pump-file", measurement_point_id: null, channels: ["vibration", "temperature"],
        start_at: "2026-10-15T00:00:00+00:00", end_at: "2026-10-18T00:00:00+00:00"},
      {source_id: "pump-opc", measurement_point_id: "drive-end", channels: ["current"],
        start_at: "2026-10-01T00:00:00+00:00", end_at: "2026-10-02T00:00:00+00:00"},
      {source_id: "broken", measurement_point_id: 3, channels: ["x"],
        start_at: "2026-10-01T00:00:00+00:00", end_at: "2026-10-02T00:00:00+00:00"},
    ]}};

test("each source and measurement point offers only its own signals and period", () => {
  const [file, opc, ...rest] = parseHistoryStreams(facts);
  assert.deepEqual([file.sourceId, file.pointId, file.channels], ["pump-file", null, ["vibration", "temperature"]]);
  assert.deepEqual([opc.sourceId, opc.pointId, opc.channels, opc.endAt],
    ["pump-opc", "drive-end", ["current"], "2026-10-02T00:00:00+00:00"]);
  assert.equal(rest.length, 0);
  assert.deepEqual(parseHistoryStreams({...facts, history: null}), []);
  assert.throws(() => parseHistoryStreams({history: facts.history}), /형식/);
});

test("a build names the stream's measurement point, and leaves it out when there is none", () => {
  const [file, opc] = parseHistoryStreams(facts);
  const request = {assetId: "pump-01", channels: ["current"], from: "a", to: "b", windowSeconds: 600};
  assert.equal(buildPayload({...request, stream: opc}).measurement_point_id, "drive-end");
  assert.equal(buildPayload({...request, stream: opc}).source_id, "pump-opc");
  assert.equal("measurement_point_id" in buildPayload({...request, stream: file}), false);
});

test("the reference period is the first share of the stream's record or what was entered", () => {
  const read = parseHistoryStreams(facts)[0];
  assert.deepEqual(referencePeriod("first-30", read),
    {from: "2026-10-15T00:00:00.000Z", to: "2026-10-15T21:36:00.000Z"});
  assert.equal(referencePeriod("first-50", read).to, "2026-10-16T12:00:00.000Z");
  assert.throws(() => referencePeriod("custom", read, {from: "", to: ""}), /시작과 끝/);
  assert.throws(() => referencePeriod("custom", read,
    {from: "2026-10-16T00:00:00+09:00", to: "2026-10-15T00:00:00+09:00"}), /뒤여야/);
});

test("a build answers with the binding, or with the reason the period was too thin", () => {
  assert.deepEqual(parseBuildResult({schema_version: 1, built: true, binding_id: "phm-pump",
    reference_windows: 144, skipped_windows: 0, package_id: "p", threshold: 0.6}),
  {built: true, bindingId: "phm-pump", referenceWindows: 144, skippedWindows: 0, reused: false});
  assert.deepEqual(parseBuildResult({schema_version: 1, built: true, binding_id: "phm-pump", reused: true,
    reference_windows: 144, skipped_windows: 0}), {built: true, bindingId: "phm-pump", referenceWindows: 144,
    skippedWindows: 0, reused: true});
  assert.equal(parseBuildResult({schema_version: 1, built: false, reason: "최소 24개",
    reference_windows: 12, skipped_windows: 0}).built, false);
  assert.throws(() => parseBuildResult({schema_version: 1, built: true, reference_windows: 1, skipped_windows: 0}));
});

test("a stored-history window result renders by its period, not a window ID", () => {
  const end = Date.parse("2026-10-16T12:40:00Z") * 1000;
  const binding = {binding_id: "phm-pump", package_id: "p", source_id: "pump-file", asset_id: "pump-01",
    measurement_point_id: null, step_kind: "history-window", recorded_replay: false, health: "ok",
    package: {package_id: "p", recipe_id: "operator-history-iforest-v1", output: {task: "anomaly-score"}},
    latest_analyzed: {position: end, state: "analyzed"}, latest_processed: {position: end, state: "analyzed"}};
  const model = parseModelBindings({schema_version: 1, change_seq: 3, bindings: [binding]}, "pump-01")[0];
  const step = {position: end, step_key: "history:1792160400", state: "analyzed", reason: null,
    analysis_run_id: "run-1", change_seq: 3, replay: false,
    input_reference: {kind: "history-window", source_id: "pump-file", asset_id: "pump-01",
      measurement_point_id: null, window_start: "2026-10-16T12:30:00+00:00",
      window_end: "2026-10-16T12:40:00+00:00", snapshot_id: 7, input_digest: "b".repeat(64)},
    event_start: "2026-10-16T12:30:00+00:00", event_end: "2026-10-16T12:40:00+00:00",
    processed_at: "2026-10-25T00:00:00+00:00", output: {score: 0.5, exceeds_threshold: false}, features: {}};
  const pointer = parseModelTrace({schema_version: 1, binding_id: "phm-pump", limit: 64, steps: [step]}, model).steps[0];
  assert.equal(parseModelRun({schema_version: 1, binding_id: "phm-pump", step}, model, pointer).evidenceKind, "history-window");
  assert.throws(() => parseModelRun({schema_version: 1, binding_id: "phm-pump",
    step: {...step, input_reference: {...step.input_reference, snapshot_id: "7"}}}, model, pointer), /맞지 않아/);
});

test("two models built from one asset's record are told apart by the period they learned", () => {
  const row = (id: string, start: string) => ({binding_id: id, package_id: "p-" + id, source_id: "s", asset_id: "pump-01",
    measurement_point_id: null, step_kind: "history-window", recorded_replay: false, health: "ok",
    latest_analyzed: null, latest_processed: null,
    package: {package_id: "p-" + id, recipe_id: "operator-history-iforest-v1", estimator_kind: "isolation-forest-refit-v1",
      output: {task: "anomaly-score"}, input: {channels: ["a", "b"]},
      training_scope: {reference_start: start, reference_end: "2026-10-16T00:00:00+00:00"}}});
  const list = parseModelBindings({schema_version: 1, change_seq: 1,
    bindings: [row("one", "2026-10-15T00:00:00+00:00"), row("two", "2026-10-15T12:00:00+00:00")]}, "pump-01");
  const names = [...modelNames(list).values()];
  assert.equal(new Set(names).size, 2);
});
