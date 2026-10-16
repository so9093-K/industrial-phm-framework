import assert from "node:assert/strict";
import { test } from "node:test";
import { parseDepartures, scoreDots } from "./departures.ts";

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
  assert.throws(() => parseDepartures(result(), "other", "R", "first-30"), /일치하지/);
  assert.throws(() => parseDepartures(result(), "motor-1", "S", "first-30"), /일치하지/);
  assert.throws(() => parseDepartures(result(), "motor-1", "R", "all"), /일치하지/);
  assert.throws(() => parseDepartures({...result(), meaning: "validated-fault"}, "motor-1", "R", "first-30"), /일치하지/);
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

test("score dots are unconnected and no missing score creates fabricated point", () => {
  const data = parseDepartures(result(), "motor-1", "R", "first-30");
  assert.equal(scoreDots(data).length, 1);
  assert.equal(scoreDots({...data, score: []}).length, 0);
});
