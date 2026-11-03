import assert from "node:assert/strict";
import {test} from "node:test";
import type {HistoryGroup} from "./history.ts";
import {
  MAX_SPAN_MS, atFinest, momentWindow, periodOrigin, periodParams, periodsBefore, pickFrom, snapInside, snapSpan, summarize, windowParams, zoomWindow,
} from "./signal-selection.ts";

const at = (minute: number) => Date.parse("2026-10-01T00:00:00Z") + minute * 60000;
const bucket = (minute: number, mean: number | null, usable: number, extra: Partial<{min: number; max: number; nulls: number; bad: number}> = {}) => ({
  channelId: "R", sourceId: "file", pointId: null, interpretationId: "i1",
  bucketStart: new Date(at(minute)).toISOString(), mean, minimum: extra.min ?? mean, maximum: extra.max ?? mean,
  usableCount: usable, nullCount: extra.nulls ?? 0, nonGoodCount: extra.bad ?? 0, conflictCount: 0,
  unit: "A", observedProperty: null,
});
const group = (buckets: ReturnType<typeof bucket>[]): HistoryGroup => ({
  key: "g", sourceId: "file", pointId: null, unit: "A", observedProperty: null, interpretationId: "i1", buckets,
});

test("a drag or tap snaps to whole chart buckets inside the read window", () => {
  const step = 60000;
  assert.deepEqual(snapSpan(at(2.5), at(2.5), at(0), at(10), step), {from: at(2), to: at(3)});
  assert.deepEqual(snapSpan(at(4.2), at(1.5), at(0), at(10), step), {from: at(1), to: at(5)});
  assert.deepEqual(snapSpan(at(-5), at(20), at(0), at(10), step), {from: at(0), to: at(10)});
});

test("after zooming a picked span keeps only the finer buckets inside it", () => {
  const origin = at(0) + 20000, step = 60000;
  assert.deepEqual(snapInside({from: at(2), to: at(6)}, origin, at(10), step), {from: at(2) + 20000, to: at(5) + 20000});
  assert.deepEqual(snapInside({from: at(2), to: at(2) + 30000}, origin, at(10), step), {from: at(1) + 20000, to: at(2) + 20000});
});

test("a bucket start parsed a millisecond early still belongs to its own bucket", () => {
  const step = 1439475, origin = at(0);
  const parsed = origin + 3 * step - 1;
  assert.deepEqual(snapSpan(parsed, parsed, origin, origin + 120 * step, step), {from: origin + 3 * step, to: origin + 4 * step});
  const early = {...bucket(0, 5, 1), bucketStart: new Date(parsed).toISOString()};
  assert.equal(summarize(group([early]), {from: origin + 3 * step, to: origin + 4 * step})?.mean, 5);
});

test("the span summary weights bucket means by usable values and never fills a gap", () => {
  const summary = summarize(group([bucket(0, 10, 1), bucket(1, 20, 3, {min: 5, max: 40}), bucket(2, null, 0, {nulls: 4, bad: 1})]),
    {from: at(0), to: at(3)});
  assert.equal(summary?.mean, 17.5);
  assert.deepEqual([summary?.minimum, summary?.maximum, summary?.usable, summary?.missing, summary?.nonGood], [5, 40, 4, 4, 1]);
  const empty = summarize(group([bucket(2, null, 0, {nulls: 2})]), {from: at(0), to: at(3)});
  assert.equal(empty?.mean, null);
  assert.equal(summarize(group([bucket(5, 1, 1)]), {from: at(0), to: at(3)}), null);
});

test("comparison and zoom only offer what the server reads: at most 31 days", () => {
  const span = {from: at(60), to: at(120)};
  assert.deepEqual(periodsBefore(span), {
    a: {from: new Date(at(0)).toISOString(), to: new Date(at(60)).toISOString()},
    b: {from: new Date(at(60)).toISOString(), to: new Date(at(120)).toISOString()},
  });
  assert.deepEqual(zoomWindow(span), {from: at(-15), to: at(150)});
  const long = {from: 0, to: MAX_SPAN_MS - 1};
  assert.deepEqual(zoomWindow(long), long);
  assert.equal(zoomWindow({from: 0, to: MAX_SPAN_MS + 1}), null);
  assert.equal(periodsBefore({from: 0, to: MAX_SPAN_MS + 1}), null);
});

test("a scatter point opens narrowly around its own moment", () => {
  const hour = 3600000;
  assert.deepEqual(momentWindow(at(600), 24 * hour), {from: at(600) - 1.2 * hour, to: at(600) + 1.2 * hour});
  assert.deepEqual(momentWindow(at(600), 10 * 60000), {from: at(600) - hour / 2, to: at(600) + hour / 2});
  assert.equal(momentWindow(0, 400 * 86400000).to - momentWindow(0, 400 * 86400000).from, MAX_SPAN_MS);
});

test("zoom stops once each bucket holds about one stored value", () => {
  assert.equal(atFinest([{usableCount: 1}, {usableCount: 0}, {usableCount: 2}]), true);
  assert.equal(atFinest([{usableCount: 4}, {usableCount: 3}]), false);
  assert.equal(atFinest([]), false);
});

test("handed-over periods name where they came from and a pick reads back", () => {
  const periods = periodsBefore({from: at(60), to: at(120)})!;
  const params = new URLSearchParams(periodParams(periods, "departure"));
  assert.equal(periodOrigin("?" + params), "departure");
  assert.equal(periodOrigin("?compare_origin=elsewhere"), null);
  const zoomed = new URLSearchParams(windowParams({from: at(0), to: at(10)}, {from: at(5), to: at(5)}));
  assert.equal(zoomed.get("monitor_range"), "window");
  assert.deepEqual(pickFrom(zoomed.get("monitor_pick")), {from: at(5), to: at(5)});
  assert.equal(pickFrom("2026-10-02T00:00:00Z~2026-10-01T00:00:00Z"), null);
  assert.equal(pickFrom(null), null);
});
