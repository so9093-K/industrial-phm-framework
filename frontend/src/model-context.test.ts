import assert from "node:assert/strict";
import {test} from "node:test";
import {modelAtChange, modelEvidence, rareAtChange} from "./model-context.ts";

test("a partial model history cannot establish disagreement with a fully read model",()=>{
  const text=modelEvidence([{name:"IF",analyzed:20,exceeded:1,complete:false},{name:"LSTM",analyzed:52,exceeded:48}]);
  assert.ok(text?.includes("일부 조회"));
  assert.ok(!text?.includes("판단이 갈림"));
  assert.ok(text?.includes("구간 전체의 모델 반응을 비교할 수 없습니다"));
});
import type {ScoreTrend, TrendPoint} from "./model-trend.ts";

const point = (position: number, exceeds: boolean | null, state: "analyzed" | "skipped" = "analyzed"): TrendPoint => ({
  pointer: {position, runId: "r" + position, state, stepKey: "s", changeSeq: 1, reason: null},
  score: state === "analyzed" ? (exceeds ? 0.9 : 0.3) : null, threshold: 0.6, exceeds, eventStart: null});
const trend = (points: TrendPoint[]): ScoreTrend => ({points, intervals: [], truncated: false});

test("a time-window model is counted over the windows that ended inside the change", () => {
  const at = (m: number) => Date.UTC(2020, 9, 4, 0, m) * 1000;
  const read = trend([point(at(0), false), point(at(10), true), point(at(20), true), point(at(30), false, "skipped"),
    point(at(40), false), point(at(60), true)]);
  assert.deepEqual(modelAtChange(read, {from: Date.UTC(2020, 9, 4, 0, 5), to: Date.UTC(2020, 9, 4, 0, 45)}, "time"), {analyzed: 3, exceeded: 2});
});

test("a vibration model is counted over the change's own acquisitions", () => {
  const read = trend([70, 71, 72, 73, 74].map((n) => point(n, n >= 72)));
  assert.deepEqual(modelAtChange(read, {from: 72, to: 123}, "acquisition"), {analyzed: 3, exceeded: 3});
  assert.deepEqual(modelAtChange(read, {from: 1, to: 10}, "acquisition"), {analyzed: 0, exceeded: 0});
});

test("a change at an operating state the model hardly learned is said to need more than the model's excess", () => {
  const operation = {label: "전류평균", unplaced: 0, windows: [],
    names: {levels: [{low: 1, high: 26, typical: 10.6}, {low: 26, high: 46, typical: 31.4}, {low: 46, high: null, typical: 61.9}], stoppedBelow: 1, unit: "A"},
    reference: {from: "2020-09-15T15:00:00Z", to: "2020-09-20T02:59:00Z", shares: [0.01, 0.02, 0.03, 0.94]}};
  assert.equal(rareAtChange(operation, "약 11 A 운전"), 0.02);
  assert.equal(rareAtChange(operation, "약 62 A 운전"), null);
  assert.equal(rareAtChange({...operation, reference: null}, "약 11 A 운전"), null);
});

test("the model evidence counts each model over the change, says when they disagree and when the state was never learned", () => {
  assert.equal(modelEvidence([{name: "Isolation Forest", analyzed: 52, exceeded: 2}, {name: "LSTM 오토인코더", analyzed: 52, exceeded: 48}]),
    "판단이 갈림 · 기준 초과 LSTM 오토인코더 52회 중 48회, Isolation Forest 52회 중 2회");
  assert.equal(modelEvidence([{name: "Isolation Forest", analyzed: 134, exceeded: 134}], {condition: "약 11 A 운전", share: 0}),
    "기준 초과 Isolation Forest 134회 중 134회 · 학습 기간에 약 11 A 운전 없음");
  // 이 구간을 분석한 모델이 없으면 근거 줄을 만들지 않는다.
  assert.equal(modelEvidence([{name: "A", analyzed: 0, exceeded: 0}]), null);
});
