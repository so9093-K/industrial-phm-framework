import assert from "node:assert/strict";
import {test} from "node:test";
import {parseModelOperation, unlearnedText} from "./model-operation.ts";

const body = (operation: unknown) => ({schema_version: 1, binding_id: "b", operation});
const operation = {label: "전류평균", unit: "A", stopped_below: 1, unplaced: 0,
  levels: [{low: 1, high: 26.1, typical: 10.6}, {low: 26.1, high: 45.9, typical: 31.4}, {low: 45.9, high: null, typical: 61.9}],
  reference: {from: "2020-09-15T15:00:00+00:00", to: "2020-09-20T02:59:42+00:00", shares: [0, 0, 0, 1]},
  windows: [{band: 1, count: 480, exceeded: 480}, {band: 2, count: 1520, exceeded: 1520}, {band: 3, count: 3327, exceeded: 438}]};

test("a model's excesses are said per operating level beside what its reference period held", () => {
  const read = parseModelOperation(body(operation), "b")!;
  assert.equal(read.windows.length, 3);
  assert.equal(unlearnedText(read),
    "기준 초과 2,438회 중 2,000회는 모델 기준 기간에 거의 없던 운전 상태(약 11 A 운전·약 31 A 운전)의 창입니다. "
    + "기준 기간에 있던 약 62 A 운전에서는 3,327개 중 438개(13%)가 기준을 넘었습니다.");
  // A model whose reference held every level it later saw has nothing to say apart.
  assert.equal(unlearnedText({...read, reference: {...read.reference!, shares: [0, 0.2, 0.3, 0.5]}}), null);
  assert.equal(parseModelOperation(body(null), "b"), null);
  assert.throws(() => parseModelOperation(body(operation), "other"));
  assert.throws(() => parseModelOperation(body({...operation, windows: [{band: 4, count: 1, exceeded: 0}]}), "b"));
  assert.throws(() => parseModelOperation(body({...operation, windows: [{band: 1, count: 1, exceeded: 2}]}), "b"));
});
