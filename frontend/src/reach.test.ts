import assert from "node:assert/strict";
import {test} from "node:test";
import {reachDuration,reachText} from "./reach.ts";

const reach = (state: string, expected: number | null = null, earliest: number | null = null) =>
  ({state, expected, earliest, latest: null});

test("limit reach reads the same everywhere and keeps its own axis", () => {
  assert.equal(reachText(reach("already"), "time"), "이미 넘음");
  assert.equal(reachText(reach("expected", 7200), "time"), "마지막 기록 후 약 2.0시간 닿음");
  assert.equal(reachText(reach("expected", 130), "time"), "마지막 기록 후 약 2분 닿음");
  assert.equal(reachText(reach("expected", 5), "time"), "마지막 기록 후 약 1분 닿음");
  assert.equal(reachText(reach("expected", 3 * 86400), "time"), "마지막 기록 후 약 3.0일 닿음");
  assert.equal(reachText(reach("expected", 7), "acquisition"), "추가 측정 7회 후 닿음");
  assert.equal(reachText(reach("possible", null, 5), "acquisition"),
    "예측 범위에서만 닿을 수 있음 · 빠르면 추가 측정 5회 후");
  assert.equal(reachText(reach("beyond"), "acquisition"), "계산 범위 안에서는 닿지 않음");
  assert.equal(reachText(null, "time"), "계산 안 됨");
  // A count is never shown as hours.
  assert.doesNotMatch(reachText(reach("expected", 3600), "acquisition"), /시간/);
});

test("a count becomes a duration only with a recorded or assumed interval", () => {
  assert.equal(reachDuration(reach("expected", 26), 60), "약 26분");
  assert.equal(reachDuration(reach("possible", null, 90), 60), "약 1.5시간");
  assert.equal(reachDuration(reach("expected", 26), null), "");
  assert.equal(reachDuration(reach("already"), 60), "");
});
