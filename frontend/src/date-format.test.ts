import assert from "node:assert/strict";
import {test} from "node:test";
import {clockText, dateTime, dateTimeRange, kstInput, kstInstant, refreshedText, spanText, timeLabel} from "./date-format.ts";

test("records and form inputs agree on the Seoul date, including the year boundary", () => {
  const before = "2020-12-31T14:59:59Z", after = "2020-12-31T15:00:01Z";
  assert.equal(dateTime(before), "12월 31일(목) 23:59:59");
  assert.equal(dateTime(after, "minute"), "1월 1일(금) 00:00");
  assert.equal(dateTimeRange(before, after), "12월 31일(목) 23:59:59 ~ 1월 1일(금) 00:00:01");
  assert.equal(kstInput(after, "second"), "2021-01-01T00:00:01");
  assert.equal(Date.parse(kstInstant(kstInput(after, "second"))), Date.parse(after));
  assert.equal(timeLabel(after, "second", "UTC"), "15:00:01");
  assert.equal(clockText(after), "1월 1일(금) 00:00");
  assert.match(spanText(Date.parse(before), Date.parse(after)), /12월 31일.*1월 1일/);
  assert.throws(() => kstInstant("2021-02-30T01:00"), /시각 형식/);
});

test("a moment in a record reads the same on every screen; the list refresh is today's clock", () => {
  assert.equal(clockText("2020-10-22T14:59:00Z"), "10월 22일(목) 23:59");
  assert.equal(clockText("2020-10-22T14:59:08Z", "second"), "10월 22일(목) 23:59:08");
  const now = Date.parse("2026-11-26T11:36:00Z");
  assert.equal(refreshedText("2026-11-26T11:36:12Z", now), "20:36");
  assert.equal(refreshedText("2026-11-25T11:36:12Z", now), "11월 25일(수) 20:36");
  assert.equal(refreshedText(null, now), "기록 없음");
});
