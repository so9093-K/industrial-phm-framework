import assert from "node:assert/strict";
import { test } from "node:test";
import {parseOptions, parsePairedProjection, MeasurementVersionMismatch,
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
  assert.throws(()=>parsePairedProjection(forecast(),outlook(),"b","R","1h",conditions),/대상/);
  assert.throws(()=>parsePairedProjection({...forecast(),meaning:"failure-time"},outlook(),
    "a","R","1h",conditions),/의미/);
});
