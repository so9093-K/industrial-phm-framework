import assert from "node:assert/strict";
import test from "node:test";
import {apartFromStart, worseThanPersistence} from "./forecast-fit.ts";

// 전망의 주의 문구는 이 두 판정을 따른다: 예측 시작값이 최근 측정 범위 밖인가, 과거에 단순 지속보다 오차가 컸는가.
test("a forecast that starts away from the latest measurements is told apart from a fair one", () => {
  // 베어링: 마지막 7.27 g, 예측 시작 4.49 g(범위 4.08–4.93). 압축기: 마지막 213.9 V, 시작 219.8 V(217.4–222.5).
  assert.equal(apartFromStart(7.27, {estimate: 4.49, lower: 4.08, upper: 4.93}), true);
  assert.equal(apartFromStart(213.9, {estimate: 219.8, lower: 217.4, upper: 222.5}), true);
  assert.equal(apartFromStart(4.6, {estimate: 4.49, lower: 4.08, upper: 4.93}), false);
  assert.equal(apartFromStart(7.27, {estimate: 4.49, lower: null, upper: null}), false);
  assert.equal(worseThanPersistence({error: 0.8, naive: 0.3}), true);
  assert.equal(worseThanPersistence({error: 0.2, naive: 0.3}), false);
});
