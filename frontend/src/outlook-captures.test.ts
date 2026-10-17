import assert from "node:assert/strict";
import {test} from "node:test";
import {
  capturePayload,compareReobservation,factsOf,nextReviewStatus,parseCapturePage,parseCurrentOutlook,positionText,
  reobservationUrl,captureUrl,reviewNote,CaptureNotFound,CaptureRejected,
} from "./outlook-captures.ts";
import type {Projection} from "./projections.ts";
import type {AcquisitionProjection} from "./acquisition-outlook.ts";
import type {CapturedOutlook} from "./outlook-captures.ts";
import type {BriefingProjection} from "./outlook-briefings.ts";
const compare=(saved:CapturedOutlook,current:BriefingProjection)=>compareReobservation(saved,factsOf(current));

const measured="a".repeat(64),evidence="b".repeat(64);
const settings={changepointPriorScale:0.05,changepointRange:0.8,trainingPoints:null,seasonality:"off" as const};
const serverSettings={changepoint_prior_scale:0.05,changepoint_range:0.8,training_points:null,seasonality:"off"};
const reach=(state:string,expected:number|null=null,earliest:number|null=null)=>
  ({state,expected,earliest,latest:null});
const history:Projection={
  assetId:"motor-a",channel:"R",horizon:"1h",measurementVersion:measured,dataVersion:evidence,
  sourceId:"source-a",pointId:"point-a",unit:"A",
  record:{first:"2026-10-15T00:00:00+00:00",last:"2026-10-16T00:00:00+00:00",points:180},
  future:[],scenarios:[{id:"current",management:reach("expected",7200),end:null}],
  conditions:{direction:"upper",management:12,end:null},outlookSettings:settings,
};
const acquisition:AcquisitionProjection={
  assetId:"bearing-a",sourceId:"bench",bindingId:"anomaly-a",featureId:"feature.rms",
  measurementVersion:measured,dataVersion:evidence,timeBasis:"recorded",
  recordedPeriod:60,assumedPeriod:null,effectivePeriod:60,horizonCount:5,searchCount:31,searchUntil:95,
  outlookSettings:settings,conditions:{direction:"upper",management:2.4,end:3},
  record:{first:1,last:64,points:64},forecast:[],
  scenarios:[{id:"current",management:reach("expected",4),end:reach("possible",null,9)}],
};

function snapshot(kind:"history"|"acquisition",change:Record<string,unknown>={}){
  const acq=kind==="acquisition";
  const outlook:Record<string,unknown>={
    schema_version:1,asset_id:acq?"bearing-a":"motor-a",kind,series:acq?"feature.rms":"R",
    axis:acq?"acquisition":"time",source_id:acq?"bench":"source-a",
    measurement_point_id:acq?null:"point-a",measurement_version:measured,data_version:evidence,
    record:acq?{first:1,last:64,points:64}
      :{first:"2026-10-15T00:00:00+00:00",last:"2026-10-16T00:00:00+00:00",points:180},
    conditions:acq?{direction:"upper",management:2.4,end:3}:{direction:"upper",management:12,end:null},
    settings:serverSettings,
    scenarios:[{id:"current",limits:acq
      ?{management:reach("expected",4),end:reach("possible",null,9)}
      :{management:reach("expected",7200)}}],
    sentences:["저장된 측정의 변화입니다."],
    meaning:"remaining-margin-to-user-conditions-not-a-diagnosis",
    ...(acq?{binding_id:"anomaly-a",time_basis:"recorded",period_seconds:60,recorded_period_seconds:60}:{}),
    ...change,
  };
  const identity:Record<string,unknown>={
    asset_id:outlook.asset_id,kind,series:outlook.series,source_id:outlook.source_id,
    measurement_point_id:outlook.measurement_point_id,axis:outlook.axis,
    time_basis:outlook.time_basis??null,
    assumed_period_seconds:outlook.time_basis==="assumed"?outlook.period_seconds:null,
    record:outlook.record,conditions:outlook.conditions,settings:outlook.settings,
    measurement_version:outlook.measurement_version,data_version:outlook.data_version,
  };
  return {schema_version:1,identity,selection:{},outlook,
    meaning:"captured-condition-outlook-not-actual-failure-or-maintenance"};
}
const event=(id:string,action:string,note="")=>
  ({event_id:"00000000-0000-4000-8000-"+id.padStart(12,"0"),action,note,
    recorded_at:"2026-10-16T01:00:00+00:00"});
function row(kind:"history"|"acquisition",id="1",extra:Record<string,unknown>={}){
  return {capture_id:"outlook-capture-"+id.repeat(64).slice(0,64),
    captured_at:"2026-10-16T00:30:00+00:00",snapshot:snapshot(kind),
    source_recheck:"same_measurement_projection",
    review:{status:"acknowledged",events:[event("1","note","메모"),event("2","acknowledge")]},...extra};
}
const page=(...captures:unknown[])=>({schema_version:1,captures});

test("a capture names the shown selection and provenance, never calculated facts",()=>{
  assert.deepEqual(capturePayload(history),{
    asset_id:"motor-a",kind:"history",series:"R",direction:"upper",source_id:"source-a",
    measurement_version:measured,data_version:evidence,changepoint_prior_scale:"0.05",
    changepoint_range:"0.8",seasonality:"off",management_limit:"12",
  });
  assert.deepEqual(capturePayload(acquisition),{
    asset_id:"bearing-a",kind:"acquisition",series:"feature.rms",direction:"upper",
    source_id:"bench",measurement_version:measured,data_version:evidence,
    changepoint_prior_scale:"0.05",changepoint_range:"0.8",seasonality:"off",
    management_limit:"2.4",end_limit:"3",binding_id:"anomaly-a",time_basis:"recorded",
    recorded_period_seconds:"60",
  });
  const assumed=capturePayload({...acquisition,timeBasis:"assumed",assumedPeriod:30,effectivePeriod:30});
  assert.equal(assumed.assumed_period_seconds,"30");
  assert.equal(assumed.time_basis,"assumed");
  const ordinal=capturePayload({...acquisition,timeBasis:"ordinal",recordedPeriod:null,effectivePeriod:1});
  assert.equal("recorded_period_seconds" in ordinal,false);
  assert.equal("assumed_period_seconds" in ordinal,false);
  assert.throws(()=>capturePayload({...history,measurementVersion:"measure-v1"}),CaptureRejected);
  assert.throws(()=>capturePayload({...history,outlookSettings:null}),CaptureRejected);
});

test("saved records are scoped to one asset and their identity must match the archived facts",()=>{
  const parsed=parseCapturePage(page(row("history"),row("history","2")),"motor-a").captures;
  assert.equal(parsed.length,2);
  assert.equal(parsed[0].outlook.pointId,"point-a");
  assert.equal(parsed[0].review.status,"acknowledged");
  assert.throws(()=>parseCapturePage(page(row("history"),row("acquisition","2")),"motor-a"),/다른 설비/);
  const acq=parseCapturePage(page(row("acquisition")),"bearing-a").captures[0].outlook;
  assert.deepEqual(acq.record,{first:1,last:64,points:64});
  assert.equal(acq.bindingId,"anomaly-a");
  assert.equal(acq.timeBasis,"recorded");
  const tampered=row("history");
  (tampered.snapshot.outlook as Record<string,unknown>).measurement_version="c".repeat(64);
  assert.throws(()=>parseCapturePage(page(tampered),"motor-a"),/식별 정보/);
  const moved=row("acquisition");
  (moved.snapshot.outlook as Record<string,unknown>).record={first:1,last:65,points:65};
  assert.throws(()=>parseCapturePage(page(moved),"bearing-a"),/식별 정보/);
  const older=row("acquisition");
  delete (older.snapshot.outlook as Record<string,unknown>).binding_id;
  assert.equal(parseCapturePage(page(older),"bearing-a").captures[0].outlook.bindingId,null);
  const invented=row("acquisition");
  (invented.snapshot.outlook as Record<string,unknown>).record={first:1,last:"2026-10-16T00:00:00Z",points:64};
  (invented.snapshot.identity as Record<string,unknown>).record={first:1,last:"2026-10-16T00:00:00Z",points:64};
  assert.throws(()=>parseCapturePage(page(invented),"bearing-a"),/측정 순서/);
  assert.throws(()=>parseCapturePage(page(row("history",undefined,{source_recheck:"fine"})),"motor-a"),/재검증/);
  assert.throws(()=>parseCapturePage(page(row("history"),row("history")),"motor-a"),/식별자/);
});

test("paging and exact deep links never substitute another record",()=>{
  const first=row("history","1"),second=row("history","2");
  assert.equal(parseCapturePage({...page(first,second),next_before:second.capture_id},"motor-a")
    .nextBefore,second.capture_id);
  assert.throws(()=>parseCapturePage({...page(first,second),next_before:first.capture_id},"motor-a"),/다음 쪽/);
  assert.equal(parseCapturePage(page(first),"motor-a",first.capture_id).captures.length,1);
  assert.throws(()=>parseCapturePage(page(second),"motor-a",first.capture_id),CaptureNotFound);
  assert.throws(()=>parseCapturePage(page(),"motor-a",first.capture_id),CaptureNotFound);
});

test("human review status is replayed from its append-only events",()=>{
  assert.equal(nextReviewStatus("open","note"),"open");
  assert.equal(nextReviewStatus("open","acknowledge"),"acknowledged");
  assert.equal(nextReviewStatus("acknowledged","close"),"closed");
  assert.throws(()=>nextReviewStatus("open","close"),/전이/);
  assert.throws(()=>nextReviewStatus("closed","note"),/완료/);
  const forged=row("history",undefined,{review:{status:"closed",events:[event("1","acknowledge")]}});
  assert.throws(()=>parseCapturePage(page(forged),"motor-a"),/일치하지/);
  const repeated=row("history",undefined,{review:{status:"open",events:[event("1","note","a"),event("1","note","b")]}});
  assert.throws(()=>parseCapturePage(page(repeated),"motor-a"),/식별자/);
  assert.equal(reviewNote("note","  확인함 \n"),"확인함");
  assert.equal(reviewNote("acknowledge","무시되는 입력"),"");
  assert.throws(()=>reviewNote("note","   "),/메모를 입력/);
  assert.throws(()=>reviewNote("note","가".repeat(1001)),/1000자/);
  assert.throws(()=>reviewNote("note","bell\u0007"),/제어 문자/);
});

test("reobservation compares only the same subject and assumptions",()=>{
  const saved=parseCapturePage(page(row("acquisition")),"bearing-a").captures[0].outlook;
  assert.deepEqual(compare(saved,acquisition),
    {kind:"same-measurement",bindingRecorded:true,anomalyEvidenceChanged:false});
  assert.equal((compare(saved,{...acquisition,dataVersion:"c".repeat(64)}) as
    {anomalyEvidenceChanged:boolean}).anomalyEvidenceChanged,true);
  assert.deepEqual(compare(saved,{...acquisition,bindingId:"anomaly-b"}),{kind:"different-subject"});
  assert.deepEqual(compare(saved,{...acquisition,timeBasis:"ordinal"}),{kind:"different-subject"});
  assert.deepEqual(compare(saved,{...acquisition,sourceId:"other"}),{kind:"different-subject"});
  assert.deepEqual(compare(saved,history),{kind:"different-subject"});
  assert.deepEqual(compare(saved,{...acquisition,
    conditions:{direction:"upper",management:2.5,end:3},
    outlookSettings:{...settings,changepointPriorScale:0.3}}),
  {kind:"changed-assumptions",changes:["관리 기준","예측 계산 설정"]});
  const later={...acquisition,measurementVersion:"d".repeat(64),record:{first:1,last:70,points:70},
    scenarios:[{id:"current",management:reach("already"),end:reach("expected",2)}]};
  const result=compare(saved,later);
  assert.equal(result.kind,"new-observation");
  if(result.kind!=="new-observation")return;
  assert.equal(result.moved,true);
  assert.deepEqual([result.before,result.after],[64,70]);
  assert.deepEqual(result.limits.map(item=>[item.name,item.before?.state,item.after?.state]),
    [["management","expected","already"],["end","possible","expected"]]);
  const corrected=compare(saved,{...later,record:{first:1,last:64,points:64}});
  assert.equal(corrected.kind==="new-observation"&&corrected.moved,false);
  const unknownBinding={...saved,bindingId:null};
  assert.equal((compare(unknownBinding,later) as {bindingRecorded:boolean}).bindingRecorded,false);
  const savedHistory=parseCapturePage(page(row("history")),"motor-a").captures[0].outlook;
  const sameInstant=compare(savedHistory,{...history,measurementVersion:"e".repeat(64),
    record:{...history.record,last:"2026-10-16T09:00:00+09:00"}});
  assert.equal(sameInstant.kind==="new-observation"&&sameInstant.moved,false);
  assert.deepEqual(compare(savedHistory,{...history,pointId:"point-b"}),{kind:"different-subject"});
});

test("positions stay on their axis and links reopen the same subject and conditions",()=>{
  assert.equal(positionText(64),"측정 순서 #64");
  assert.match(positionText("2026-10-16T00:00:00+00:00"),/2026/);
  const saved=parseCapturePage(page(row("acquisition")),"bearing-a").captures[0].outlook;
  const url=new URL(reobservationUrl({...saved,timeBasis:"assumed",assumedPeriod:30}),"http://localhost");
  assert.deepEqual(Object.fromEntries(url.searchParams),{page:"assets",tab:"outlook",data:"vibration",
    monitor_asset:"bearing-a",acq_forecast_feature:"feature.rms",acq_direction:"upper",
    acq_management:"2.4",acq_end:"3",acq_assumed_period:"30"});
  const savedHistory=parseCapturePage(page(row("history")),"motor-a").captures[0].outlook;
  assert.deepEqual(Object.fromEntries(new URL(reobservationUrl(savedHistory),"http://localhost").searchParams),
    {page:"assets",tab:"outlook",data:"history",monitor_asset:"motor-a",monitor_channel:"R",
      projection_direction:"upper",projection_management:"12"});
  assert.equal(captureUrl("a b","outlook-capture-x"),
    "/web-next/?page=maintenance&monitor_asset=a+b&capture_id=outlook-capture-x");
});

test("today's recomputation is parsed like the archived facts and compared on the same axis",()=>{
  const saved=parseCapturePage(page(row("acquisition")),"bearing-a").captures[0].outlook;
  const later=parseCurrentOutlook({...snapshot("acquisition").outlook,measurement_version:"d".repeat(64),
    record:{first:1,last:70,points:70}},saved);
  assert.equal(compareReobservation(saved,later).kind,"new-observation");
  const same=parseCurrentOutlook(snapshot("acquisition").outlook,saved);
  assert.equal(compareReobservation(saved,same).kind,"same-measurement");
  assert.throws(()=>parseCurrentOutlook({...snapshot("acquisition").outlook,asset_id:"other"},saved),/다른 설비/);
});
