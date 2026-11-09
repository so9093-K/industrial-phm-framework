import assert from "node:assert/strict";
import {test} from "node:test";
import {parseVibrationFindings, vibrationLinks} from "./vibration-findings.ts";

const body = (intervals: unknown[]) => ({schema_version: 1, asset_id: "bearing", first: 1, last: 123, period_seconds: 60,
  judged: 14, features: 14, meaning: "departures-from-the-first-30-percent-not-fault-diagnosis", intervals});
const change = {feature: "feature.Horizontal_vibration_signals.rms", label: "수평 진동 RMS", unit: "g", direction: "up",
  reason: "record-end", kind: "departure", from: 77, to: 123, baseline: {from: 1, to: 37},
  reference_value: 0.56, typical_value: 7.27, value: 9.1, usual: {low: 0.4, high: 0.7}, trace: [[1, 0.5], [77, 6.9], [123, 7.3]],
  related: [{feature: "feature.Vertical_vibration_signals.rms", label: "수직 진동 RMS", unit: "g", reference: 0.6, current: 2.3, state: "higher"}]};

test("vibration changes read by acquisition number and open the feature at the change", () => {
  const found = parseVibrationFindings(body([change]), "bearing");
  const [first] = found.intervals;
  assert.equal(first.from, 77);
  assert.deepEqual(first.trace[1], {at: 77, value: 6.9});
  assert.equal(first.related[0].label, "수직 진동 RMS");
  assert.throws(() => parseVibrationFindings(body([{...change, related: [{...change.related[0], state: "within"}]}]), "bearing"));
  const links = vibrationLinks("bearing", first);
  const signal = new URL(links.signal, "http://local").searchParams;
  assert.equal(signal.get("vibration_feature"), change.feature);
  assert.equal(signal.get("vibration_at"), "77");
  const compare = new URL(links.compare, "http://local").searchParams;
  assert.deepEqual(["feature_a_from", "feature_a_to", "feature_b_from", "feature_b_to"].map(key => compare.get(key)), ["1", "37", "77", "123"]);
  assert.throws(() => parseVibrationFindings(body([{...change, from: 130}]), "bearing"));
  assert.throws(() => parseVibrationFindings(body([change]), "other"));
  assert.equal(parseVibrationFindings({...body([]), first: null, last: null}, "bearing").first, null);
});
