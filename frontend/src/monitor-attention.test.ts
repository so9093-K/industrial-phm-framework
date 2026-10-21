import assert from "node:assert/strict";
import {test} from "node:test";
import {attentionByAsset,attentionComplete,attentionText,parseDepartures,parsePhmMonitor,refusalReason} from "./monitor-attention.ts";
import {parseSources} from "./operations-status.ts";

function model(extra:Record<string,unknown>){
  return {binding_id:"anomaly-a",asset_id:"bearing-a",step_kind:"acquisition-snapshot",recipe_id:"lstm",
    processing_state:"processed",processing_reason:null,latest_analyzed:{position:3,output:{exceeds_threshold:false}},
    latest_processed:{position:3},latest_review_status:null,...extra};
}
const monitor=(...items:unknown[])=>parsePhmMonitor({schema_version:1,items,truncated:false,review_read_error:false});

test("threshold, refusal, waiting and review notes open the exact place, most urgent first",()=>{
  const phm=monitor(
    model({binding_id:"a",latest_analyzed:{position:7,output:{exceeds_threshold:true}},
      open_interval:{start_position:5,end_position:7,step_count:3,start_event_at:null}}),
    model({binding_id:"b",processing_state:"rejected",processing_reason:"snapshot sha256 mismatch",latest_processed:{position:8}}),
    model({binding_id:"c",processing_state:"pending",latest_review_status:"open"}),
    model({binding_id:"d",asset_id:"motor-1",step_kind:"observation-window"}),
  );
  const groups=attentionByAsset(phm.models,null);
  assert.deepEqual(groups.map(group=>group.assetId),["bearing-a"]);
  assert.deepEqual(groups[0].notes.map(note=>note.kind),["threshold","refusal","pending","review"]);
  assert.match(groups[0].notes[0].href,/model_binding=a&model_position=7/);
  assert.match(groups[0].notes[1].href,/model_position=8/);
  assert.match(groups[0].notes[1].detail,/전달 뒤 원본이 바뀜/);
  assert.match(groups[0].notes[3].href,/page=maintenance/);
  assert.equal(refusalReason("package expects 2 channels"),"모델이 받는 입력 규격과 다름");
});

test("a run of crossings still going on is a change; a latest crossing on its own is said as such",()=>{
  const lstm={package_id:"lstm-pkg",estimator_kind:"lstm-autoencoder-v1"};
  const iforest={package_id:"if-pkg",estimator_kind:"isolation-forest-refit-v1"};
  const both=attentionByAsset(monitor(
    model({binding_id:"a",...lstm,latest_analyzed:{position:123,output:{exceeds_threshold:true}},
      open_interval:{start_position:76,end_position:123,step_count:48,start_event_at:null}}),
    model({binding_id:"b",...iforest,latest_analyzed:{position:123,output:{exceeds_threshold:true}},open_interval:null}),
  ).models,null);
  assert.equal(both[0].notes[0].kind,"threshold");
  assert.equal(both[0].notes[0].detail,"LSTM 오토인코더 측정 순서 #76부터 계속 기준 초과 · 48회 · Isolation Forest는 최근 측정만 기준 초과");
  assert.match(both[0].notes[0].href,/model_binding=a/);
  const lone=attentionByAsset(monitor(
    model({binding_id:"b",...iforest,latest_analyzed:{position:119,output:{exceeds_threshold:true}}}),
  ).models,null);
  assert.deepEqual([lone[0].notes[0].kind,lone[0].notes[0].label,lone[0].notes[0].detail],
    ["crossing","최근 측정에서 모델 기준 초과","Isolation Forest · 연속 초과는 아님"]);
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
    {asset_id:"pump-2",channel:"current_a",label:"전류",unit:"A",distance:96.4,direction:"up",since:"2026-10-01T02:05:57Z"},
    {asset_id:"pump-3",channel:"x"},
  ]});
  assert.equal(departures.length,1);
  const [group]=attentionByAsset([],null,departures);
  assert.equal(group.assetId,"pump-2");
  assert.equal(group.notes[0].kind,"departure");
  assert.match(group.notes[0].detail,/^전류 \(A\) · 기준 변동 폭의 96배 높음 · /);
  assert.match(group.notes[0].href,/tab=anomaly&method=baseline/);
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
