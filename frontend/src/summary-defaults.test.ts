import assert from "node:assert/strict";
import {test} from "node:test";
import {relationPair, summarySignal} from "./summary-defaults.ts";
import {suggestedHorizon} from "./projections.ts";
import type {FoundInterval, RecordFindings} from "./record-findings.ts";
import type {RecordContext} from "./record-context.ts";

const record = {from: "2020-09-15T15:00:00Z", to: "2020-11-15T15:00:00Z"};
const context = (key: string, source = "plc"): RecordContext =>
  ({key, sourceId: source, pointId: "motor", interpretationId: key + "-meaning", record});
const change = (channel: string, label: string, extra: Partial<FoundInterval> = {}): FoundInterval => ({
  start: "2020-10-04T00:00:00Z", end: "2020-10-04T22:00:00Z", channel, label, unit: "V", direction: "up", value: 226,
  usual: {low: 220, high: 224}, within: [], reason: "sustained", reference: 222, typical: 226, related: [],
  baseline: {from: record.from, to: "2020-10-03T15:00:00Z"}, bucketSeconds: 3180, context: context(channel), ...extra,
});
const findings = (intervals: FoundInterval[], withCurrent = true): RecordFindings => ({
  assetId: "1306", baseline: null, record, bucketSeconds: 3180, judged: 3, unchecked: 0, count: intervals.length, intervals,
  signals: [
    {channel: "전류평균", label: "전류평균", unit: "A", state: "scored", held: null, later: null, context: context("전류평균")},
    {channel: "R상전압", label: "R상전압", unit: "V", state: "scored", held: null, later: null, context: context("R상전압")},
    {channel: "R상선간전압", label: "R상선간전압", unit: "V", state: "copied", held: null, later: null, context: context("R상선간전압")},
  ],
  operation: withCurrent ? [{key: "전류평균", label: "전류평균", unit: "A", stoppedBelow: 1, bucketSeconds: 3180, excluded: 0,
    levels: [{low: 1, high: 26, typical: 10.6}, {low: 26, high: 46, typical: 31.4}, {low: 46, high: null, typical: 61.9}],
    baseline: null, shares: {record: null, baseline: null, after: null}, timeline: []}] : [],
});
const ids = ["R상선간전압", "R상무효전력", "R상전압", "전류평균"];

test("a screen opens on the change the summary leads with, else on the current the levels come from", () => {
  const voltage = change("R상전압", "R상전압", {band: 1});
  assert.deepEqual(summarySignal(findings([voltage]), ids), {channel: "R상전압", context: context("R상전압")});
  assert.equal(summarySignal(findings([]), ids)?.channel, "전류평균");
  // A signal the screen does not offer is passed over, and nothing is guessed without either.
  assert.equal(summarySignal(findings([voltage]), ["전류평균", "R상선간전압"])?.channel, "전류평균");
  assert.equal(summarySignal(findings([], false), ids), null);
});

test("the relation screen shows the summary's change against the load, over its own reference and change", () => {
  const pair = relationPair(findings([change("R상전압", "R상전압", {band: 1})]), ids)!;
  assert.equal(pair.x, "전류평균");
  assert.equal(pair.y, "R상전압");
  assert.deepEqual(pair.focus, {source: "plc", point: "motor", interpretation: "전류평균-meaning"});
  assert.deepEqual(pair.periods, {a: {from: record.from, to: "2020-10-03T15:00:00Z"},
    b: {from: "2020-10-04T00:00:00.000Z", to: "2020-10-04T22:00:00.000Z"}});
  assert.equal(pair.note, "상태 요약의 첫 변화를 기준 전류와 함께 봅니다. 가로축 전류평균, 세로축 R상전압 · 약 11 A 운전 중 변화."
    + " 기간 A는 변화를 판단한 기록 처음 30%, 기간 B는 변화 구간입니다.");
});

test("without a current beside it, the change is paired with what moved with it", () => {
  const related = [{channel: "R상전류", label: "R상전류", unit: "A", reference: 60, current: 60, state: "within" as const},
    {channel: "R상무효전력", label: "R상무효전력", unit: "var", reference: 10, current: 14, state: "higher" as const}];
  const elsewhere = change("R상전압", "R상전압", {context: context("R상전압", "meter"), related});
  const pair = relationPair(findings([elsewhere]), ids)!;
  assert.deepEqual([pair.x, pair.y], ["R상전압", "R상무효전력"]);
  assert.match(pair.note, /같은 구간에 함께 달라진 신호와 함께 봅니다/);
  // A reference longer than one comparison may be leaves the periods to the screen's own default.
  const long = change("R상전압", "R상전압", {baseline: {from: "2020-01-01T00:00:00Z", to: "2020-03-01T00:00:00Z"}});
  assert.equal(relationPair(findings([long]), ids)!.periods, null);
  // No change: the current with a judged signal at its place; nothing without a current.
  const quiet = relationPair(findings([]), ids)!;
  assert.deepEqual([quiet.x, quiet.y, quiet.periods], ["전류평균", "R상전압", null]);
  assert.equal(relationPair(findings([], false), ids), null);
});

test("a forecast opens reaching at most a quarter of its record, within what the record supports", () => {
  const all = {"1h": null, "24h": null, "7d": null, "30d": null};
  const day = 86400;
  assert.equal(suggestedHorizon(all, 61 * day), "7d");
  assert.equal(suggestedHorizon(all, 130 * day), "30d");
  assert.equal(suggestedHorizon({...all, "30d": "short-history", "7d": "short-history"}, 130 * day), "24h");
  assert.equal(suggestedHorizon(all, 2 * day), "1h");
  // Too short for a quarter to reach an hour: the shortest supported; nothing supported, nothing suggested.
  assert.equal(suggestedHorizon({...all, "24h": "short-history", "7d": "short-history", "30d": "short-history"}, 3 * 3600), "1h");
  assert.equal(suggestedHorizon({"1h": "few-points", "24h": "few-points", "7d": "few-points", "30d": "few-points"}, day), null);
});
