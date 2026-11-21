import test from "node:test";
import assert from "node:assert/strict";
import {crossedSince, investigatedChange, limitSuggestions, nearestAt, outlookScale, outlookWindow, reachAt, reachSummary} from "./outlook-view.ts";

const history = Array.from({length: 100}, (_, i) => ({x: i + 1, value: 1 + i / 100}));
const future = Array.from({length: 10}, (_, i) => ({x: 101 + i, estimate: 2, lower: 1.8, upper: 2.2}));

test("the outlook starts early enough to show the change the investigation came from", () => {
  assert.deepEqual(outlookWindow(history, future, null), {from: 80, to: 110});
  const window = outlookWindow(history, future, {from: 40, to: 60});
  assert.ok(window.from < 40 && window.from >= 1);
  assert.equal(window.to, 110);
});

test("a limit far beyond the measured values is named, not drawn", () => {
  const near = outlookScale([1, 2], {median: 1, low: .9, high: 1.1}, {management: 2.5, end: 50});
  assert.equal(near.high, 2.5);
  assert.deepEqual(near.outside, {management: false, end: true});
  assert.equal(near.low, .9);
});

test("a reach sits where the forecast meets the limit, or at the earliest possible point", () => {
  assert.deepEqual(reachAt({state: "expected", expected: 3600, earliest: 1800, latest: 7200}, 1000, "time"), {x: 1000 + 3_600_000, sure: true});
  assert.deepEqual(reachAt({state: "possible", expected: null, earliest: 5, latest: 9}, 123, "acquisition"), {x: 128, sure: false});
  assert.deepEqual(reachAt({state: "already", expected: null, earliest: null, latest: null}, 123, "acquisition"), {x: 123, sure: true, already: true});
  assert.equal(reachAt({state: "beyond", expected: null, earliest: null, latest: null}, 123, "acquisition"), null);
});

test("only the investigated change of this very signal is carried over", () => {
  const search = "summary_change=" + encodeURIComponent(JSON.stringify(["vibration", "feature.v.rms", 72, 123]));
  assert.deepEqual(investigatedChange(search, "vibration", "feature.v.rms"), {from: 72, to: 123});
  assert.equal(investigatedChange(search, "vibration", "feature.v.kurtosis"), null);
  assert.equal(investigatedChange(search, "history", "feature.v.rms"), null);
  assert.equal(investigatedChange("summary_change=%5Bbroken", "vibration", "feature.v.rms"), null);
});

test("reading a point picks the nearest measurement or forecast", () => {
  assert.equal(nearestAt(history, future, 50.2)?.kind, "measured");
  assert.deepEqual(nearestAt(history, future, 104.6), {kind: "forecast", point: future[4]});
});

test("limits to pick from: the early range, and the supply tolerance for a 220 V phase voltage", () => {
  const voltage = limitSuggestions("V", {median: 218.4, low: 211.2, high: 225.6}, "R상전압");
  assert.deepEqual(voltage.map(row => [row.label, row.value, row.direction]), [
    ["공급 전압 상한 233 V", 233, "upper"], ["공급 전압 하한 207 V", 207, "lower"],
    ["처음 범위 상단 226 V", 226, "upper"], ["처음 범위 하단 211 V", 211, "lower"],
  ]);
  assert.equal(limitSuggestions("V", {median: 380, low: 370, high: 390}, "R상선간전압").some(row => row.label.startsWith("공급")), false);
  assert.deepEqual(limitSuggestions("g", {median: .6, low: .55, high: .65}, "수직 진동 RMS").map(row => row.value), [.65, .55]);
  assert.deepEqual(limitSuggestions(null, null, "x"), []);
});

test("an exceeded limit is told from the measurements: since when it has stayed beyond", () => {
  const points = [.6, .62, .7, .65, .8, 1.2, 2.4].map((value, i) => ({x: i + 1, value}));
  assert.equal(crossedSince(points, .691, "upper"), 5);
  assert.equal(crossedSince(points, 3, "upper"), null);
  assert.equal(crossedSince(points, .61, "lower"), null);
});

test("the margin reads as one short headline and one line of where it comes from", () => {
  const place = (x: number) => x + "번째";
  assert.deepEqual(reachSummary({state: "already", expected: null, earliest: null, latest: null}, "acquisition", 60, place, 123, 73),
    {headline: "이미 넘음", detail: "73번째부터 이어서 넘음"});
  assert.deepEqual(reachSummary({state: "possible", expected: null, earliest: 10.6 * 86400, latest: null}, "time", null, x => String(x), 0, null),
    {headline: "빠르면 약 10.6일 뒤", detail: "예측 범위에서만 닿음 · " + 10.6 * 86400 * 1000});
  assert.deepEqual(reachSummary({state: "expected", expected: 5, earliest: 3, latest: 9}, "acquisition", null, place, 123, null),
    {headline: "추가 측정 5회 뒤", detail: "예측선 도달 · 128번째"});
  assert.equal(reachSummary({state: "expected", expected: 30, earliest: 3, latest: 9}, "acquisition", 60, place, 123, null).headline, "약 30분 뒤");
  assert.equal(reachSummary({state: "beyond", expected: null, earliest: null, latest: null}, "time", null, place, 0, null).headline, "계산한 범위 안에서 닿지 않음");
});
