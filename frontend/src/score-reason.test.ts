import assert from "node:assert/strict";
import test from "node:test";
import {reasonValueText, scoreReason} from "./score-reason.ts";

const parts = {"R상전류.std": 0.4, "R상전류.max": 0.1, "R상전류고조파.std": 0.3, "전류평균.min": 0.25, "R상역률.mean": 0.15, "R상전압.mean": 0.28};
const measured = [
  {feature: "R상전류.std", label: "R상전류 표준편차", current: 3.92, unit: null, learned: {low: 0.122, high: 1.22}},
  {feature: "전류평균.min", label: "전류평균 최소", current: 49.9, unit: null, learned: {low: 52.8, high: 64.2}},
];
const names = new Map([["R상전류", {label: "R상전류", unit: "A"}], ["전류평균", {label: "전류평균", unit: "A"}]]);

test("three signals lead and the rest is one line, adding up to the whole", () => {
  const reason = scoreReason(parts, measured, names)!;
  assert.deepEqual(reason.rows.map((row) => [row.signal, row.share, row.statistic]),
    [["R상전류", 34, "표준편차"], ["R상전류고조파", 20, "R상전류고조파.std"], ["R상전압", 19, "R상전압.mean"]]);
  assert.deepEqual(reason.rest, {signals: 2, share: 27});
});

test("a value is read against the model's reference period in the signal's unit", () => {
  const [current] = scoreReason(parts, measured, names)!.rows;
  assert.equal(reasonValueText(current, String), "표준편차 3.92 A · 기준 기간보다 높음 (0.122–1.22 A)");
  const low = scoreReason({"전류평균.min": 1}, measured, names)!.rows[0];
  assert.equal(reasonValueText(low, String), "최소 49.9 A · 기준 기간보다 낮음 (52.8–64.2 A)");
  assert.equal(scoreReason({"전류평균.min": 1}, measured, names)!.rest, null);
});

test("a result without parts has no reason", () => {
  assert.equal(scoreReason(undefined, measured, names), null);
  assert.equal(scoreReason({"a.mean": -1}, measured, null), null);
});
