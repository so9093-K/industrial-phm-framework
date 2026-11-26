import assert from "node:assert/strict";
import test from "node:test";
import {answerParts, freshLink} from "./answer-text.ts";

test("measured values stand out, dates and counts do not", () => {
  const parts = answerParts("수직 진동 RMS가 0.617g에서 2.19 g으로, 약 3.5배가 됐습니다. 10월 4일 72번째 측정부터 226 V입니다.");
  assert.deepEqual(parts.filter((part) => part.value).map((part) => part.text), ["0.617g", "2.19 g", "3.5배", "226 V"]);
  assert.equal(parts.map((part) => part.text).join(""), "수직 진동 RMS가 0.617g에서 2.19 g으로, 약 3.5배가 됐습니다. 10월 4일 72번째 측정부터 226 V입니다.");
  assert.deepEqual(answerParts("값이 없습니다."), [{text: "값이 없습니다.", value: false}]);
});

test("the same analysis link is not offered twice in a row", () => {
  const thread = [{analysis: "open_compare"}, {analysis: "open_compare"}, {analysis: "open_spectrum"}, {analysis: null}, {analysis: "open_compare"}];
  assert.deepEqual(thread.map((_, index) => freshLink(thread, index)), [true, false, true, false, true]);
});
