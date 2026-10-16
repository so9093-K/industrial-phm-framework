import assert from "node:assert/strict";
import {test} from "node:test";
import {defaultPeriods,parseProfile,parseSources,type Periods} from "./comparison.ts";
const a = "2026-10-01T00:00:00Z", m = "2026-10-02T00:00:00Z", e = "2026-10-03T00:00:00Z";
const periods: Periods = {a:{from:a,to:m},b:{from:m,to:e}};
const p=(n:number)=>({observation_count:n,usable_count:n,missing_count:0,non_good_count:0,
  conflict_count:0,quantiles:[0,1,n,3,4],mean:n});
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
  assert.throws(()=>parseProfile(response([withoutEvidence]),"motor","current",periods),/계산 근거/);
});
