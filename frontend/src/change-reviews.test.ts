import assert from "node:assert/strict";
import {test} from "node:test";
import {parseChangePage} from "./change-reviews.ts";

test("a stored change judged within one operating level can be read back", () => {
  // 운전 수준별로 판단한 변화(공기압축기 1306의 R상전압)는 스냅샷에 운전 수준 표 없이 저장된다.
  const key = "a".repeat(64);
  const finding = {review_key: key, key: "b".repeat(64), channel: "R상전압", label: "R상전압", unit: "V", direction: "up", kind: "departure",
    start: "2020-10-04T09:19:44+09:00", end: "2020-10-05T07:31:42+09:00", value: 227.8, reason: "sustained",
    reference_value: 221.8, typical_value: 226.1, usual: {low: 218.5, high: 225.2}, within: [], related: [], baseline: null,
    source_id: "s", measurement_point_id: null, interpretation_id: "i", record: {from: "2020-09-16T00:00:00+09:00", to: "2020-10-22T23:59:09+09:00"},
    band: 1, operation: {key: "c".repeat(64), interval: [0, 0.44, 0.56, 0], baseline: [0, 0.15, 0.44, 0.41]}};
  const page = parseChangePage({schema_version: 1, asset_id: "공기압축기 1306", next_before: null, captures: [{
    capture_id: "change-review-" + "d".repeat(64), captured_at: "2026-11-19T12:57:33+00:00",
    snapshot: {change: {asset_id: "공기압축기 1306", finding}, identity: {asset_id: "공기압축기 1306", finding_id: key}},
    review: {status: "open", events: []}}]}, "공기압축기 1306");
  const read = page.captures[0];
  assert.equal(read.kind, "history");
  assert.equal(read.kind === "history" && read.finding.channel, "R상전압");
});
