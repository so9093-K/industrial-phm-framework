import assert from "node:assert/strict";
import {test} from "node:test";
import {changeEnded, lastNumber, toward, versusStart} from "./change-story.ts";

test("a change that ended well before the record's end is told apart from one that reached it", () => {
  // 마지막 두 구간 안에서 끝났으면 기록 끝까지 이어진 변화다.
  assert.notEqual(changeEnded("2020-10-05T07:31:42+09:00", "2020-10-22T23:59:09+09:00", 3196.7), null);
  assert.equal(changeEnded("2020-10-22T22:30:00+09:00", "2020-10-22T23:59:09+09:00", 3196.7), null);
  assert.equal(changeEnded("2020-10-05T07:31:42+09:00", null, 60), null);
});

test("a period name takes 으로 after a closed syllable and 로 after an open one or ㄹ", () => {
  assert.equal(toward("초기"), "초기로");
  assert.equal(toward("특이사항 구간"), "특이사항 구간으로");
  assert.equal(toward("기간 A"), "기간 A로");
  assert.equal(toward("직전 구간"), "직전 구간으로");
  assert.equal(toward("1번 측정"), "1번 측정으로");
  assert.equal(toward("레일"), "레일로");
});

test("a multiple reads with one decimal everywhere, like the monitor card", () => {
  // 서버가 '초기의 약 10.1배'라고 쓰는 값을 화면 일부가 '10배'로 줄이면 같은 값에 표기가 둘이 된다.
  assert.equal(versusStart(7.268, 0.716, "g"), "초기의 약 10.2배");
  assert.equal(versusStart(3.3, 0.716, "g"), "초기의 약 4.6배");
  const facts = {label: "수평 진동 RMS", unit: "g", direction: "up" as const, reference: 0.716, typical: 3.3};
  assert.deepEqual(lastNumber(facts, 7.268, "마지막 측정 · 123번째 측정"),
    {caption: "마지막 측정 · 123번째 측정", value: "7.27 g", note: "초기의 약 10.2배"});
});
