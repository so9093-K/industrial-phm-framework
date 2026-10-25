import assert from "node:assert/strict";
import {test} from "node:test";
import {buildPayload, historyFeatureLabel, parseBuildResult, parseHistoryStreams, referencePeriod, streamLabel} from "./history-model.ts";
import {attentionByAsset, parsePhmMonitor} from "./monitor-attention.ts";
import {modelNames, parseModelBindings, parseModelRun, parseModelTrace, windowLabel} from "./model-evidence.ts";

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
  assert.equal(streamLabel(opc), "pump-opc · 측정 위치 drive-end");
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
  assert.equal(windowLabel(end), "10. 16. 21:40까지 구간");
});

test("history statistics read with the signal's own name; other labels stay", () => {
  const names = new Map([["motor_temp_c", {label: "모터 온도", unit: "°C"}]]);
  assert.equal(historyFeatureLabel("motor_temp_c 표준편차", names), "모터 온도 (°C) 표준편차");
  assert.equal(historyFeatureLabel("motor_temp_c.max", names), "모터 온도 (°C) 최대");
  assert.equal(historyFeatureLabel("vibration_mm_s 평균", names), "vibration_mm_s 평균");
  assert.equal(historyFeatureLabel("수평 진동 RMS", names), "수평 진동 RMS");
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
  assert.match(names[0], /^Isolation Forest \(기준 10\. 15\. 09:00~10\. 16\. 09:00 · 신호 2개\)$/);
});

test("a sustained crossing of a stored-history model is a measured-signal change, not electrical", () => {
  const groups = attentionByAsset([{bindingId: "b", assetId: "pump-01", stepKind: "history-window", recipeId: null,
    packageId: "p", estimatorKind: null, state: "processed", reason: null,
    analyzed: {position: 2_000_000, exceeds: true}, ongoing: {start: 1_000_000, steps: 5, startAt: "2026-10-16T12:30:00Z"},
    processed: 2_000_000}], null);
  assert.equal(groups[0].notes[0].label, "측정 신호 변화 확인 필요");
});

test("a monitor note tells two same-method models apart by the period each learned", () => {
  const model = (bindingId: string, start: string) => ({binding_id: bindingId, asset_id: "pump-01",
    step_kind: "history-window", recipe_id: "operator-history-iforest-v1", package_id: "p-" + bindingId,
    estimator_kind: "isolation-forest-refit-v1", processing_state: "processed", processing_reason: null,
    latest_analyzed: {position: 2_000_000, output: {exceeds_threshold: true}},
    open_interval: {start_position: 1_000_000, step_count: 4, start_event_at: "2026-10-16T12:30:00Z"},
    latest_processed: {position: 2_000_000},
    training_reference: {start, end: "2026-10-16T00:00:00+00:00", channels: 2}});
  const monitor = parsePhmMonitor({schema_version: 1, assessed_at: null, truncated: false,
    items: [model("one", "2026-10-15T00:00:00+00:00"), model("two", "2026-10-15T12:00:00+00:00")]});
  const detail = attentionByAsset(monitor.models, null)[0].notes[0].detail;
  assert.match(detail, /^Isolation Forest \(기준 10\. 15\. 09:00~10\. 16\. 09:00 · 신호 2개\) .* \/ /);
  assert.match(detail, / \/ Isolation Forest \(기준 10\. 15\. 21:00~10\. 16\. 09:00 · 신호 2개\) /);
  const alone = attentionByAsset(parsePhmMonitor({schema_version: 1, assessed_at: null, truncated: false,
    items: [model("one", "2026-10-15T00:00:00+00:00")]}).models, null)[0].notes[0].detail;
  assert.doesNotMatch(alone, /기준 10\./);
});
