import assert from "node:assert/strict";
import {test} from "node:test";
import {defaultPeriods,newValues,parseHistogram,parseProfile,parseSources,type Periods} from "./comparison.ts";
import {historyPeriodMessage} from "./analysis-messages.ts";
const a = "2026-10-01T00:00:00Z", m = "2026-10-02T00:00:00Z", e = "2026-10-03T00:00:00Z";
const periods: Periods = {a:{from:a,to:m},b:{from:m,to:e}};
const p=(n:number)=>({observation_count:n,usable_count:n,missing_count:0,non_good_count:0,
  conflict_count:0,quantiles:[n-2,n-1,n,n+1,n+2],mean:n});
const series=(source:string,point:string,unit:string)=>({
  kind:"history",key:"current",label:"current",source_id:source,source_type:"csv",
  measurement_point_id:point,interpretation_id:unit,unit,
  periods:{a:p(30),b:p(20)},comparison:{median_change:-10,b_outside_a_band_percent:20}
});
const response=(items:unknown[]=[])=>({
  schema_version:1,asset_id:"motor",kind:"history",meaning:"stored-measurements-compared-not-asset-health",
  periods,series:items,
});
test("two periods must be valid bounded time windows",()=>{
  assert.doesNotThrow(()=>defaultPeriods(a,e));
  assert.throws(()=>defaultPeriods(a,a),/부족/);
  assert.equal(defaultPeriods(a,e).b.to, "2026-10-03T00:00:01.000Z");
});
test("available source channels are bound to the asset",()=>{
  const src={schema_version:1,asset_id:"motor",history:{channels:["current","current"],start_at:a,end_at:e}};
  assert.deepEqual(parseSources(src,"motor").channels,["current"]);
  assert.throws(()=>parseSources(src,"other"),/계약/);
});
test("same channel across source/point/unit remains different comparison rows",()=>{
  const x=parseProfile(response([series("src-1","motor-1","A"),series("src-2","motor-2","V")]),
    "motor","current",periods);
  assert.equal(x.series.length,2);
  assert.notEqual(x.series[0].key,x.series[1].key);
  assert.equal(x.series[0].medianChange,-10);
  assert.throws(()=>parseProfile(response([series("src-1","motor-1","A")]),"motor","voltage",periods),
    /혼합/);
});
test("mismatched period, missing quantiles and invalid metrics fail closed",()=>{
  assert.throws(()=>parseProfile({...response(),periods:{...periods,b:{from:m,to:a}}},"motor","current",periods),/다른 통계/);
  const withoutEvidence=series("src-1","motor-1","A");
  withoutEvidence.periods.b.quantiles=null as unknown as number[];
  assert.throws(()=>parseProfile(response([withoutEvidence]),"motor","current",periods),/대표값 없이/);
});
test("unordered quantiles are rejected, ties are valid",()=>{
  const invalid=series("src-1","motor-1","A");
  invalid.periods.b.quantiles=[0,1,5,3,6];
  assert.throws(()=>parseProfile(response([invalid]),"motor","current",periods),/분위수/);
  const tied=series("src-1","motor-1","A");
  tied.periods.a.quantiles=[0,1,1,3,4];
  assert.equal(parseProfile(response([tied]),"motor","current",periods).series.length,1);
});

test("a comparison says how the source ran in each period and which level it compared within", () => {
  const periods = {a: {from: "2026-10-14T00:00:00Z", to: "2026-10-14T01:00:00Z"}, b: {from: "2026-10-14T01:00:00Z", to: "2026-10-14T02:00:00Z"}};
  const payload = (extra: Record<string, unknown>) => ({schema_version: 1, asset_id: "m", kind: "history",
    meaning: "stored-measurements-compared-not-asset-health", periods, series: [], ...extra});
  const operation = {source_id: "s", point_id: null, label: "전류", unit: "A", stopped_below: 1,
    levels: [{low: 1, high: 35, typical: 10}, {low: 35, high: null, typical: 60}], shares: {a: [0, 0.5, 0.5], b: null}};
  const read = parseProfile(payload({operation, level: 2}), "m", "전압", periods);
  assert.equal(read.level, 2);
  assert.deepEqual(read.operation?.shares, {a: [0, 0.5, 0.5], b: null});
  assert.equal(read.operation?.names.levels[1].typical, 60);
  assert.equal(parseProfile(payload({}), "m", "전압", periods).operation, null);
  assert.throws(() => parseProfile(payload({operation, level: 3}), "m", "전압", periods));
  assert.throws(() => parseProfile(payload({operation: {...operation, shares: {a: [1], b: null}}}), "m", "전압", periods));
});

test("a second group of values B took where A had almost none is found and said with its range", () => {
  // 1306-like: A sits near 219 V; 42% of B moved to about 380 V, while B's median barely moved.
  const a = Array(20).fill(0), b = Array(20).fill(0);
  a[1] = 950; a[2] = 50; b[1] = 500; b[2] = 80; b[17] = 300; b[18] = 120;
  const histogram = parseHistogram({low: 200, high: 400, bins: 20, a, b})!;
  assert.deepEqual(newValues(histogram), {low: 370, high: 390, count: 420, total: 1000});
  const told = historyPeriodMessage({unit: "V", a: {usable: 1000, median: 219, low: 214, high: 224}, b: {usable: 1000, median: 221},
    outsideCount: 420, outsidePercent: 42, medianChangePercent: 0.9, onset: null, means: {a: 219, b: 287},
    aMiddle: {low: 217, high: 221}, lowCurrent: null, newValues: newValues(histogram)})!;
  assert.match(told.meaning!, /^기간 B 측정 1000회 중 420회\(42%\)는 기간 A에 거의 없던 370~390 V 범위의 값입니다\(기간 A 측정의 1% 미만\)\./);
  // A shift within A's own values, or a small one, is not a second group.
  const near = [...a]; near[3] = 0;
  assert.equal(newValues(parseHistogram({low: 200, high: 400, bins: 20, a, b: [0, 600, 400, ...Array(17).fill(0)]})), null);
  assert.equal(newValues(parseHistogram({low: 200, high: 400, bins: 20, a, b: [0, 950, 0, ...Array(16).fill(0), 50]})), null);
  assert.equal(newValues(parseHistogram({low: 200, high: 400, bins: 20, a: near, b: null})), null);
  assert.equal(parseHistogram(null), null);
  assert.throws(() => parseHistogram({low: 200, high: 400, bins: 20, a: [1, 2], b}), /값 분포/);
});

