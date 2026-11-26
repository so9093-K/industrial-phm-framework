import assert from "node:assert/strict";
import {test} from "node:test";
import {clockText, dateTime, dateTimeRange, kstInput, kstInstant, spanText, timeLabel} from "./date-format.ts";

test("records and form inputs agree on the Seoul date, including the year boundary", () => {
  const before = "2020-12-31T14:59:59Z", after = "2020-12-31T15:00:01Z";
  assert.equal(dateTime(before), "2020. 12. 31. 23:59:59");
  assert.equal(dateTime(after, "minute"), "2021. 1. 1. 00:00");
  assert.equal(dateTimeRange(before, after), "2020. 12. 31. 23:59:59 ~ 2021. 1. 1. 00:00:01");
  assert.equal(kstInput(after, "second"), "2021-01-01T00:00:01");
  assert.equal(Date.parse(kstInstant(kstInput(after, "second"))), Date.parse(after));
  assert.equal(timeLabel(after, "second", "UTC"), "15:00:01");
  assert.equal(clockText(after), "1월 1일(금) 00:00");
  assert.match(spanText(Date.parse(before), Date.parse(after)), /12월 31일.*1월 1일/);
  assert.throws(() => kstInstant("2021-02-30T01:00"), /시각 형식/);
});
