import assert from "node:assert/strict";
import {test} from "node:test";
import {episodes, focusWindow, operationColumns, spanText, visiblePoints} from "./asset-timeline.ts";

test("changes that overlap in time form one episode, in start order", () => {
  // Bearing1_1: 첨도 69–78, RMS 72–123, 왜도 79–82 → 한 시기. 떨어진 변화는 따로.
  const found = episodes([{k: "rms", from: 72, to: 123}, {k: "kurt", from: 69, to: 78}, {k: "skew", from: 79, to: 82}, {k: "late", from: 130, to: 140}],
    item => item);
  assert.deepEqual(found.map(e => [e.from, e.to, e.members.map(m => m.k)]), [[69, 123, ["kurt", "rms", "skew"]], [130, 140, ["late"]]]);
});

test("the zoomed window keeps context on both sides but stays inside the record", () => {
  assert.deepEqual(focusWindow({from: 0, to: 1000}, {from: 500, to: 510}), {from: 480, to: 530});
  assert.deepEqual(focusWindow({from: 0, to: 1000}, {from: 5, to: 105}), {from: 0, to: 305});
});

test("operating-level counts become shares per bucket and empty buckets are left out", () => {
  const columns = operationColumns([{at: "2020-10-04T00:00:00Z", counts: [0, 3, 1, 0]}, {at: "2020-10-04T01:00:00Z", counts: [0, 0, 0, 0]}], 3600);
  assert.equal(columns.length, 1);
  assert.deepEqual(columns[0].shares, [0, 0.75, 0.25, 0]);
  assert.equal(columns[0].to - columns[0].from, 3600 * 1000);
});

test("zoomed points use the finer reading where it exists and the record elsewhere", () => {
  const lane = {points: [{x: 0, value: 1}, {x: 10, value: 2}, {x: 20, value: 3}, {x: 30, value: 4}], detail: [{x: 9, value: 5}, {x: 12, value: 6}]};
  assert.deepEqual(visiblePoints(lane, {from: 0, to: 25}, true).map(p => p.x), [0, 9, 12, 20]);
  assert.deepEqual(visiblePoints(lane, {from: 0, to: 25}, false).map(p => p.x), [0, 10, 20]);
});

test("history intervals show their actual dates and Korean time without repeating a same-day date",()=>{
  assert.equal(spanText(Date.parse("2020-10-04T09:19:00+09:00"),Date.parse("2020-10-05T07:31:00+09:00")),"10월 4일(일) 09:19 ~ 10월 5일(월) 07:31");
  assert.equal(spanText(Date.parse("2020-10-04T09:19:00+09:00"),Date.parse("2020-10-04T17:19:00+09:00")),"10월 4일(일) 09:19 ~ 17:19");
});
