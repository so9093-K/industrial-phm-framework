import assert from "node:assert/strict";
import {test} from "node:test";
import {measurementLinks} from "./measurement-links.ts";

const query = (href: string) => new URL(href, "http://local").searchParams;

test("one measurement opens the same measurement in every vibration view", () => {
  const links = measurementLinks("bearing", 40, {first: 1, last: 45, feature: "rms", bindingId: "if-1"});
  const by = Object.fromEntries(links.map((link) => [link.key, query(link.href)]));
  assert.deepEqual(Object.keys(by), ["trend", "model", "spectrum", "features"]);
  assert.equal(by.trend.get("vibration_at"), "40");
  assert.deepEqual([by.model.get("model_position"), by.model.get("model_binding")], ["40", "if-1"]);
  assert.deepEqual(["a_from", "a_to", "b_from", "b_to"].map((key) => by.spectrum.get("spectrum_" + key)), ["39", "39", "40", "40"]);
  // The before/after comparison stays inside the stored measurements.
  assert.deepEqual(["a_from", "a_to", "b_from", "b_to"].map((key) => by.features.get("feature_" + key)), ["30", "39", "40", "45"]);
  assert.equal(by.features.get("acquisition_feature"), "rms");
});

test("the first measurement has nothing before it and unknown measurements offer nothing", () => {
  assert.deepEqual(measurementLinks("bearing", 1, {first: 1, last: 9}).map((link) => link.key), ["trend", "model"]);
  assert.deepEqual(measurementLinks("bearing", 3, {first: 1, last: 9}, "model").map((link) => link.key), ["trend", "spectrum", "features"]);
  assert.deepEqual(measurementLinks("bearing", 10, {first: 1, last: 9}), []);
});
