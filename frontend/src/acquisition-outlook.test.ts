import assert from "node:assert/strict";
import {test} from "node:test";
import {
  parseAcquisitionOptions,parseAcquisitionPair,AcquisitionVersionMismatch,
  validateAcquisitionChoice,
} from "./acquisition-outlook.ts";
const version="a".repeat(64),data="b".repeat(64);
const features=[{key:"feature.rms",label:"RMS",valid_points:64,count_forecast:true,
  valid_span_steps:63,horizons:{"1h":null}}];
const options=()=>({schema_version:1,asset_id:"bearing-a",history:null,
  acquisition:{source_id:"wave-source",binding_id:"anomaly-a",
    first:1,last:64,count:64,period_seconds:60,series:features}});
const forecast=()=>({
  schema_version:1,asset_id:"bearing-a",kind:"acquisition",
  axis:"acquisition",source_id:"wave-source",binding_id:"anomaly-a",
  measurement_point_id:null,measurement_version:version,time_basis:"recorded",
  period_seconds:60,recorded_period_seconds:60,assumed_period_seconds:null,
  series:"feature.rms",horizon:"count",horizon_count:20,
  meaning:"stored-flow-continued-not-failure-time-or-remaining-life",
  forecast:[[64,2.1,2,2.2],[65,2.2,2.1,2.3],[84,3,2.8,3.2]],
});
const outlook=()=>({
  schema_version:1,asset_id:"bearing-a",kind:"acquisition",
  axis:"acquisition",source_id:"wave-source",binding_id:"anomaly-a",
  measurement_point_id:null,measurement_version:version,time_basis:"recorded",
  period_seconds:60,recorded_period_seconds:60,assumed_period_seconds:null,
  series:"feature.rms",offset_unit:"acquisition",data_version:data,
  meaning:"remaining-margin-to-user-conditions-not-a-diagnosis",
  conditions:{direction:"upper",management:2.4,end:3},
  record:{first:1,last:64,points:64},
  search:{acquisitions:31,until:95},
  settings:{changepoint_prior_scale:0.05,changepoint_range:0.9,
    training_points:null,seasonality:"off"},
  scenarios:[{id:"linear",limits:{
    management:{state:"expected",expected:4,earliest:null,latest:null},
    end:{state:"possible",expected:null,earliest:13,latest:null},
  }}],
});
const conditions={direction:"upper" as const,management:2.4,end:3};
function paired(f:unknown=forecast(),o:unknown=outlook(),opts:unknown=options()){
  const parsed=parseAcquisitionOptions(opts,"bearing-a");
  assert.ok(parsed);
  return parseAcquisitionPair(f,o,parsed,"feature.rms",20,null,conditions);
}
test("acquisition choices preserve source and precise model binding",()=>{
  const result=parseAcquisitionOptions(options(),"bearing-a");
  assert.equal(result?.bindingId,"anomaly-a");
  assert.equal(result?.recordedPeriod,60);
  assert.equal(result?.features[0].validPoints,64);
  assert.throws(()=>parseAcquisitionOptions({...options(),asset_id:"another"},"bearing-a"),/설비/);
  assert.throws(()=>parseAcquisitionOptions({...options(),acquisition:{...options().acquisition,
    binding_id:""} },"bearing-a"),/데이터 출처 정보/);
});
test("paired ordinal forecast and conditional offsets never become UTC timestamps",()=>{
  const result=paired();
  assert.equal(result.timeBasis,"recorded");
  assert.equal(result.record.last,64);
  assert.equal(result.forecast[1].ordinal,65);
  assert.equal(result.scenarios[0].management?.expected,4);
  assert.equal(result.searchCount,31);
  assert.equal(result.searchUntil,95);
  assert.equal(result.dataVersion,data);
});
test("same observations with another binding, measurement version or source must fail",()=>{
  for(const delta of [
    {binding_id:"other"},
    {source_id:"other"},
    {measurement_version:"c".repeat(64)},
    {measurement_point_id:"point-that-is-not-an-acquisition"},
    {time_basis:"assumed"},
  ]){
    assert.throws(()=>paired(forecast(),{...outlook(),...delta}),
      AcquisitionVersionMismatch);
  }
  assert.throws(()=>paired({...forecast(),binding_id:"other"}),AcquisitionVersionMismatch);
});
test("ordinal without recorded spacing cannot create recorded or assumed time",()=>{
  const noClock={...options(),acquisition:{...options().acquisition,period_seconds:null}};
  const forecastCount={...forecast(),time_basis:"ordinal",period_seconds:1,
    recorded_period_seconds:null,assumed_period_seconds:null};
  const outlookCount={...outlook(),time_basis:"ordinal",period_seconds:1,
    recorded_period_seconds:null,assumed_period_seconds:null};
  const result=paired(forecastCount,outlookCount,noClock);
  assert.equal(result.timeBasis,"ordinal");
  assert.equal(result.recordedPeriod,null);
  assert.equal(result.assumedPeriod,null);
  assert.throws(()=>paired({...forecastCount,time_basis:"recorded"},
    {...outlookCount,time_basis:"recorded"},noClock),AcquisitionVersionMismatch);
});
test("declared assumed interval must match on both APIs, even if recorded exists",()=>{
  const selected=parseAcquisitionOptions(options(),"bearing-a");
  assert.ok(selected);
  const changed={time_basis:"assumed",period_seconds:120,assumed_period_seconds:120};
  const result=parseAcquisitionPair({...forecast(),...changed},{...outlook(),...changed},
    selected,"feature.rms",20,120,conditions);
  assert.equal(result.timeBasis,"assumed");
  assert.equal(result.recordedPeriod,60);
  assert.throws(()=>parseAcquisitionPair({...forecast(),...changed},
    {...outlook(),...changed,period_seconds:60},selected,"feature.rms",20,120,conditions),
    AcquisitionVersionMismatch);
});
test("invalid acquisition count, scope and future ordinates never render",()=>{
  const feature={id:"R",label:"R",validPoints:64,countForecast:true};
  assert.throws(()=>validateAcquisitionChoice(feature,0,null),/1~2000/);
  assert.throws(()=>validateAcquisitionChoice(feature,2001,null),/1~2000/);
  assert.throws(()=>validateAcquisitionChoice(feature,20,0),/1~86400/);
  assert.throws(()=>validateAcquisitionChoice({...feature,validPoints:1,countForecast:false},20,null),/20회/);
  assert.throws(()=>paired({...forecast(),forecast:[[100,12,11,13]]}),/요청 범위/);
  assert.throws(()=>paired(forecast(),{...outlook(),offset_unit:"second"}),/맞지 않아/);
  assert.throws(()=>paired(forecast(),{...outlook(),record:{first:1,last:65,points:64}}),
    AcquisitionVersionMismatch);
  assert.throws(()=>paired(forecast(),{...outlook(),search:{acquisitions:30,until:95}}),
    AcquisitionVersionMismatch);
});
