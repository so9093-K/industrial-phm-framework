import assert from "node:assert/strict";
import {test} from "node:test";
import type {TrendPoint} from "./model-trend.ts";
import {asOf, largestChanges} from "./review-evidence.ts";
import {exceedanceStory, exceedanceText} from "./model-trend.ts";

test("how much: the largest stored relative changes, unknown ones left out", () => {
  const row = (feature: string, previous: number | null, current: number, relativePercent: number | null) =>
    ({feature, label: feature, previous, current, relativePercent});
  const rows = [row("a", 1, 1.1, 10), row("b", 1, 0.2, -80), row("c", null, 5, null), row("d", 1, 7.7, 670), row("e", 2, 2, 0)];
  assert.deepEqual(largestChanges(rows).map((item) => item.feature), ["d", "b", "a"]);
});

test("since when, as it stood at the reviewed measurement", () => {
  const point = (position: number, exceeds: boolean): TrendPoint => ({
    pointer: {position, runId: "r" + position, state: "analyzed", stepKey: "k" + position, changeSeq: position, reason: null},
    score: exceeds ? 2 : 0.5, threshold: 1, exceeds, eventStart: null});
  const points = Array.from({length: 12}, (_, i) => point(i + 1, i + 1 >= 6));
  const trend = {points, truncated: false, intervals: [{start: 6, end: 12, steps: 7, peak: 2, open: true}]};
  // Reviewing #8: the run held #8 then, with three crossings so far; later measurements are not counted.
  assert.equal(exceedanceText(exceedanceStory(asOf(trend, 8)), (at) => "#" + at)?.headline, "#6부터 계속 기준 초과 · 3회");
  // Reviewing #4, before the run: nothing had crossed yet.
  assert.equal(exceedanceStory(asOf(trend, 4)).state, "none");
});
