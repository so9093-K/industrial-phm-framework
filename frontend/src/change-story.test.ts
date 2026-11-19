import assert from "node:assert/strict";
import {test} from "node:test";
import {changeEnded, changeHeadline, changeNumbers, changeSentence, object, plainLabel, subject} from "./change-story.ts";

test("a name takes the subject particle its last sound asks for", () => {
  assert.deepEqual(["T상전압", "주파수", "수직 진동 RMS", "전류 L", "채널 1", "채널 2", "온도 (입구)"].map(subject),
    ["T상전압이", "주파수가", "수직 진동 RMS가", "전류 L이", "채널 1이", "채널 2가", "온도 (입구)가"]);
  assert.deepEqual(["전류평균", "주파수"].map(object), ["전류평균을", "주파수를"]);
});

test("a change reads as one sentence: what, from when for how long, against what", () => {
  const voltage = {label: "T상전압", unit: "V", direction: "down" as const, reference: 231, typical: 228, referenceSpread: 0.63};
  assert.equal(changeSentence(voltage, "2. 2. 08:18부터 약 1시간 21분 동안", "약 9.4 A 운전"),
    "T상전압이 2. 2. 08:18부터 약 1시간 21분 동안 같은 운전 수준(약 9.4 A 운전)의 기록 처음 30%보다 낮았습니다.");
  assert.equal(changeSentence({...voltage, direction: "up", kind: "level-change"}, "72번째 측정부터 마지막 측정까지"),
    "T상전압이 72번째 측정부터 마지막 측정까지 기록 처음 30%에 일정하던 값보다 높았습니다.");
});

test("both numbers say what they are, how steady the first was and how far the second moved", () => {
  assert.deepEqual(changeNumbers({label: "T상전압", unit: "V", direction: "down", reference: 231, typical: 228, referenceSpread: 0.63}), {
    before: {caption: "기록 처음 30%의 중앙값", value: "231 V", note: "이 기간의 변동 약 ±0.63 V"},
    after: {caption: "이 구간의 중앙값", value: "228 V", note: "처음보다 3 V 낮음"},
  });
  // A several-fold rise also says how many times; a start at zero has no ratio.
  assert.equal(changeNumbers({label: "RMS", unit: "g", direction: "up", reference: 0.623, typical: 2.3, referenceSpread: 0.0195})!.after.note,
    "처음보다 1.68 g 높음 · 약 3.69배");
  assert.deepEqual(changeNumbers({label: "전류", unit: null, direction: "up", kind: "level-change", reference: 0, typical: 193})!, {
    before: {caption: "기록 처음 30%의 중앙값", value: "0", note: "이 값이 그대로 유지됨"},
    after: {caption: "이 구간의 중앙값", value: "193", note: "처음보다 193 높음"},
  });
  assert.equal(changeNumbers({label: "전류", unit: "A", direction: "up", reference: null, typical: 3}), null);
});


test("the entry headline stays brief while keeping its comparison direction", () => {
  assert.equal(changeHeadline({label:"수직 진동 RMS",feature:"feature.Vertical_vibration_signals.rms",direction:"up"}),"수직 진동 크기 (RMS)가 비교 기준보다 높았습니다.");
  assert.equal(changeHeadline({label:"전류",direction:"up"}),"전류가 비교 기준보다 높았습니다.");
  assert.equal(changeHeadline({label:"온도",direction:"down",kind:"level-change"}),"온도가 일정하던 기준값보다 낮았습니다.");
});

test("a vibration feature reads in plain words first and keeps its calculation name in parentheses", () => {
  assert.equal(plainLabel("수직 진동 초과 첨도", "feature.Vertical_vibration_signals.excess_kurtosis"), "수직 진동 충격성 (첨도)");
  assert.equal(plainLabel("수직 진동 왜도", "feature.Vertical_vibration_signals.skewness"), "수직 진동 치우침 (왜도)");
  assert.equal(plainLabel("수평 진동 파고율", "feature.Horizontal_vibration_signals.crest_factor"), "수평 진동 피크 배율 (파고율)");
  // 전기 채널 이름은 그대로 둔다.
  assert.equal(plainLabel("R상전압", null), "R상전압");
  assert.equal(changeHeadline({label:"수직 진동 초과 첨도",feature:"feature.Vertical_vibration_signals.excess_kurtosis",direction:"up"}),
    "수직 진동 충격성 (첨도)가 비교 기준보다 높았습니다.");
});

test("a change that ended well before the record's end says when it ended; one that reached the end says nothing", () => {
  // 공기압축기 1306: 10월 5일 07:31에 끝났고 기록은 10월 22일까지 (구간 약 53분).
  assert.equal(changeEnded("2020-10-05T07:31:42+09:00", "2020-10-22T23:59:09+09:00", 3196.7),
    "변화 종료 10월 5일 07:31 · 기록 마지막 10월 22일 23:59");
  // 마지막 두 구간 안에서 끝났으면 기록 끝까지 이어진 변화다.
  assert.equal(changeEnded("2020-10-22T22:30:00+09:00", "2020-10-22T23:59:09+09:00", 3196.7), null);
  assert.equal(changeEnded("2020-10-05T07:31:42+09:00", null, 60), null);
});
