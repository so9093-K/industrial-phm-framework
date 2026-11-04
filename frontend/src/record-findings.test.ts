import assert from "node:assert/strict";
import {test} from "node:test";
import {findingLinks, findingText, parseRecordFindings, unjudgedText} from "./record-findings.ts";

const body = () => ({
  schema_version: 1, asset_id: "comp", meaning: "departures-from-the-first-30-percent-not-fault-diagnosis",
  baseline: {from: "2020-10-21T15:00:22Z", to: "2020-10-23T17:24:04Z"},
  record: {from: "2020-10-21T15:00:22Z", to: "2020-10-28T14:59:22Z"}, bucket_seconds: 604.8,
  signals: [{channel: "T상전류", label: "T상전류", unit: "A", state: "scored"}, {channel: "R상전류", label: "R상전류", unit: "A", state: "scored"},
    {channel: "압력", label: "압력", unit: "bar", state: "constant", held: 6, later: {low: 0, high: 6.2}},
    {channel: "유량", label: "유량", unit: null, state: "short-baseline"}],
  judged: 2, unchecked: 0, interval_count: 9,
  intervals: [{start: "2020-10-24T07:10:33Z", end: "2020-10-25T23:19:26Z", channel: "T상전류", label: "T상전류", unit: "A",
    direction: "down", value: 0, usual: {low: 46.196, high: 78.4}, within: ["R상전류", "S상전류", "온도"]}],
});

test("what the whole record held reads as when, how long, against which range, and what else moved", () => {
  const found = parseRecordFindings(body(), "comp");
  assert.deepEqual(found.record, body().record);
  assert.equal(found.count, 9);
  const told = findingText(found.intervals[0], found.bucketSeconds);
  assert.equal(told.when, "10. 24. 16:10 ~ 10. 26. 08:19 (약 1일 16시간)");
  assert.equal(told.what, "T상전류 · 기록 처음 30%의 평소 범위(46.2~78.4 A)보다 낮았습니다 · 10분 평균으로 가장 낮을 때 0 A"
    + " · 같은 구간 안에서 평소 범위를 벗어난 다른 신호: R상전류, S상전류, 온도");
  // Signals not judged say why, never "no change"; a held baseline also says what came after.
  assert.deepEqual(found.signals.filter((row) => row.state !== "scored").map(unjudgedText), [
    "압력(기록 처음 30% 동안 값이 일정해 벗어난 정도를 계산할 수 없음 · 처음 30%는 6 bar, 그 뒤 0~6.2 bar)",
    "유량(기록 처음 30%의 값이 너무 적어 평소 범위를 정하지 못함)"]);
  // The judged count must match the signals, and intervals need a judged signal.
  assert.throws(() => parseRecordFindings({...body(), judged: 3}, "comp"));
  assert.throws(() => parseRecordFindings({...body(), judged: 0, signals: body().signals.slice(2)}, "comp"));
  const links = findingLinks("comp", found.intervals[0], found.baseline, found.bucketSeconds);
  assert.match(links.signal!, /tab=signals.*monitor_range=window/);
  assert.match(links.compare!, /method=compare.*compare_origin=departure/);
  assert.throws(() => parseRecordFindings({...body(), meaning: "fault"}, "comp"));
  assert.throws(() => parseRecordFindings({...body(), interval_count: 0}, "comp"));
  const reversed = body(); reversed.intervals[0].usual = {low: 80, high: 40};
  assert.throws(() => parseRecordFindings(reversed, "comp"));
});
