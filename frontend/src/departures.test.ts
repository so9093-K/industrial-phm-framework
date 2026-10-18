import assert from "node:assert/strict";
import { test } from "node:test";
import { departureChart, parseDepartures } from "./departures.ts";

const result = () => ({
  schema_version: 1,
  meaning: "departures-from-a-chosen-baseline-not-fault-diagnosis",
  asset_id: "motor-1", available: ["R"],
  series: ["R"], units: { R: "A" }, bucket_seconds: 60, threshold: 3.5,
  baseline: {name: "first-30", from: "2026-10-10T00:00:00Z", to: "2026-10-10T00:30:00Z"},
  channels: [{ key: "R", state: "scored", median: 2, spread: 0.2, marked: 1 }],
  score: [["2026-10-10T00:34:00Z", 4.1, "R"]],
  intervals: [{
    start: "2026-10-10T00:34:00Z", end: "2026-10-10T00:35:00Z",
    points: 1, channels: ["R"], channel: "R", median: 2, value: 3.4,
    direction: "up", distance: 4.1,
  }],
  interval_count: 1,
});

test("server meaning, asset, signal and baseline must match selected task", () => {
  assert.equal(parseDepartures(result(), "motor-1", "R", "first-30").intervalCount, 1);
  assert.throws(() => parseDepartures(result(), "other", "R", "first-30"), /맞지 않아/);
  assert.throws(() => parseDepartures(result(), "motor-1", "S", "first-30"), /맞지 않아/);
  assert.throws(() => parseDepartures(result(), "motor-1", "R", "all"), /맞지 않아/);
  assert.throws(() => parseDepartures({...result(), meaning: "validated-fault"}, "motor-1", "R", "first-30"), /맞지 않아/);
});

test("no departures differs from insufficient baseline and never becomes health", () => {
  const empty = result();
  empty.channels = [{key: "R", state: "scored", median: 2, spread: 0.2, marked: 0}];
  empty.score = [];
  empty.intervals = [];
  empty.interval_count = 0;
  assert.equal(parseDepartures(empty, "motor-1", "R", "first-30").scored.state, "scored");
  empty.channels = [{key: "R", state: "short-baseline", median: 2, spread: 0.2, marked: 0}];
  assert.equal(parseDepartures(empty, "motor-1", "R", "first-30").scored.state, "short-baseline");
});

test("intervals reject mixed source evidence and invalid numeric values", () => {
  const mixed = result();
  mixed.intervals[0].channel = "S";
  assert.throws(() => parseDepartures(mixed, "motor-1", "R", "first-30"), /선택하지 않은/);
  const negative = result();
  negative.threshold = -1;
  assert.throws(() => parseDepartures(negative, "motor-1", "R", "first-30"), /조건/);
});

test("the chart marks the baseline, the threshold and each interval, and never bridges a gap", () => {
  const data = parseDepartures(result(), "motor-1", "R", "first-30");
  assert.equal(departureChart({...data, score: []}), null);
  const at = (minute: number) => new Date(Date.UTC(2026, 0, 1, 0, minute)).toISOString();
  const chart = departureChart({...data,
    baseline: {...data.baseline, from: at(0), to: at(3)},
    score: [0, 1, 2, 3, 10, 11].map((minute, i) => ({at: at(minute), distance: i})),
    intervals: [{...data.intervals[0], start: at(10), end: at(11)}]})!;
  // A ten-minute hole between minute 3 and 10 starts a new line.
  assert.equal(chart.path.split("M").length - 1, 2);
  assert.ok(chart.baseline.x === 0 && chart.baseline.width > 0 && chart.baseline.width < chart.width / 2);
  assert.ok(chart.intervals[0].x > chart.width / 2);
  assert.ok(chart.thresholdY > 0 && chart.thresholdY < chart.height);
});
