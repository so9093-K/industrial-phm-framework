import assert from "node:assert/strict";
import {test} from "node:test";
import {findingLinks, findingText, parseRecordFindings} from "./record-findings.ts";

const body = () => ({
  schema_version: 1, asset_id: "comp", meaning: "departures-from-the-first-30-percent-not-fault-diagnosis",
  baseline: {from: "2020-10-21T15:00:22Z", to: "2020-10-23T17:24:04Z"},
  record: {from: "2020-10-21T15:00:22Z", to: "2020-10-28T14:59:22Z"}, bucket_seconds: 604.8,
  checked: ["R상전류", "S상전류", "T상전류", "온도"], unchecked: 0, interval_count: 9,
  intervals: [{start: "2020-10-24T07:10:33Z", end: "2020-10-25T23:19:26Z", channel: "T상전류", label: "T상전류", unit: "A",
    direction: "down", value: 0, usual: {low: 46.196, high: 78.4}, with: ["R상전류", "S상전류", "온도"]}],
});

test("what the whole record held reads as when, how long, against which range, and what else moved", () => {
  const found = parseRecordFindings(body(), "comp");
  assert.equal(found.count, 9);
  const told = findingText(found.intervals[0], found.bucketSeconds);
  assert.equal(told.when, "10. 24. 16:10 ~ 10. 26. 08:19 (약 1일 16시간)");
  assert.equal(told.what, "T상전류 · 기록 처음 30%의 평소 범위(46.2~78.4 A)보다 낮았습니다 · 10분 평균으로 가장 낮을 때 0 A"
    + " · 같은 때 평소 범위를 벗어난 신호: R상전류, S상전류, 온도");
  const links = findingLinks("comp", found.intervals[0], found.baseline, found.bucketSeconds);
  assert.match(links.signal!, /tab=signals.*monitor_range=window/);
  assert.match(links.compare!, /method=compare.*compare_origin=departure/);
  assert.throws(() => parseRecordFindings({...body(), meaning: "fault"}, "comp"));
  assert.throws(() => parseRecordFindings({...body(), interval_count: 0}, "comp"));
  const reversed = body(); reversed.intervals[0].usual = {low: 80, high: 40};
  assert.throws(() => parseRecordFindings(reversed, "comp"));
});
