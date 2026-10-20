import assert from "node:assert/strict";
import {test} from "node:test";
import {elapsedText, measurementScale, sinceStart, xTicks} from "./time-axis.ts";

test("durations read as people say them", () => {
  assert.deepEqual([0, 45, 90, 1800, 4500, 7200, 93600, 2 * 86400].map(elapsedText),
    ["0초", "45초", "1분 30초", "30분", "1시간 15분", "2시간", "1일 2시간", "2일"]);
  assert.equal(sinceStart(76, 60), "기록 시작 후 1시간 15분");
});

test("a sequence with a recorded interval is drawn as time since its first measurement", () => {
  // XJTU-SY: measurements #1–#100, one per minute.
  const ticks = xTicks(1, 100, {kind: "elapsed", period: 60}, 5);
  assert.deepEqual(ticks.map((tick) => tick.label), ["0분", "20분", "40분", "1시간", "1시간 20분"]);
  assert.deepEqual(ticks.map((tick) => tick.value), [1, 21, 41, 61, 81]);
  assert.equal(ticks[0].x, 0);
  // The forecast continues on the same axis past the last measurement.
  assert.equal(xTicks(1, 130, {kind: "elapsed", period: 60}, 5).at(-1)!.label, "2시간");
  // Without an interval, the measurement number is all there is.
  assert.deepEqual(xTicks(1, 100, measurementScale(null), 5).map((tick) => tick.label), ["#20", "#40", "#60", "#80", "#100"]);
  assert.deepEqual(measurementScale(60), {kind: "elapsed", period: 60});
});

test("a record with timestamps is drawn on the Korean clock, naming the day when it changes", () => {
  const start = Date.parse("2026-10-15T15:00:00Z"); // 10. 16. 00:00 KST
  const ticks = xTicks(start, start + 2 * 86400_000, {kind: "clock"}, 5);
  assert.deepEqual(ticks.map((tick) => tick.label), ["10. 16.", "12:00", "10. 17.", "12:00", "10. 18."]);
  assert.deepEqual(xTicks(start, start + 7 * 86400_000, {kind: "clock"}, 4).map((tick) => tick.label),
    ["10. 16.", "10. 18.", "10. 20.", "10. 22."]);
  const hours = xTicks(start + 3600_000 * 9, start + 3600_000 * 21, {kind: "clock"}, 5);
  assert.deepEqual(hours.map((tick) => tick.label), ["10. 16. 09:00", "12:00", "15:00", "18:00", "21:00"]);
  // Wall times written without an offset keep their written clock.
  const naive = Date.parse("2026-10-15T08:00:00Z");
  assert.equal(xTicks(naive, naive + 6 * 3600_000, {kind: "clock", zone: "UTC"}, 3)[0].label, "10. 15. 08:00");
  assert.equal(xTicks(5, 5, {kind: "clock"}).length, 1);
});

test("short and zoomed-in records retain distinct tick labels", () => {
  const start = Date.parse("2026-10-16T00:00:05Z");
  const seconds = xTicks(start, start + 20_000, {kind: "clock"});
  assert.match(seconds[0].label, /09:00:05/);
  assert.equal(new Set(seconds.map(tick => tick.label)).size, seconds.length);
  const subsecond = xTicks(start, start + 500, {kind: "clock"});
  assert.equal(new Set(subsecond.map(tick => tick.label)).size, subsecond.length);
  const late = xTicks(86401, 86421, {kind: "elapsed", period: 1});
  assert.equal(new Set(late.map(tick => tick.label)).size, late.length);
  assert.match(late[1].label, /1일.*초/);
  const fast = xTicks(1, 6, measurementScale(0.1));
  assert.equal(new Set(fast.map(tick => tick.label)).size, fast.length);
  assert.deepEqual(xTicks(76, 76, measurementScale(60)), [{value: 76, x: 0, label: "1시간 15분"}]);
  assert.deepEqual(xTicks(1, 6, {kind: "order"}, 2).map(tick => tick.label), ["#1", "#6"]);
  assert.deepEqual(xTicks(34, 94, {kind: "order"}, 2).map(tick => tick.label), ["#34", "#94"]);
});

test("long records keep a bounded number of ticks and invalid intervals cannot be converted", () => {
  const start = Date.parse("2025-01-01T00:00:00Z");
  const year = xTicks(start, start + 730 * 86400_000, {kind: "clock"});
  assert.ok(year.length > 0 && year.length <= 6);
  assert.match(year[0].label, /202[567]/);
  for (const period of [0, -1, NaN, Infinity]) {
    assert.deepEqual(measurementScale(period), {kind: "order"});
    assert.deepEqual(xTicks(1, 100, {kind: "elapsed", period}), []);
  }
  assert.deepEqual(xTicks(NaN, 100, measurementScale(60)), []);
  // A sliced record keeps its original elapsed position; it never starts at zero again.
  assert.equal(xTicks(61, 100, measurementScale(60))[0].label, "1시간");
});
