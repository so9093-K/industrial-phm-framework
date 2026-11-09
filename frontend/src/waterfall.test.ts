import assert from "node:assert/strict";
import {test} from "node:test";
import {parseWaterfall, shade} from "./waterfall.ts";

const body = {schema_version: 1, asset_id: "b", meaning: "stored-waveform-spectra-not-fault-frequencies",
  sampling_rate_hz: 25600, frequencies: [0, 100, 200], acquisitions: [1, 2], floor_db: -60,
  channels: [{channel: "Horizontal_vibration_signals", label: "수평 진동", decibels: [[-50, -20, -60], [-10, 0, -40]]}]};

test("each acquisition's spectrum reads as one row, and stronger power reads darker", () => {
  const read = parseWaterfall(body, "b");
  assert.equal(read.channels[0].decibels[1][1], 0);
  assert.throws(() => parseWaterfall({...body, acquisitions: [1]}, "b"));
  assert.throws(() => parseWaterfall({...body, channels: [{...body.channels[0], decibels: [[0, 0], [0, 0]]}]}, "b"));
  const [weak, strong] = [shade(-60, -60), shade(0, -60)];
  assert.ok(strong.reduce((a, b) => a + b) < weak.reduce((a, b) => a + b));
  assert.deepEqual(shade(-90, -60), weak);
});
