import assert from "node:assert/strict";
import {test} from "node:test";
import {changeEnded, object, plainLabel, subject, topic} from "./change-story.ts";

test("a name takes the subject particle its last sound asks for", () => {
  assert.deepEqual(["T상전압", "주파수", "수직 진동 RMS", "전류 L", "채널 1", "채널 2", "온도 (입구)"].map(subject),
    ["T상전압이", "주파수가", "수직 진동 RMS가", "전류 L이", "채널 1이", "채널 2가", "온도 (입구)가"]);
  assert.deepEqual(["전류평균", "주파수"].map(object), ["전류평균을", "주파수를"]);
  assert.deepEqual(["마지막 측정값", "마지막 구간 평균", "전압"].map(topic), ["마지막 측정값은", "마지막 구간 평균은", "전압은"]);
});

test("a vibration feature keeps its calculation name in parentheses after the plain word", () => {
  assert.equal(plainLabel("수직 진동 초과 첨도", "feature.Vertical_vibration_signals.excess_kurtosis"), "수직 진동 충격성 (첨도)");
  assert.equal(plainLabel("R상전압", null), "R상전압");
});

test("a change that ended well before the record's end is told apart from one that reached it", () => {
  // 마지막 두 구간 안에서 끝났으면 기록 끝까지 이어진 변화다.
  assert.notEqual(changeEnded("2020-10-05T07:31:42+09:00", "2020-10-22T23:59:09+09:00", 3196.7), null);
  assert.equal(changeEnded("2020-10-22T22:30:00+09:00", "2020-10-22T23:59:09+09:00", 3196.7), null);
  assert.equal(changeEnded("2020-10-05T07:31:42+09:00", null, 60), null);
});
