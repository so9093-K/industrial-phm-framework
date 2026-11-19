import assert from "node:assert/strict";
import {test} from "node:test";
import {afterChange, changeConclusion, changeEnded, changeNumbers, object, plainLabel, subject, topic} from "./change-story.ts";

test("a name takes the subject particle its last sound asks for", () => {
  assert.deepEqual(["T상전압", "주파수", "수직 진동 RMS", "전류 L", "채널 1", "채널 2", "온도 (입구)"].map(subject),
    ["T상전압이", "주파수가", "수직 진동 RMS가", "전류 L이", "채널 1이", "채널 2가", "온도 (입구)가"]);
  assert.deepEqual(["전류평균", "주파수"].map(object), ["전류평균을", "주파수를"]);
  assert.deepEqual(["마지막 측정값", "마지막 구간 평균", "전압"].map(topic), ["마지막 측정값은", "마지막 구간 평균은", "전압은"]);
});

test("the conclusion tells two different changes apart: still there at the last measurement, or when, how long and how much", () => {
  // Bearing1_1: 마지막 측정까지 이어졌고, 마지막 값이 처음의 몇 배인지가 먼저 볼 이유다.
  const bearing = {label: "수직 진동 RMS", feature: "feature.Vertical_vibration_signals.rms", unit: "g", direction: "up" as const,
    reference: 0.62305, typical: 2.3019};
  assert.equal(changeConclusion(bearing, {latest: {caption: "마지막 측정값", value: 5.7835}}),
    "수직 진동 크기 (RMS)가 마지막 측정까지 처음보다 높았고, 마지막 측정값은 처음의 약 9.28배입니다.");
  // 공기압축기 1306: 끝난 변화는 언제부터 얼마 동안, 처음보다 얼마나(차이와 비율) 높았는지 말한다.
  const voltage = {label: "R상전압", unit: "V", direction: "up" as const, reference: 221.82, typical: 226.08};
  assert.equal(changeConclusion(voltage, {span: "2020년 10월 4일(일) 09:19부터 약 22시간 12분 동안"}),
    "R상전압이 2020년 10월 4일(일) 09:19부터 약 22시간 12분 동안 처음보다 4.26 V(1.9%) 높았습니다.");
  assert.equal(changeConclusion(voltage, {latest: {caption: "마지막 구간 평균", value: 216}}),
    "R상전압이 마지막 측정까지 처음보다 높았고, 마지막 구간 평균은 처음보다 5.82 V(2.6%) 낮습니다.");
  // 크게 줄어든 값은 처음의 몇 %, 온도처럼 0이 기준이 아닌 단위는 차이만 말한다.
  assert.equal(changeConclusion({label: "전류", unit: "A", direction: "down", reference: 60, typical: 12}, {span: "3일 동안"}),
    "전류가 3일 동안 처음의 약 20%였습니다.");
  assert.equal(changeConclusion({label: "온도", unit: "°C", direction: "up", reference: 40, typical: 65}, {latest: {caption: "마지막 구간 평균", value: 65}}),
    "온도가 마지막 측정까지 처음보다 높았고, 마지막 구간 평균은 처음보다 25 °C 높습니다.");
  assert.equal(changeConclusion({label: "온도", unit: "°C", direction: "down", kind: "level-change", reference: null, typical: null}, {latest: null}),
    "온도가 마지막 측정까지 처음 일정하던 값보다 낮았습니다.");
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


test("a vibration feature reads in plain words first and keeps its calculation name in parentheses", () => {
  assert.equal(plainLabel("수직 진동 초과 첨도", "feature.Vertical_vibration_signals.excess_kurtosis"), "수직 진동 충격성 (첨도)");
  assert.equal(plainLabel("수직 진동 왜도", "feature.Vertical_vibration_signals.skewness"), "수직 진동 치우침 (왜도)");
  assert.equal(plainLabel("수평 진동 파고율", "feature.Horizontal_vibration_signals.crest_factor"), "수평 진동 피크 배율 (파고율)");
  // 전기 채널 이름은 그대로 둔다.
  assert.equal(plainLabel("R상전압", null), "R상전압");
  assert.equal(changeConclusion({label: "수직 진동 초과 첨도", feature: "feature.Vertical_vibration_signals.excess_kurtosis", unit: null,
    direction: "up", reference: 0.1, typical: 0.5}, {latest: null}), "수직 진동 충격성 (첨도)가 마지막 측정까지 처음보다 높았습니다.");
});

test("a change that ended well before the record's end says when it ended; one that reached the end says nothing", () => {
  // 공기압축기 1306: 10월 5일 07:31에 끝났고 기록은 10월 22일까지 (구간 약 53분).
  assert.equal(changeEnded("2020-10-05T07:31:42+09:00", "2020-10-22T23:59:09+09:00", 3196.7),
    "변화 종료 10월 5일 07:31 · 기록 마지막 10월 22일 23:59");
  // 마지막 두 구간 안에서 끝났으면 기록 끝까지 이어진 변화다.
  assert.equal(changeEnded("2020-10-22T22:30:00+09:00", "2020-10-22T23:59:09+09:00", 3196.7), null);
  assert.equal(changeEnded("2020-10-05T07:31:42+09:00", null, 60), null);
});

test("after a change that ended, the record says how often the same condition came back and whether it was inside the first range", () => {
  // 공기압축기 1306: 종료 뒤 구간 115개 중 약 11 A 운전은 4개뿐이라 '돌아왔다'고 볼 근거가 적다.
  const rows = [{at: "2020-10-05T06:00:00+09:00", mean: 220, judged: 226},
    ...Array.from({length: 115}, (_, i) => ({at: new Date(Date.parse("2020-10-05T08:00:00+09:00") + i * 3600_000).toISOString(),
      mean: 221, judged: [3, 40, 77, 110].includes(i) ? 222 : null}))];
  const usual = {low: 218.46, high: 225.18};
  assert.equal(afterChange("2020-10-05T07:31:42+09:00", usual, rows, "level", "약 11 A 운전"),
    "변화 구간 끝 10월 5일 07:31 · 이후 구간 115개 중 약 11 A 운전 4개, 모두 처음 범위 안");
  assert.equal(afterChange("2020-10-05T07:31:42+09:00", usual, rows.map(row => ({...row, judged: null})), "level", "약 11 A 운전"),
    "변화 구간 끝 10월 5일 07:31 · 이후 구간 115개 중 약 11 A 운전 없음");
  assert.equal(afterChange("2020-10-05T07:31:42+09:00", {low: 220.5, high: 230}, rows, "all", null),
    "변화 구간 끝 10월 5일 07:31 · 이후 구간 115개, 모두 처음 범위 안");
  assert.equal(afterChange("2020-10-05T07:31:42+09:00", {low: 223, high: 230}, rows, "all", null),
    "변화 구간 끝 10월 5일 07:31 · 이후 구간 115개, 모두 처음 범위 밖");
  assert.equal(afterChange("2020-10-23T00:00:00+09:00", usual, rows, "all", null), null);
});
