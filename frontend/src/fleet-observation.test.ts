import assert from "node:assert/strict";
import {test} from "node:test";
import {latestEpisode, parseGroup, positionAt, sharedSpan, visibleSeries} from "./fleet-observation.ts";

const hour = 3600_000;
const phases = parseGroup({label: "상전압", unit: "V", axis: "time", focus: "r", bucket_seconds: 3600, period_seconds: null,
  record: {from: "2020-10-04T00:00:00Z", to: "2020-10-04T03:00:00Z"},
  series: ["R", "S"].map(name => ({key: name.toLowerCase(), label: name + "상전압", short: name + "상",
    trace: [["2020-10-04T00:00:00Z", 220], ["2020-10-04T01:00:00Z", 221], ["2020-10-04T02:00:00Z", 226]], trace_join: [false, true, true]}))})!;

test("a replay draws only the time buckets that have fully passed", () => {
  const start = Date.parse("2020-10-04T00:00:00Z");
  // 02:30에는 02:00–03:00 구간 평균이 아직 정해지지 않았다.
  assert.deepEqual(visibleSeries(phases, start + 2.5 * hour)[0].points.map(point => point.value), [220, 221]);
  assert.deepEqual(visibleSeries(phases, start + 3 * hour)[1].points.map(point => point.value), [220, 221, 226]);
});

test("the replay position is a share of each record; acquisitions stay whole numbers", () => {
  assert.equal(positionAt(phases, 0.5), Date.parse("2020-10-04T01:30:00Z"));
  const bearing = parseGroup({label: "진동 RMS", unit: "g", axis: "acquisition", focus: "v", bucket_seconds: null, period_seconds: 60,
    record: {from: 1, to: 123}, series: [{key: "v", label: "수직 진동 RMS", short: "수직", trace: [[1, 0.5]], trace_join: [false]}]})!;
  assert.equal(positionAt(bearing, 0.5), 62);
  assert.equal(positionAt(bearing, 0), 1);
});

test("the latest episode joins changes that overlap through a chain", () => {
  // 공기압축기 1306: R 00:19–22:31, S 00:19–08:19, T 18:05–21:38 → 세 상이 한 시기.
  const change = (key: string, from: number, to: number) => ({key, channel: key, label: key, from, to, up: true, before: null, after: null});
  const found = latestEpisode([change("early", -50, -40), change("r", 0, 22), change("s", 0, 8), change("t", 18, 21)]);
  assert.deepEqual(found.map(row => row.key).sort(), ["r", "s", "t"]);
  assert.deepEqual(latestEpisode([]), []);
});

test("a group without series or with a malformed trace is not drawn", () => {
  assert.equal(parseGroup(null), null);
  assert.throws(() => parseGroup({label: "x", unit: null, axis: "time", focus: "x", record: {from: "2020-10-04T00:00:00Z", to: "2020-10-04T01:00:00Z"},
    series: [{key: "x", label: "x", short: "x", trace: [["2020-10-04T00:00:00Z", 1]], trace_join: []}]}));
});

test("records share one axis only when they can be compared on it", () => {
  const group = (axis: "time" | "acquisition", from: number, to: number) => ({...phases, axis, record: {from, to}});
  // 베어링 수명시험: 모두 1번째 측정부터 세므로 123회와 491회도 같은 축(시험 시작 후 경과)에 놓는다.
  assert.deepEqual(sharedSpan([group("acquisition", 1, 123), group("acquisition", 1, 491)]), {from: 1, to: 491});
  // 서로 다른 시기의 현장 기록(9~10월, 10~11월)은 각자의 축을 쓴다.
  const day = 86_400_000;
  assert.equal(sharedSpan([group("time", 0, 37 * day), group("time", 34 * day, 67 * day)]), null);
  assert.deepEqual(sharedSpan([group("time", 0, 37 * day), group("time", 2 * day, 36 * day)]), {from: 0, to: 37 * day});
  assert.equal(sharedSpan([group("acquisition", 1, 123), group("acquisition", 1, 2538)]), null);
});
