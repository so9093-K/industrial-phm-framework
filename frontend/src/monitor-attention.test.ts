import assert from "node:assert/strict";
import {test} from "node:test";
import {assetChecks,attentionByAsset,departureSignalHref,attentionComplete,attentionText,modelFact,noteFact,parseDepartures,parsePhmMonitor,refusalReason} from "./monitor-attention.ts";
import {parseSources} from "./operations-status.ts";

function model(extra:Record<string,unknown>){
  return {binding_id:"anomaly-a",asset_id:"bearing-a",source_id:"bench",measurement_point_id:null,step_kind:"acquisition-snapshot",recipe_id:"pca",
    processing_state:"processed",processing_reason:null,latest_analyzed:{position:3,output:{exceeds_threshold:false}},
    latest_processed:{position:3},latest_review_status:null,...extra};
}
const monitor=(...items:unknown[])=>parsePhmMonitor({schema_version:1,items,truncated:false});

test("PHM alerts exclude optional review states while preserving actionable model events",()=>{
  const phm=monitor(
    model({binding_id:"a",latest_analyzed:{position:7,output:{exceeds_threshold:true}},
      open_interval:{start_position:5,end_position:7,step_count:3,start_event_at:null}}),
    model({binding_id:"b",processing_state:"rejected",processing_reason:"snapshot sha256 mismatch",latest_processed:{position:8}}),
    model({binding_id:"c",processing_state:"pending",latest_review_status:"open"}),
    model({binding_id:"d",asset_id:"motor-1",step_kind:"observation-window"}),
  );
  const groups=attentionByAsset(phm.models,null);
  assert.deepEqual(groups.map(group=>group.assetId),["bearing-a"]);
  assert.deepEqual(groups[0].notes.map(note=>note.kind),["threshold","refusal","pending"]);
  assert.match(groups[0].notes[0].href,/model_binding=a&model_position=7/);
  assert.match(groups[0].notes[1].href,/model_position=8/);
  assert.match(groups[0].notes[1].detail,/전달 뒤 원본이 바뀜/);
  assert.equal(groups[0].notes.some(note=>note.href.includes("page=maintenance")),false);
  assert.equal(refusalReason("package expects 2 channels"),"모델이 받는 입력 규격과 다름");
});

test("an open human-review status alone does not make an asset need PHM attention",()=>{
  const reports=monitor(model({latest_review_status:"open"}));
  assert.deepEqual(attentionByAsset(reports.models,null),[]);
  const sources={assessedAt:null,items:[],truncated:false,readErrors:[],liveErrors:[]};
  assert.equal(attentionComplete(reports,sources,true),true);
});

test("a run of crossings still going on is a change; a latest crossing on its own is said as such",()=>{
  const pca={package_id:"pca-pkg",estimator_kind:"pca-residual-v1"};
  const iforest={package_id:"if-pkg",estimator_kind:"isolation-forest-refit-v1"};
  const both=attentionByAsset(monitor(
    model({binding_id:"a",...pca,latest_analyzed:{position:123,output:{exceeds_threshold:true}},
      open_interval:{start_position:76,end_position:123,step_count:48,start_event_at:null}}),
    model({binding_id:"b",...iforest,latest_analyzed:{position:123,output:{exceeds_threshold:true}},open_interval:null}),
  ).models,null);
  assert.equal(both[0].notes[0].kind,"threshold");
  assert.equal(both[0].notes[0].detail,"PCA 잔차 76번째 측정 이후 기준 초과 48회 · 최근 측정은 기준 초과 · Isolation Forest는 최근 측정에서 기준 초과");
  assert.match(both[0].notes[0].href,/model_binding=a/);
  const lone=attentionByAsset(monitor(
    model({binding_id:"b",...iforest,latest_analyzed:{position:119,output:{exceeds_threshold:true}}}),
  ).models,null);
  assert.deepEqual([lone[0].notes[0].kind,lone[0].notes[0].label,lone[0].notes[0].detail],
    ["crossing","최근 측정에서 모델 기준 초과","Isolation Forest · 그 전 기준 초과 기록은 점수 추이에서 확인"]);
});

test("an interval kept open across an allowed quiet measurement stays visible",()=>{
  const open=monitor(model({latest_analyzed:{position:5,output:{exceeds_threshold:false}},
    open_interval:{start_position:3,end_position:4,step_count:2,start_event_at:null}})).models;
  const [group]=attentionByAsset(open,null);
  assert.equal(group.notes[0].kind,"threshold");
  assert.match(group.notes[0].detail,/3번째 측정 이후 기준 초과 2회 · 최근 측정은 기준 이하/);
  assert.match(group.notes[0].href,/model_position=5/);
  assert.deepEqual(attentionByAsset(open.map(item=>({...item,ongoing:null})),null),[]);
});

test("only a collection someone asked to run is flagged when it stops receiving",()=>{
  const sources=parseSources({schema_version:1,meaning:"registration-does-not-imply-accepted-receipt-or-live-connection",
    sources:{items:[
      {source_id:"s1",name:"Live",source_type:"opcua",asset_id:"pump-1",lifecycle_state:"active",collection_desired_state:"running",
        last_live_receive_fresh:false},
      {source_id:"s2",name:"Paused",source_type:"opcua",asset_id:"pump-2",lifecycle_state:"paused",collection_desired_state:"running",
        last_live_receive_fresh:false},
      {source_id:"s3",name:"Stopped",source_type:"opcua",asset_id:"pump-3",lifecycle_state:"active",collection_desired_state:"stopped",
        last_live_receive_fresh:false},
      {source_id:"s4",name:"Live 2",source_type:"opcua",asset_id:"pump-1",lifecycle_state:"active",collection_desired_state:"running",
        last_live_receive_fresh:false},
    ],total:4,truncated:false},read_error_scopes:[],live_evidence_error_scopes:[]}).items;
  const groups=attentionByAsset([],sources);
  assert.deepEqual(groups.map(group=>[group.assetId,group.notes[0].kind]),[["pump-1","receipt"]]);
  // Two silent connections of one asset are two notes, each with its own key in the list.
  assert.deepEqual(groups[0].notes.map(note=>[note.id,note.detail.split(" · ")[0]]),[["receipt:s1","Live"],["receipt:s4","Live 2"]]);
  assert.throws(()=>parsePhmMonitor({schema_version:1,items:[model({processing_state:"healthy"})]}),/형식/);
});

test("a stored signal that ends far from its baseline asks for a look and opens that signal", () => {
  const departures=parseDepartures({schema_version:1,items:[
    {asset_id:"pump-2",channel:"current_a",label:"전류",unit:"A",distance:96.4,direction:"up",since:"2020-10-01T02:05:57Z",last_at:"2020-10-02T02:05:57Z",
      key:"record-a",source_id:"source-b",measurement_point_id:null,interpretation_id:"b".repeat(64),record:{from:"2020-09-01T00:00:00Z",to:"2020-10-02T02:05:58Z"},
      usual:{low:42.1,high:73.2}},
    {asset_id:"pump-3",channel:"x"},
  ]});
  assert.equal(departures.length,1);
  const [group]=attentionByAsset([],null,departures);
  assert.equal(group.assetId,"pump-2");
  assert.equal(group.notes[0].kind,"departure");
  assert.equal(group.notes[0].label,"전류 · 기준 범위보다 높아짐");
  assert.match(group.notes[0].detail,/비교 범위 42\.1~73\.2 A.*10월 1일\(목\) 11:05/);
  assert.match(group.notes[0].href,/tab=signals/);
  const link=new URL(group.notes[0].href,"http://local");
  assert.equal(link.searchParams.get("monitor_source"),"source-b");
  assert.equal(link.searchParams.get("monitor_point"),"");
  assert.equal(link.searchParams.get("monitor_interpretation"),"b".repeat(64));
  assert.equal(link.searchParams.get("record_key"),"record-a");
  assert.equal(link.searchParams.get("monitor_range"),"window");
  assert.equal(group.notes[0].departure?.lastAt,"2020-10-02T02:05:57Z");
  assert.match(group.notes[0].href,/monitor_channel=current_a/);
});

test("a partial or failed attention read never turns an unverified zero into no items", () => {
  assert.equal(attentionText(0,"ready"),"없음");
  for (const state of ["partial","failed","loading"] as const)
    assert.doesNotMatch(attentionText(0,state),/없음/);
  assert.equal(attentionText(2,"partial"),"최소 2건 · 일부 미확인");
  const sources={assessedAt:null,items:[],truncated:false,readErrors:[],liveErrors:[]};
  assert.equal(attentionComplete(monitor(),sources,true),true);
  assert.equal(attentionComplete(monitor(),null,true),false);
  assert.equal(attentionComplete(monitor(),sources,false),false);
  assert.equal(attentionComplete({...monitor(),truncated:true},sources,true),false);
  assert.equal(attentionComplete(monitor(),{...sources,readErrors:["registry"]},true),false);
});


test("a long change opens its start within the signal limit; missing measurement clocks are not guessed",()=>{
  const item={assetId:"pump",channel:"current",label:null,unit:null,distance:4,direction:"up" as const,since:"2020-01-01T00:00:00Z",lastAt:"2020-04-01T00:00:00Z",usual:null};
  const url=new URL(departureSignalHref(item),"http://local");
  const [start,end]=url.searchParams.get("monitor_pick")!.split("~").map(Date.parse);
  assert.equal(start,Date.parse(item.since));
  assert.equal(end-start,31*86400000);
  const missing=new URL(departureSignalHref({...item,lastAt:null}),"http://local");
  assert.equal(missing.searchParams.has("monitor_pick"),false);
  assert.equal(missing.searchParams.get("monitor_channel"),"current");
});

test("the overview row says which models crossed at the latest measurement, by name", () => {
  const pca={package_id:"pca-pkg",estimator_kind:"pca-residual-v1"};
  const iforest={package_id:"if-pkg",estimator_kind:"isolation-forest-refit-v1"};
  const at=(exceeds:boolean)=>({latest_analyzed:{position:123,output:{exceeds_threshold:exceeds}}});
  assert.equal(modelFact(monitor(model({binding_id:"a",...pca,...at(true)}),model({binding_id:"b",...iforest,...at(true)})).models),
    "마지막 분석 · 123번째 측정 기준 초과 · PCA 잔차, Isolation Forest");
  assert.equal(modelFact(monitor(model({binding_id:"a",...pca,...at(true)}),model({binding_id:"b",...iforest,...at(false)})).models),
    "마지막 분석 · 123번째 측정 기준 초과 · PCA 잔차 (기준 이하 · Isolation Forest)");
  assert.equal(modelFact(monitor(model({binding_id:"b",...iforest,...at(false)})).models), "마지막 분석 · 123번째 측정 기준 이하 · Isolation Forest");
  // 아직 분석하지 않은 모델은 결과로 말하지 않는다. 대기 중이라는 사실은 확인 항목이 말한다.
  const waiting=monitor(model({binding_id:"c",...iforest,processing_state:"pending",latest_analyzed:null}));
  assert.equal(modelFact(waiting.models), null);
  const [group]=attentionByAsset(waiting.models,null);
  assert.equal(noteFact(group.notes[0]), "모델 · 새 입력 분석 대기");
  const checks=assetChecks(waiting.models,[group],"ready");
  assert.deepEqual(Object.keys(checks.models),["bearing-a"]);
  assert.equal(checks.notes["bearing-a"][0].kind,"pending");
  // 모델 기준 초과는 모델 줄이 말하므로 확인 항목 줄로 다시 쓰지 않는다.
  const [crossed]=attentionByAsset(monitor(model({binding_id:"a",...pca,...at(true)})).models,null);
  assert.equal(noteFact(crossed.notes[0]), null);
});

test("last results from different measurements or streams are named separately",()=>{
  const first=model({binding_id:"a",estimator_kind:"pca-residual-v1",latest_analyzed:{position:123,output:{exceeds_threshold:true}}});
  const second=model({binding_id:"b",estimator_kind:"isolation-forest-refit-v1",latest_analyzed:{position:120,output:{exceeds_threshold:false}}});
  assert.equal(modelFact(monitor(first,second).models),
    "모델별 마지막 분석 · PCA 잔차 · 123번째 측정: 기준 초과 / Isolation Forest · 120번째 측정: 기준 이하");
  for(const scope of [{source_id:"another-source"},{measurement_point_id:"other-point"},{source_id:null}]){
    const sameNumber={...second,...scope,latest_analyzed:{position:123,output:{exceeds_threshold:false}}};
    assert.match(modelFact(monitor(first,sameNumber).models)!,/^모델별 마지막 분석/);
  }
});

test("windows ending together are combined only when their measured intervals match",()=>{
  const end="2020-10-22T14:50:00Z",position=Date.parse(end)*1000;
  const window=(start:string|null,exceeds:boolean)=>model({binding_id:exceeds?"a":"b",step_kind:"history-window",
    estimator_kind:exceeds?"pca-residual-v1":"isolation-forest-refit-v1",
    latest_analyzed:{position,event_start:start,event_end:end,output:{exceeds_threshold:exceeds}}});
  const first=window("2020-10-22T14:40:00Z",true);
  for(const start of ["2020-10-22T14:30:00Z",null])
    assert.match(modelFact(monitor(first,window(start,false)).models)!,/^모델별 마지막 분석/);
  const different=modelFact(monitor(first,window("2020-10-22T14:30:00Z",false)).models)!;
  assert.match(different,/23:40:00 ~ 23:50:00/);
  assert.match(different,/23:30:00 ~ 23:50:00/);
  assert.match(modelFact(monitor(first,window("2020-10-22T23:40:00+09:00",false)).models)!,/^마지막 분석/);
});

test("short equipment statuses combine only models of the same measured input",()=>{
  const first=model({binding_id:"a",latest_analyzed:{position:123,output:{exceeds_threshold:true}}});
  const second=model({binding_id:"b",latest_analyzed:{position:123,output:{exceeds_threshold:false}}});
  assert.equal(modelFact(monitor(first,second).models,true),"마지막 분석 · 기준 초과 결과 있음");
  assert.equal(modelFact(monitor(first,{...second,latest_analyzed:{position:120,output:{exceeds_threshold:false}}}).models,true),"모델마다 분석한 측정이 다름");
  assert.equal(modelFact(monitor(first,{...second,source_id:"another-source"}).models,true),"모델마다 분석한 측정이 다름");
  assert.equal(modelFact(monitor(second).models,true),"마지막 분석 · 모델 기준 이하");
});

test("a latest window at an operating level the model did not learn is not an input refusal", () => {
  const [item]=monitor(model({step_kind:"history-window",processing_state:"unjudged",processing_reason:"operating level not learned: 11 A",
    latest_processed:{position:4,reason:"operating level not learned: 11 A"}})).models;
  assert.equal(item.state,"unjudged");
  assert.deepEqual(attentionByAsset([item],null),[]);
});
