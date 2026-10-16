import assert from "node:assert/strict";
import {test} from "node:test";
import {briefingSelection,verifyOutlookVersion,parseBriefings,BriefingEvidenceChanged} from "./outlook-briefings.ts";
import type {Projection} from "./projections.ts";
import type {AcquisitionProjection} from "./acquisition-outlook.ts";
const version="a".repeat(64);
const projection:Projection={
  assetId:"pump-1",channel:"R",horizon:"1h",
  measurementVersion:"measured-1",dataVersion:version,
  sourceId:"source-1",pointId:"point-1",unit:"A",
  record:{first:"2026-10-15T00:00:00Z",last:"2026-10-16T00:00:00Z",points:22},
  future:[],scenarios:[],conditions:{direction:"upper",management:12,end:null},
  outlookSettings:{changepointPriorScale:0.05,changepointRange:0.9,trainingPoints:null,seasonality:"auto"},
};
const serverOutlook=()=>({
  schema_version:1,asset_id:"pump-1",kind:"history",series:"R",axis:"time",
  source_id:"source-1",measurement_point_id:"point-1",
  measurement_version:"measured-1",data_version:version,
  conditions:{direction:"upper",management:12,end:null},
  settings:{changepoint_prior_scale:0.05,changepoint_range:0.9,training_points:null,seasonality:"auto"},
});
const selection=briefingSelection(projection);
function response(){
  return {schema_version:1,selection,briefings:[{
    id:"briefing-a",status:"complete",question:"어떤 변화?",model:"local-model",
    requested_at:"2026-10-16T00:01:00Z",finished_at:"2026-10-16T00:01:02Z",
    answer:{summary:"측정 흐름을 비교합니다.",points:[{text:"변화가 있었습니다.",evidence:["change"]}],
      evidence:{change:{label:"변화",text:"측정된 변화 근거"}},checks:{source:"computed"}},
  }]};
}
test("canonical briefing identity includes selected conditions and independent AI version",()=>{
  assert.equal(selection,
    "asset_id=pump-1&changepoint_prior_scale=0.05&changepoint_range=0.9"+
    "&data_version="+version+"&direction=upper&kind=history"+
    "&management_limit=12&seasonality=auto&series=R");
  assert.notEqual(briefingSelection({...projection,dataVersion:"b".repeat(64)}),selection);
  assert.notEqual(briefingSelection({...projection,conditions:{...projection.conditions,end:30}}),selection);
  assert.throws(()=>briefingSelection({...projection,dataVersion:"stale"}),/버전/);
});
test("server measurement/data versions and source/point must still match after refresh",()=>{
  assert.doesNotThrow(()=>verifyOutlookVersion(serverOutlook(),projection));
  const cases=[
    {data_version:"b".repeat(64)}, {measurement_version:"revised"},
    {source_id:"another"}, {measurement_point_id:"other"},
    {conditions:{direction:"lower",management:12,end:null}},
    {settings:{changepoint_prior_scale:0.5,changepoint_range:0.9,training_points:null,seasonality:"auto"}},
    {asset_id:"pump-2"},
  ];
  for(const patch of cases)
    assert.throws(()=>verifyOutlookVersion({...serverOutlook(),...patch},projection),
      BriefingEvidenceChanged);
});
test("the server echoes the exact selection before a stored answer can be displayed",()=>{
  const result=parseBriefings(response(),selection);
  assert.equal(result[0].answer?.source,"computed");
  assert.equal(result[0].answer?.evidence.change.label,"변화");
  assert.throws(()=>parseBriefings({...response(),selection:"old-query"},selection),
    BriefingEvidenceChanged);
  assert.throws(()=>parseBriefings({...response(),briefings:Array(6).fill(response().briefings[0])},
    selection),BriefingEvidenceChanged);
});
test("an AI point without the cited server fact must not be shown",()=>{
  const changed=response();
  changed.briefings[0].answer.points[0].evidence=["invented"];
  assert.throws(()=>parseBriefings(changed,selection),/존재하지 않는 계산 근거/);
});
test("stored pending/failed states never masquerade as completed explanations",()=>{
  const raw=response();
  const pending={...raw.briefings[0],id:"briefing-b",status:"pending",answer:null,finished_at:null};
  assert.equal(parseBriefings({...raw,briefings:[pending]},selection)[0].answer,null);
  assert.throws(()=>parseBriefings({...raw,briefings:[{...pending,status:"complete"}]},selection),
    /내용이 없습니다/);
  assert.throws(()=>parseBriefings({...raw,briefings:[{...pending,answer:raw.briefings[0].answer}]},
    selection),/완료되지 않은/);
});

const acquired:AcquisitionProjection={
  assetId:"bearing-a",sourceId:"wave-a",bindingId:"binding-a",featureId:"feature.rms",
  measurementVersion:"c".repeat(64),dataVersion:"d".repeat(64),timeBasis:"recorded",
  recordedPeriod:60,assumedPeriod:null,effectivePeriod:60,
  horizonCount:5,searchCount:31,searchUntil:95,
  record:{first:1,last:64,points:64},
  conditions:{direction:"upper",management:2.4,end:null},
  forecast:[{ordinal:65,estimate:2.1,lower:1.9,upper:2.3}],scenarios:[],
  outlookSettings:{changepointPriorScale:0.05,changepointRange:0.9,
    trainingPoints:null,seasonality:"off"},
};
const acquiredOutlook=()=>({
  schema_version:1,asset_id:"bearing-a",kind:"acquisition",axis:"acquisition",
  source_id:"wave-a",binding_id:"binding-a",measurement_point_id:null,
  measurement_version:acquired.measurementVersion,data_version:acquired.dataVersion,
  series:"feature.rms",time_basis:"recorded",period_seconds:60,
  recorded_period_seconds:60,assumed_period_seconds:null,
  conditions:{direction:"upper",management:2.4,end:null},
  record:{first:1,last:64,points:64},search:{acquisitions:31,until:95},
  settings:{changepoint_prior_scale:0.05,changepoint_range:0.9,
    training_points:null,seasonality:"off"},
});
test("acquisition briefing identity includes source, binding, measurement, axis and exact spacing",()=>{
  const identity=briefingSelection(acquired);
  assert.ok(identity.includes("kind=acquisition"));
  assert.ok(identity.includes("binding_id=binding-a"));
  assert.ok(identity.includes("measurement_version="+acquired.measurementVersion));
  assert.ok(identity.includes("time_basis=recorded"));
  assert.ok(identity.includes("recorded_period_seconds=60"));
  assert.notEqual(briefingSelection({...acquired,bindingId:"binding-b"}),identity);
  assert.notEqual(briefingSelection({...acquired,timeBasis:"ordinal",
    recordedPeriod:null,effectivePeriod:1}),identity);
  assert.notEqual(briefingSelection({...acquired,timeBasis:"assumed",
    assumedPeriod:120,effectivePeriod:120}),identity);
  assert.notEqual(briefingSelection({...acquired,outlookSettings:{...acquired.outlookSettings,
    changepointPriorScale:0.2}}),identity);
});
test("acquisition briefing rejects changed binding, series, time basis and stale anomaly facts",()=>{
  assert.doesNotThrow(()=>verifyOutlookVersion(acquiredOutlook(),acquired));
  const bad=[
    {binding_id:"binding-b"},{source_id:"new-wave"},{data_version:"e".repeat(64)},
    {measurement_version:"f".repeat(64)},{time_basis:"ordinal",period_seconds:1,
      recorded_period_seconds:null},{period_seconds:1},{series:"feature.other"},
    {search:{acquisitions:32,until:96}},
    {settings:{...acquiredOutlook().settings,seasonality:"auto"}},
  ];
  for(const patch of bad)
    assert.throws(()=>verifyOutlookVersion({...acquiredOutlook(),...patch},acquired),
      BriefingEvidenceChanged);
});
test("an acquisition briefing query must contain the exact echoed selection",()=>{
  const expected=briefingSelection(acquired);
  assert.deepEqual(parseBriefings({schema_version:1,selection:expected,briefings:[]},expected),[]);
  assert.throws(()=>parseBriefings({schema_version:1,selection:expected+"&binding_id=other",
    briefings:[]},expected),BriefingEvidenceChanged);
});
