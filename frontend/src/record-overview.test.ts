import assert from "node:assert/strict";
import {test} from "node:test";
import {overviewChart, overviewKind, parseOverview} from "./record-overview.ts";

const at = (minute: number) => new Date(Date.UTC(2026, 10, 1, 0, minute)).toISOString();

test("the whole-record series is read as it was sent and refuses broken rows", () => {
  assert.deepEqual(parseOverview([[at(0), 2, 1, 3, null, false]]), [{at: at(0), mean: 2, low: 1, high: 3, judged: null, join: false}]);
  assert.deepEqual(parseOverview(undefined), []);
  assert.throws(() => parseOverview([[at(0), 5, 1, 3, null, false]]));
  assert.throws(() => parseOverview([[at(0), 2, 1, 3, null]]));
  assert.equal(overviewKind("level"), "level");
  assert.equal(overviewKind("anything"), "all");
});

test("the chart draws the judged values over the record and marks where the change sits", () => {
  // 0~9분 정지(0), 10~19분 운전(10). 운전 중의 값만 판단했다.
  const rows = Array.from({length: 20}, (_, i) => ({at: at(i), mean: i < 10 ? 0 : 10, low: i < 10 ? 0 : 9, high: i < 10 ? 0 : 11,
    judged: i < 10 ? null : 10, join: i > 0}));
  const chart = overviewChart(rows, "running", {baseline: {from: at(0), to: at(6)}, change: {from: at(15), to: at(15)},
    window: {from: at(12), to: at(18)}, record: {from: at(0), to: at(19)}}, 1900, 100)!;
  assert.ok(chart.all && chart.all.startsWith("M0.0,"));
  assert.equal(chart.judged.split("M").length - 1, 1);
  assert.equal(chart.dots.length, 0);
  assert.equal(chart.bands.change.width, 3);
  assert.deepEqual(chart.bands.baseline, {x: 0, width: 600});
  assert.equal(chart.ranges.length, 20);
});

test("judged values with nothing next to them stay visible as dots, and one series needs no grey line", () => {
  const rows = [0, 5, 10].map((minute, i) => ({at: at(minute), mean: i, low: i, high: i, judged: i === 1 ? 1 : null, join: false}));
  const level = overviewChart(rows, "level", {baseline: null, change: {from: at(5), to: at(6)}, window: null, record: null})!;
  assert.equal(level.dots.length, 1);
  const all = overviewChart(rows, "all", {baseline: null, change: {from: at(5), to: at(6)}, window: null, record: null})!;
  assert.equal(all.all, null);
  assert.equal(all.dots.length, 3);
  assert.equal(overviewChart(rows.slice(0, 1), "all", {baseline: null, change: {from: at(0), to: at(1)}, window: null, record: null}), null);
});
