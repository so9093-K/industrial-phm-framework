import assert from "node:assert/strict";
import {test} from "node:test";
import {
  coefficientGap, formulaLink, modelMessage, modelOnset, outlookMessage, periodMessage, periodOnset, relationMessage, shiftedBand,
  spectrumMessage, tie, times,
} from "./analysis-messages.ts";
import {thresholdRatios, type Interval, type TrendPoint} from "./model-trend.ts";

const place = (n: number) => n + "번째 측정";

// Numbers below are what the screens computed for the XJTU-SY Bearing1_1 replay, #1–75 against #76–100.
test("a period whose every value left the usual range says so before the medians", () => {
  const facts = {unit: "g", a: {usable: 75, median: 0.7657, low: 0.6024, high: 0.8630}, b: {usable: 25, median: 2.7954},
    outsideCount: 25, outsidePercent: 100, medianChangePercent: 265.1, onset: {first: 76, stayed: true}};
  const message = periodMessage(facts, place)!;
  assert.equal(message.headline,
    "기간 B의 측정 25회가 모두 기간 A의 평소 범위(0.602~0.863 g)를 벗어났습니다. 중앙값은 0.766 → 2.8 g로 약 3.7배입니다.");
  assert.equal(message.meaning, "76번째 측정에서 처음 평소 범위를 벗어났고 그 뒤로 계속 벗어나 있습니다.");
  assert.match(message.certainty!, /수준 자체가 달라졌습니다/);
});

test("a few values outside the usual range read as possibly brief, a tenth or less as no clear change", () => {
  const base = {unit: null, a: {usable: 40, median: 10, low: 8, high: 12}, b: {usable: 40, median: 10.5},
    medianChangePercent: 5, onset: null};
  const some = periodMessage({...base, outsideCount: 8, outsidePercent: 20}, place)!;
  assert.match(some.headline, /일부\(20%, 8회\)만/);
  assert.match(some.certainty!, /잠깐의 변화일 수 있습니다/);
  assert.doesNotMatch(some.headline, /배입니다/);
  const none = periodMessage({...base, outsideCount: 2, outsidePercent: 5}, place)!;
  assert.match(none.headline, /대부분 기간 A의 평소 범위\(8~12\) 안/);
  assert.match(none.certainty!, /뚜렷한 변화로 보기 어렵습니다/);
  const few = periodMessage({...base, b: {usable: 3, median: 20}, outsideCount: 3, outsidePercent: 100}, place)!;
  assert.match(few.certainty!, /기간 B 3회/);
  assert.equal(periodMessage({...base, b: {usable: 0, median: null}, outsideCount: null, outsidePercent: null}, place), null);
});

test("the onset is the first value of B outside A's range, and whether it stayed out", () => {
  const points = [70, 75, 76, 77, 78].map((ordinal, i) => ({ordinal, value: [0.8, 0.9, 1.1, 0.85, 2][i]}));
  assert.deepEqual(periodOnset(points, {from: 76, to: 78}, 0.6, 0.86), {first: 76, stayed: false});
  assert.deepEqual(periodOnset(points, {from: 78, to: 78}, 0.6, 0.86), {first: 78, stayed: true});
  assert.equal(periodOnset(points, {from: 76, to: 77}, 0.6, 2), null);
});

test("a relation that vanished in B is told as a change, with the crest factor's formula and its drop", () => {
  const peak = "feature.Horizontal_vibration_signals.absolute_peak", crest = "feature.Horizontal_vibration_signals.crest_factor";
  const message = relationMessage(peak, crest, {pearson: 0.938, spearman: 0.923, pairs: 75},
    {pearson: -0.336, spearman: 0.141, pairs: 25}, {a: 8.45, b: 6.47})!;
  assert.equal(message.headline, "두 값의 관계가 달라졌습니다. 기간 A에서는 같은 방향으로 강하게 함께 움직였고(피어슨 0.94), "
    + "기간 B에서는 관계가 분명하지 않습니다(피어슨 -0.34 · 스피어먼 0.14).");
  assert.match(message.meaning!, /절대 피크를 RMS로 나눈 값/);
  assert.match(message.meaning!, /8.45 → 6.47로 낮아졌습니다. 가끔 튀는 진동보다 진동 전체가 커지는/);
  assert.match(message.certainty!, /기간 B에서는 피어슨과 스피어먼이 서로 다른 방향/);
});

test("an unchanged relation says so, and the gap test tells chance from change", () => {
  const x = "feature.H.rms", y = "feature.V.rms";
  const same = relationMessage(x, y, {pearson: 0.9, spearman: 0.88, pairs: 50}, {pearson: 0.85, spearman: 0.84, pairs: 50}, null)!;
  assert.match(same.headline, /두 기간 모두 두 값은 같은 방향으로 강하게 함께 움직입니다.*관계는 그대로입니다/);
  assert.equal(same.meaning, null);
  assert.match(same.certainty!, /우연 범위 안/);
  const few = relationMessage(x, y, {pearson: 0.9, spearman: 0.9, pairs: 6}, {pearson: 0.1, spearman: 0.1, pairs: 40}, null)!;
  assert.match(few.certainty!, /기간 A는 짝이 6개뿐/);
  assert.ok(coefficientGap({pearson: 0.938, spearman: null, pairs: 75}, {pearson: -0.336, spearman: null, pairs: 25})! > 8);
  assert.deepEqual(tie({pearson: 0.1, spearman: -0.2, pairs: 30}), {kind: "none"});
  assert.equal(tie({pearson: 0.9, spearman: 0.9, pairs: 2}), null);
});

test("only features computed from one another on the same channel are formula links", () => {
  assert.equal(formulaLink("feature.H.rms", "feature.H.standard_deviation"), "rms-std");
  assert.equal(formulaLink("feature.H.peak_to_peak", "feature.H.absolute_peak"), "peaks");
  assert.equal(formulaLink("feature.H.crest_factor", "feature.H.rms"), "crest-rms");
  assert.equal(formulaLink("feature.H.crest_factor", "feature.V.absolute_peak"), null);
  assert.equal(formulaLink("feature.H.rms", "feature.H.skewness"), null);
});

test("the spectrum says how much energy grew and where it went, and whether both directions agree", () => {
  const band = (from: number, a: number, b: number) => ({from, to: from + 793.75, a, b});
  const horizontal = {label: "수평 진동", ratio: 12.0, shares: [band(0, 0.03, 0.09), band(800, 0.14, 0.57), band(1600, 0.83, 0.34)]};
  const vertical = {label: "수직 진동", ratio: 8.6, shares: [band(0, 0.19, 0.21), band(800, 0.28, 0.57), band(1600, 0.53, 0.22)]};
  const message = spectrumMessage([horizontal, vertical], {a: 8, b: 8})!;
  assert.equal(message.headline,
    "기간 B의 수평 진동 에너지는 기간 A의 12배가 됐고, 800~1,594 Hz가 전체 에너지에서 차지하는 비중이 14% → 57%로 커졌습니다.");
  assert.match(message.certainty!, /수직 진동에서도 같은 대역 비중이 28% → 57%로 커져/);
  const flat = spectrumMessage([{label: "수평 진동", ratio: 1.1, shares: [band(0, 0.5, 0.52), band(800, 0.5, 0.48)]}], {a: 2, b: 2})!;
  assert.match(flat.headline, /기간 A와 비슷하고\(1.1배\), 주파수별 에너지 분포는 비슷합니다/);
  assert.match(flat.certainty!, /측정 2회만 비교해 우연일 수 있습니다/);
  assert.equal(shiftedBand([band(0, 0.5, 0.55)]), null);
  assert.equal(spectrumMessage([{label: "수평 진동", ratio: null, shares: []}], {a: 8, b: 8}), null);
});

function line(scores: [number, number][], intervals: Interval[]) {
  const points: TrendPoint[] = scores.map(([position, score]) => ({
    pointer: {position, runId: "r" + position, state: "analyzed", stepKey: "k" + position, changeSeq: position, reason: null},
    score, threshold: 1, exceeds: score > 1, eventStart: null}));
  return thresholdRatios({points, intervals, truncated: false});
}

test("models that disagree are named as disagreeing, with where each stands", () => {
  const lstm = line([[74, 0.5], [75, 0.8], [76, 1.4], [77, 6.3], [78, 3]], [{start: 76, end: 78, steps: 3, peak: 6.3, open: true}]);
  const forest = line([[74, 0.6], [75, 0.7], [76, 0.8], [77, 0.97], [78, 0.9]], []);
  const reads = [{name: "LSTM 오토인코더", line: lstm}, {name: "Isolation Forest", line: forest}];
  const message = modelMessage(reads, place)!;
  assert.equal(message.headline, "모델마다 다르게 말합니다. LSTM 오토인코더 점수는 76번째 측정부터 계속 기준을 넘고 있습니다"
    + "(3회, 가장 높을 때 기준의 6.3배), Isolation Forest 점수는 한 번도 기준을 넘지 않았습니다(가장 높을 때 기준의 0.97배).");
  assert.match(message.certainty!, /일부 모델만 기준을 넘어/);
  assert.equal(modelOnset(reads), 76);
  const both = modelMessage([reads[0], {name: "PCA", line: line([[77, 2], [78, 2]], [{start: 77, end: 78, steps: 2, peak: 2, open: true}])}], place)!;
  assert.match(both.headline, /^모든 모델이 기준을 넘고 있습니다/);
  assert.match(both.certainty!, /같은 무렵\(76번째 측정\)부터/);
  assert.equal(times(0.966), "0.97배");
  assert.equal(times(12.04), "12배");
});

test("the outlook gives every reading's reach and how far the past check lets one trust it", () => {
  const reach = (state: string, expected: number | null = null) => ({state, expected, earliest: null, latest: null});
  // Bearing1_1 at #100 with the user's 4 g and 6 g: four readings of the trend, the last 25 hidden for the check.
  const facts = {axis: "acquisition" as const, period: 60, unit: "g", conditions: {management: 4, end: 6},
    scenarios: [{id: "current", management: reach("expected", 6), end: reach("expected", 29)},
      {id: "recent", management: reach("expected", 4), end: reach("expected", 25)},
      {id: "responsive", management: reach("expected", 15), end: reach("possible")},
      {id: "linear", management: reach("expected", 15), end: reach("beyond")}],
    checks: [{points: 25, error: 1.53, naive: 1.62, coverage: 0}]};
  const message = outlookMessage(facts)!;
  assert.equal(message.headline, "지금 추세가 이어진다고 가정하면 관리 기준 4 g까지 추가 측정 4~15회(약 4분~15분) 남았습니다. "
    + "종료 기준 6 g까지 추가 측정 25~29회(약 25분~29분) 남았습니다(계산 방식 4가지 중 2가지에서만 닿음).");
  assert.equal(message.certainty, "기록의 마지막 25개를 가리고 같은 방법으로 예측해 보니 실제 값이 예측 범위 안에 든 비율은 0%였고, "
    + "마지막 값을 그대로 이어 쓴 것과 오차가 비슷했습니다. 계산 방식에 따라 도달 시점이 두 배 넘게 갈립니다. "
    + "도달 시점은 정확한 시각이 아니라 대략의 범위로 읽고, 새 측정이 들어올 때마다 다시 확인하세요.");
  const good = outlookMessage({...facts, period: null, conditions: {management: 4, end: null},
    scenarios: [{id: "current", management: reach("expected", 10), end: null}], checks: [{points: 20, error: 0.2, naive: 1, coverage: 0.9}]})!;
  assert.equal(good.headline, "지금 추세가 이어진다고 가정하면 관리 기준 4 g까지 추가 측정 10회 남았습니다.");
  assert.match(good.certainty!, /오차가 작았습니다. 과거 확인에서는 예측이 실제 값을 대체로 따라갔습니다/);
  const time = outlookMessage({...facts, axis: "time", period: null, conditions: {management: 4, end: 6},
    scenarios: [{id: "current", management: reach("already"), end: reach("beyond")}], checks: []})!;
  assert.equal(time.headline, "마지막 측정이 이미 관리 기준 4 g에 닿았습니다. 지금 추세가 이어진다고 가정하면 종료 기준 6 g에는 계산한 범위 안에서 닿지 않습니다.");
  assert.match(time.certainty!, /과거 자료로 예측을 확인하지 못했습니다/);
  assert.equal(outlookMessage({...facts, conditions: {management: null, end: null}}), null);
});
