import assert from "node:assert/strict";
import {test} from "node:test";
import {num} from "./format.ts";

test("floating-point noise is not shown, while integers and missing values stay distinct", () => {
  assert.equal(num(0.7620000000000001), "0.762");
  assert.equal(num(1.59440625), "1.59441");
  assert.equal(num(-0.000123456789), "-0.000123457");
  assert.equal(num(64), "64");
  assert.equal(num(0), "0");
  assert.equal(num(null), "미산출");
  assert.equal(num(Number.NaN, "계산 안 됨"), "계산 안 됨");
});
