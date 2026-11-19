import assert from "node:assert/strict";
import {test} from "node:test";
import {rangeEvidence, relatedEvidence, spectrumEvidence} from "./change-evidence.ts";

test("the range evidence says how many of the change's values left the first 30%'s range, with the comparison's own numbers", () => {
  assert.equal(rangeEvidence({usable: 52, outside: 52, low: 0.5684, high: 0.6453, unit: "g", condition: null}),
    "변화 구간 52회 모두 기록 처음 30% 값의 90%가 있던 범위(0.568~0.645 g) 밖");
  // 두 기간 비교 화면과 같은 비율 표기(소수 한 자리)를 쓴다.
  assert.equal(rangeEvidence({usable: 591, outside: 572, percent: 96.785, low: 219.4, high: 224.2, unit: "V", condition: "약 11 A 운전"}),
    "약 11 A 운전 중 값끼리 · 변화 구간 591회 중 572회(96.8%)가 기록 처음 30% 값의 90%가 있던 범위(219~224 V) 밖");
  assert.equal(rangeEvidence({usable: 52, outside: 30, low: 1, high: 2, unit: "g", condition: null}),
    "변화 구간 52회 중 30회(58%)가 기록 처음 30% 값의 90%가 있던 범위(1~2 g) 밖");
  assert.equal(rangeEvidence({usable: 10, outside: null, low: 1, high: 2, unit: null, condition: null}), null);
});

test("what changed with it names one or two signals with their before and after values", () => {
  assert.equal(relatedEvidence([{label: "수평 진동 크기 (RMS)", reference: 0.7162, current: 3.2269, unit: "g"},
    {label: "수직 진동 피크-피크", reference: 6.241, current: 18.945, unit: "g"}, {label: "셋째", reference: 1, current: 2, unit: null}]),
  "수평 진동 크기 (RMS) 0.716 → 3.23 g, 수직 진동 피크-피크 6.24 → 18.9 g");
  assert.equal(relatedEvidence([]), null);
});

test("the frequency evidence names the band whose share grew most, else the energy ratio", () => {
  const band = (from: number, to: number, a: number, b: number) => ({from, to, a, b});
  assert.equal(spectrumEvidence([
    {label: "수평 진동", ratio: 27.3, shares: [band(0, 793.8, 0.6, 0.2), band(800, 1593.8, 0.175, 0.63)]},
    {label: "수직 진동", ratio: 20.1, shares: [band(800, 1593.8, 0.34, 0.599)]}]),
  "수평 진동 800~1,594 Hz 대역의 에너지 비중 18% → 63%");
  assert.equal(spectrumEvidence([{label: "수평 진동", ratio: 2.5, shares: [band(0, 800, 0.5, 0.52)]}]),
    "수평 진동 전체 에너지 기록 처음의 2.5배 · 비중이 10%p 이상 커진 대역 없음");
});
