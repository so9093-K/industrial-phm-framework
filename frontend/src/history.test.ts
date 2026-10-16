import assert from "node:assert/strict";
import {test} from "node:test";
import {groupHistory, parseChannels, parseTrend, pointsForChart} from "./history.ts";

const bucket = (source: string, interpretation: string, mean: number | null, usable = 1) => ({
  channel_id: "R", source_id: source, measurement_point_id: "motor-a",
  interpretation_id: interpretation,
  bucket_start: "2026-10-01T00:01:00Z",
  mean, usable_count: usable, null_count: 0, non_good_count: 0, conflict_count: 0,
  semantics: {unit: interpretation === "i1" ? "A" : "V", observed_property: "current"},
});

const data = (buckets: unknown[]) => ({
  asset_id: "motor", channel_ids: ["R"], start_at: "2026-10-01T00:00:00Z",
  end_at: "2026-10-01T01:00:00Z", assessed_at: "2026-10-16T00:00:00Z",
  buckets, latest_stored: [],
});

test("channels are strictly for the selected asset", () => {
  assert.deepEqual(
    parseChannels({asset_id: "motor", channels: {items: ["R", "R", "S"], truncated: false}}, "motor").ids,
    ["R", "S"],
  );
  assert.throws(
    () => parseChannels({asset_id: "other", channels: {items: [], truncated: false}}, "motor"),
    /선택한 설비/,
  );
});

test("source and interpretation differences never become one measurement series", () => {
  const trend = parseTrend(data([bucket("src1", "i1", 2), bucket("src1", "i2", 8),
    bucket("src2", "i1", 4)]), "motor", "R");
  assert.equal(groupHistory(trend).length, 3);
});

test("null/non-good points cannot become drawn values or invented zero", () => {
  const trend = parseTrend(data([bucket("src1", "i1", null, 0), bucket("src1", "i1", 0, 1)]), "motor", "R");
  const group = groupHistory(trend)[0];
  const points = pointsForChart(group, trend.startAt, trend.endAt);
  assert.equal(points.length, 1);
  assert.equal(points[0].bucket.mean, 0);
});

test("mixed source, invalid counts and wrong asset cannot render", () => {
  assert.throws(() => parseTrend(data([bucket("src1", "i1", 2)]), "different", "R"), /선택한 설비/);
  assert.throws(() => parseTrend(data([{...bucket("src1", "i1", 1), null_count: -1}]), "motor", "R"),
    /품질 건수/);
});
