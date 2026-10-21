import assert from "node:assert/strict";
import {test} from "node:test";
import {measure, niceTicks, yTicks} from "./chart-axis.ts";

test("a value axis gets a few round ticks inside the drawn range", () => {
  assert.deepEqual(niceTicks(7.6, 13.2), [8, 10, 12]);
  assert.deepEqual(niceTicks(0.52, 3.41), [1, 2, 3]);
  assert.deepEqual(niceTicks(34.9, 43.7), [35, 37.5, 40, 42.5]);
  assert.deepEqual(niceTicks(2, 2), []);
  const ticks = yTicks(-0.5, 10.5, 10, 210);
  assert.deepEqual(ticks.map((tick) => tick.value), [0, 5, 10]);
  assert.ok(Math.abs(ticks.at(-1)!.y - (210 - (10.5 / 11) * 200)) < 1e-9);
  // A tick on the plot's edge would print half outside it.
  assert.deepEqual(yTicks(0, 10, 10, 210).map((tick) => tick.value), [2.5, 5, 7.5]);
});

test("values read with a few digits and their unit", () => {
  assert.equal(measure(12.8242, "A"), "12.8 A");
  assert.equal(measure(0.56389, null), "0.564");
  assert.equal(measure(1500.4, "rpm"), "1,500 rpm");
  assert.equal(measure(8, "°C"), "8 °C");
  assert.equal(measure(2e-8, null), "2.00e-8");
});
