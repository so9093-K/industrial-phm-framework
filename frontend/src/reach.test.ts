import assert from "node:assert/strict";
import {test} from "node:test";
import {reachDuration,reachText,recordAgeText,reachCalendarText} from "./reach.ts";

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

test("an old forecast is anchored to the last measurement and never claims observed failure", () => {
  const last = "2026-10-18T00:00:00Z", now = Date.parse("2026-10-20T00:00:00Z");
  assert.match(recordAgeText(last, now), /2일 전에 끝났습니다/);
  assert.equal(recordAgeText(last, Date.parse(last)), "");
  assert.match(reachCalendarText(reach("expected", 3600), last, now), /도달 예상 시점이 지났습니다/);
  assert.match(reachCalendarText(reach("expected", 3600), last, now), /실제 도달 여부는 이후 측정/);
  assert.match(reachCalendarText(reach("expected", 3600), last, Date.parse(last)), /도달 예상 시각.*10\. 18\..*10:00/);
  assert.doesNotMatch(reachCalendarText(reach("expected", 3600), last, Date.parse(last)), /지났/);
  assert.match(reachCalendarText(reach("possible", null, 3600), last, now), /예측 범위의 가장 이른 도달 시각.*지난 시점/);
  assert.equal(reachCalendarText(reach("beyond"), last, now), "");
  assert.equal(reachCalendarText(reach("already"), last, now), "");
});
