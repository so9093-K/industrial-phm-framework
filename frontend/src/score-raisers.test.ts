import assert from "node:assert/strict";
import test from "node:test";
import {raisersText, scoreRaisers, signalOf} from "./score-raisers.ts";

test("a feature belongs to the signal it summarizes", () => {
  assert.equal(signalOf("R상역률.mean"), "R상역률");
  assert.equal(signalOf("feature.Horizontal_vibration_signals.rms"), "수평 진동");
  assert.equal(signalOf("current.phase_r.mean_a"), "current.phase_r.mean_a");
});

test("signals are ranked by what their features added to the score", () => {
  const raisers = scoreRaisers({"R상역률.mean": 0.3, "R상역률.min": 0.22, "R상전압.max": 0.4, "R상전류.std": 0.08, "R상전압.mean": -0.5});
  assert.deepEqual(raisers, [
    {signal: "R상역률", share: 52, feature: "R상역률.mean"},
    {signal: "R상전압", share: 40, feature: "R상전압.max"},
    {signal: "R상전류", share: 8, feature: "R상전류.std"},
  ]);
  assert.equal(raisersText(raisers.slice(0, 2)), "R상역률 52% · R상전압 40%");
});

test("several results add their parts before the shares are taken", () => {
  assert.deepEqual(scoreRaisers([{"a.mean": 1}, {"b.mean": 3}, null], 1), [{signal: "b", share: 75, feature: "b.mean"}]);
});

test("a model without parts names no signal", () => {
  assert.deepEqual(scoreRaisers(undefined), []);
  assert.deepEqual(scoreRaisers({"a.mean": -1, "b.mean": 0}), []);
  assert.equal(raisersText([]), "");
});
