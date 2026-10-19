import assert from "node:assert/strict";
import {test} from "node:test";
import {parseAcquisitionTrend, trendChart} from "./acquisition-trend.ts";

const body = (points: unknown[]) => ({schema_version: 1, asset_id: "bearing-a", source_id: "bench",
  binding_id: "anomaly-a", feature: "feature.rms", label: "RMS", period_seconds: 60, analyzed: 3,
  sampled: false, points, meaning: "stored-acquisition-features-not-asset-health"});

test("a stored vibration feature is read in acquisition order and drawn on that axis", () => {
  const trend = parseAcquisitionTrend(body([[1, 0.5], [2, 0.6], [5, 1.2]]), "bearing-a", "feature.rms");
  assert.deepEqual(trend.points.map((point) => point.ordinal), [1, 2, 5]);
  const chart = trendChart(trend);
  assert.ok(chart);
  assert.equal(chart.first, 1);
  assert.equal(chart.last, 5);
  assert.equal(chart.high, 1.2);
  assert.match(chart.line, /^M0\.0 /);
  assert.equal(trendChart(parseAcquisitionTrend(body([[1, 0.5]]), "bearing-a", "feature.rms")), null);
});

test("a trend for another asset, feature or out-of-order acquisitions is refused", () => {
  assert.throws(() => parseAcquisitionTrend(body([[1, 0.5]]), "other", "feature.rms"), /형식/);
  assert.throws(() => parseAcquisitionTrend(body([[1, 0.5]]), "bearing-a", "feature.peak"), /형식/);
  assert.throws(() => parseAcquisitionTrend(body([[2, 0.5], [1, 0.6]]), "bearing-a", "feature.rms"), /형식/);
  assert.throws(() => parseAcquisitionTrend(body([[1, null]]), "bearing-a", "feature.rms"), /형식/);
});
