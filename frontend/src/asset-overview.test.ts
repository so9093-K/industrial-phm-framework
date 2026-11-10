import assert from "node:assert/strict";
import {test} from "node:test";
import {equipmentKind, parseOverview, sparkline} from "./asset-overview.ts";

const row = {schema_version: 1, asset_id: "공기압축기 1306", kind: "history", finding_count: 3, judged: 25, copied: 9,
  operation: {key: "k", label: "전류평균", stopped_below: 1, shares: [0, 0.08, 0.29, 0.63],
    levels: [{low: 1, high: 26.1, typical: 10.6}, {low: 26.1, high: 45.9, typical: 31.4}, {low: 45.9, high: null, typical: 61.9}]},
  main: {label: "전류평균", unit: "A", axis: "time", latest: {at: "2020-10-22T14:59:08+00:00", value: 60.3},
    trace: [["2020-09-15T15:00:00+00:00", 62], ["2020-09-16T15:00:00+00:00", 61]]},
  finding: {label: "R상전압", unit: "V", band: 1, direction: "up", kind: "departure", value: 228,
    reference: 222, typical: 226, start: "2020-10-04T00:19:44+00:00", end: "2020-10-05T03:51:24+00:00"}};

test("an overview row reads the summary's first change with how the asset ran", () => {
  const read = parseOverview(row, "공기압축기 1306");
  assert.equal(read.finding?.band, 1);
  assert.equal(read.operation?.names.levels[2].typical, 61.9);
  assert.equal(read.main?.trace[1].x, Date.parse("2020-09-16T15:00:00+00:00"));
  assert.equal(read.copied, 9);
  assert.throws(() => parseOverview(row, "other"));
  assert.throws(() => parseOverview({...row, operation: {...row.operation, shares: [1]}}, "공기압축기 1306"));
  const empty = parseOverview({schema_version: 1, asset_id: "x", kind: null, operation: null, main: null, finding: null,
    finding_count: 0, judged: 0, copied: 0}, "x");
  assert.equal(empty.kind, null);
});

test("the kind of equipment is the name without its number", () => {
  assert.equal(equipmentKind("공기압축기 1306"), "공기압축기");
  assert.equal(equipmentKind("펌프·일반모터 4025"), "펌프·일반모터");
  assert.equal(equipmentKind("Bearing1_1"), "Bearing");
  assert.equal(equipmentKind("보일러"), "보일러");
});

test("a sparkline spans its box and draws nothing from a single point", () => {
  assert.equal(sparkline([{x: 0, value: 1}], 120, 28), "");
  assert.equal(sparkline([{x: 0, value: 0}, {x: 10, value: 10}], 120, 28), "M0.0 26.0 L120.0 2.0");
});
