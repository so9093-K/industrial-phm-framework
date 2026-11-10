import assert from "node:assert/strict";
import { test } from "node:test";
import {loadOptions, loadPaired, outlookChart, steadyRange, parseOptions, parsePairedProjection, spreadRows, MeasurementVersionMismatch,
  type Conditions} from "./projections.ts";
const conditions:Conditions={direction:"upper",management:12,end:16};
const forecast=()=>({
  schema_version:1,asset_id:"a",kind:"history",series:"R",horizon:"1h",axis:"time",
  measurement_version:"v1",source_id:"src",measurement_point_id:"point",unit:"A",
  meaning:"stored-flow-continued-not-failure-time-or-remaining-life",
  forecast:[["2026-10-16T00:30:00Z",14,12,16]],
});
const outlook=()=>({
  schema_version:1,asset_id:"a",kind:"history",series:"R",axis:"time",
  measurement_version:"v1",data_version:"ai-review-fingerprint",source_id:"src",
  measurement_point_id:"point",
  meaning:"remaining-margin-to-user-conditions-not-a-diagnosis",
  conditions:{direction:"upper",management:12,end:16},
  record:{first:"2026-10-10T00:00:00Z",last:"2026-10-16T00:00:00Z",points:180},
  scenarios:[{id:"current",limits:{
    management:{state:"expected",expected:3600,earliest:3200,latest:3900},
    end:{state:"not-reached",expected:null,earliest:null,latest:null},
  }}],
});
test("forecast options are scoped to the selected asset and supported horizon",()=>{
  const src={schema_version:1,asset_id:"a",history:{series:[{key:"R"}],
    horizons:{"1h":null,"24h":"short-history","7d":"short-history","30d":"short-history"}}};
  assert.equal(parseOptions(src,"a").channels[0],"R");
  assert.equal(parseOptions(src,"a").horizons["24h"],"short-history");
  assert.throws(()=>parseOptions(src,"b"),/다른 설비/);
});
test("selected forecast readiness uses its own inputs and training limit",async()=>{
  const original=globalThis.fetch;
  const reasons={"1h":"few-points","24h":"few-points","7d":"few-points","30d":"few-points"};
  const payload={schema_version:1,asset_id:"a",history:{series:[{key:"long"},{key:"short"}],
    horizons:{"1h":null,"24h":null,"7d":null,"30d":null}},
    selection:{kind:"history",series:"short",points:10,horizons:reasons}};
  globalThis.fetch=(async(url:string|URL|Request)=>{
    const query=new URL(String(url),"http://localhost").searchParams;
    assert.equal(query.get("series"),"short");
    assert.equal(query.get("kind"),"history");
    assert.equal(query.get("training_points"),"100");
    return new Response(JSON.stringify(payload));
  }) as typeof fetch;
  try{
    const options=await loadOptions("a",new AbortController().signal,{channel:"short",trainingPoints:100});
    assert.deepEqual(options.horizons,reasons);
    await assert.rejects(loadOptions("a",new AbortController().signal,{channel:"short",trainingPoints:100,recordKey:"different"}),MeasurementVersionMismatch);
    assert.throws(()=>parseOptions(payload,"a","long"),/선택한 신호/);
    assert.throws(()=>parseOptions({...payload,selection:undefined},"a","short"),/선택한 신호/);
  }finally{globalThis.fetch=original;}
});
test("same measurement/version/source allows read-only joined evidence",()=>{
  const data=parsePairedProjection(forecast(),outlook(),"a","R","1h",conditions);
  assert.equal(data.future[0].estimate,14);
  assert.equal(data.scenarios[0].management?.expected,3600);
  assert.equal(data.dataVersion,"ai-review-fingerprint");
});
test("the reach sentence rests on the outlook's own check, not the drawn forecast's",async()=>{
  // Shaped like compressor 1338 R상전류: the 24 h forecast's check held 83% inside its band while
  // the outlook's check over its 3.5-day reach search held 0.4%; the screen said the former.
  const original=globalThis.fetch;
  globalThis.fetch=(async(url:string|URL|Request)=>new Response(JSON.stringify(String(url).startsWith("/api/v1/forecast?")
    ?{...forecast(),backtest:{points:143,mean_absolute_error:9.7,naive_mean_absolute_error:4.5,inside_interval:0.83}}
    :{...outlook(),check:{points:250,mean_absolute_error:65.5,naive_mean_absolute_error:4.5,inside_interval:0.004}}))) as typeof fetch;
  try{
    const data=await loadPaired("a","R","1h",conditions,new AbortController().signal);
    assert.deepEqual(data.checks?.map(check=>check.coverage),[0.83]);
    assert.deepEqual(data.reachChecks?.map(check=>check.coverage),[0.004]);
  }finally{globalThis.fetch=original;}
});
test("changed measurements or source block every joined result",()=>{
  assert.throws(()=>parsePairedProjection(forecast(),{...outlook(),measurement_version:"v2"},
    "a","R","1h",conditions),MeasurementVersionMismatch);
  assert.throws(()=>parsePairedProjection(forecast(),{...outlook(),source_id:"other"},
    "a","R","1h",conditions),MeasurementVersionMismatch);
});
test("each calculation uses and verifies the exact selected record",async()=>{
  const original=globalThis.fetch;
  const recordKey="record-b";
  const urls:string[]=[];
  globalThis.fetch=(async(url:string|URL|Request)=>{
    const parsed=new URL(String(url),"http://local");urls.push(parsed.pathname);
    assert.equal(parsed.searchParams.get("record_key"),recordKey);
    return new Response(JSON.stringify(parsed.pathname.endsWith("/forecast")
      ?{...forecast(),record_key:recordKey}:{...outlook(),record_key:recordKey}));
  }) as typeof fetch;
  try{
    const result=await loadPaired("a","R","1h",conditions,new AbortController().signal,undefined,recordKey);
    assert.equal(result.recordKey,recordKey);
    assert.deepEqual(urls.sort(),["/api/v1/forecast","/api/v1/outlook"]);
    assert.throws(()=>parsePairedProjection({...forecast(),record_key:"other"},{...outlook(),record_key:recordKey},"a","R","1h",conditions),MeasurementVersionMismatch);
  }finally{globalThis.fetch=original;}
});
test("changed conditions, asset and meanings fail closed",()=>{
  assert.throws(()=>parsePairedProjection(forecast(),{...outlook(),
    conditions:{direction:"lower",management:12,end:16}},"a","R","1h",conditions),/조건/);
  assert.throws(()=>parsePairedProjection(forecast(),outlook(),"b","R","1h",conditions),/맞지 않아/);
  assert.throws(()=>parsePairedProjection({...forecast(),meaning:"failure-time"},outlook(),
    "a","R","1h",conditions),/맞지 않아/);
});

test("the outlook chart shows recent records, the forecast range and both limits on one scale",()=>{
  const data=parsePairedProjection({...forecast(),
    history:[["2026-10-15T00:00:00Z",9],["2026-10-15T23:30:00Z",11],["2026-10-16T00:00:00Z",11.5],["2026-10-16T00:10:00Z",null]],
    forecast:[["2026-10-16T00:00:00Z",11.5,11,12],["2026-10-16T00:30:00Z",14,12,16]]},
  outlook(),"a","R","1h",conditions);
  // A missing stored value is skipped, never drawn as zero.
  assert.equal(data.history?.length,3);
  const chart=outlookChart(data)!;
  // Only twice the forecast span of history is shown, so the day-old value is left out.
  assert.equal(chart.low,11);
  assert.equal(chart.high,16);
  assert.ok(chart.management!>chart.endLimit!);
  assert.match(chart.band,/Z$/);
  assert.ok(chart.lastX>0&&chart.lastX<chart.width);
  assert.deepEqual(spreadRows([1,2,3,4,5,6,7,8,9,10],4),[1,4,7,10]);
});

test("a distant criterion cannot flatten the forecast unless the reader includes it",()=>{
  const data=parsePairedProjection({...forecast(),history:[["2026-10-16T00:00:00Z",11]]},outlook(),"a","R","1h",conditions);
  const distant={...data,conditions:{...data.conditions,end:1000}};
  const chart=outlookChart(distant)!;
  assert.equal(chart.high,16);
  assert.equal(chart.endLimit,null);
  assert.equal(outlookChart(distant,true)!.high,1000);
  assert.notEqual(outlookChart(distant,true)!.endLimit,null);
});

test("the drawn forecast range follows the estimate without the jitter of its sampled width", () => {
  // Widths of 2 and 4 alternate by sampling chance around an estimate that rises and falls daily.
  const future = Array.from({length: 200}, (_, index) => {
    const estimate = 220 + Math.sin(index / 28 * 2 * Math.PI) * 2, width = index % 2 ? 4 : 2;
    return {at: new Date(Date.UTC(2020, 9, 23) + index * 3_600_000).toISOString(), estimate, lower: estimate - width, upper: estimate + width};
  });
  const drawn = steadyRange(future);
  assert.equal(drawn.length, 200);
  for (const [index, row] of drawn.entries()) {
    const width = row.upper - future[index].estimate;
    assert.ok(width > 2.7 && width < 3.3, "width " + width + " at " + index);
    assert.ok(row.lower < future[index].estimate && row.upper > future[index].estimate);
  }
  // Points without a range are left out, as before.
  assert.equal(steadyRange([{...future[0], lower: null, upper: null}]).length, 0);
});

