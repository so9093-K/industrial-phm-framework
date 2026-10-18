import assert from "node:assert/strict";
import { test } from "node:test";
import {outlookChart, parseOptions, parsePairedProjection, spreadRows, MeasurementVersionMismatch,
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
test("same measurement/version/source allows read-only joined evidence",()=>{
  const data=parsePairedProjection(forecast(),outlook(),"a","R","1h",conditions);
  assert.equal(data.future[0].estimate,14);
  assert.equal(data.scenarios[0].management?.expected,3600);
  assert.equal(data.dataVersion,"ai-review-fingerprint");
});
test("changed measurements or source block every joined result",()=>{
  assert.throws(()=>parsePairedProjection(forecast(),{...outlook(),measurement_version:"v2"},
    "a","R","1h",conditions),MeasurementVersionMismatch);
  assert.throws(()=>parsePairedProjection(forecast(),{...outlook(),source_id:"other"},
    "a","R","1h",conditions),MeasurementVersionMismatch);
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
