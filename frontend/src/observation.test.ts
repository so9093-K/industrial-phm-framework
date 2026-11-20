import assert from "node:assert/strict";
import {test} from "node:test";
import {observationLink,parseObservation,readObservation} from "./observation.ts";

const stream={sourceId:"csv-meter",pointId:null,channels:["voltage"],startAt:"2026-11-20T00:00:00Z",endAt:"2026-11-20T01:00:00Z"};
const body={schema_version:1,asset_id:"compressor",channel_ids:["voltage"],snapshot_id:12,
  start_at:"2026-11-20T00:00:00Z",end_at:"2026-11-20T01:00:00Z",bucket_seconds:60,buckets:[],
  latest_stored:[{channel_id:"voltage",source_id:"csv-meter",measurement_point_id:null,event_at:"2026-11-20T00:59:00Z",
    value:0,unit:"V",usable_for_display:true,source_quality:"good"}],reference:null};

test("an observation preserves its measured time, zero and unit and refuses a different source or point",()=>{
  const read=parseObservation(body,"compressor",stream,"voltage");
  assert.equal(read.trend.latest[0].value,0);
  assert.equal(read.trend.latest[0].unit,"V");
  assert.equal(read.trend.latest[0].eventAt,"2026-11-20T00:59:00Z");
  for(const replacement of [{source_id:"other-source"},{measurement_point_id:"other-point"}])
    assert.throws(()=>parseObservation({...body,latest_stored:[{...body.latest_stored[0],...replacement}]},"compressor",stream,"voltage"));
});

test("a fixed observation cannot accept a newer snapshot in its place",async()=>{
  const original=globalThis.fetch;
  globalThis.fetch=async()=>new Response(JSON.stringify(body));
  try{
    await assert.rejects(readObservation("compressor",stream,"voltage",{range:"1h",window:null,snapshot:11,reference:null,anchor:"latest"},new AbortController().signal));
  }finally{globalThis.fetch=original;}
});

test("investigation keeps the selected source, point and fixed reference instead of replacing it with the previous period",()=>{
  const start=Date.parse("2026-11-20T00:00:00Z"),selection={from:start+40*60_000,to:start+50*60_000};
  const reference={from:"2026-11-19T00:00:00Z",to:"2026-11-19T01:00:00Z"};
  const url=new URL(observationLink("compressor","voltage",stream,"meaning-v",{from:start,to:start+3600_000},selection,reference,"compare","전압"),"http://local");
  assert.equal(url.searchParams.get("monitor_source"),"csv-meter");
  assert.equal(url.searchParams.get("monitor_point"),"");
  assert.equal(url.searchParams.get("monitor_interpretation"),"meaning-v");
  assert.equal(url.searchParams.get("compare_a"),reference.from+"~"+reference.to);
  assert.equal(url.searchParams.get("compare_b"),new Date(selection.from).toISOString()+"~"+new Date(selection.to).toISOString());
  assert.equal(url.searchParams.get("observation_follow"),"paused");
});


test("related signals start with the selected signal and a companion from its own stream",()=>{
  const start=Date.parse("2026-11-20T00:00:00Z"),scope={from:start,to:start+600_000};
  const url=new URL(observationLink("compressor","R상전압",{...stream,channels:["무효전력","R상전압","S상전압"]},"voltage-v",scope,scope,null,"relation","전압"),"http://local");
  assert.equal(url.searchParams.get("relation_x"),"R상전압");
  assert.equal(url.searchParams.get("relation_y"),"S상전압");
});

test("editing analysis periods and signals never replaces the original observation viewport or selection",async()=>{
  const {observationOrigin,observationSnapshot,withObservation}=await import("./observation-context.ts");
  const {tabSelectionUrl,assetTabUrl}=await import("./routes.ts");
  const start=Date.parse(stream.startAt),window={from:start,to:start+3600_000},selection={from:start+40*60_000,to:start+45*60_000};
  const url=new URL(observationLink("compressor","voltage",stream,"meaning-v",window,selection,null,"compare","전압"),"http://local");
  url.searchParams.set("observation_snapshot","12");
  const before=observationOrigin(url.searchParams,"compressor");
  assert.equal(Date.parse(before!.window.to)-Date.parse(before!.window.from),3600_000);
  for(const key of ["monitor_from","monitor_to","monitor_pick","compare_a","compare_b","monitor_channel","monitor_source","monitor_point"])
    url.searchParams.set(key,"edited-in-analysis");
  const back=new URL(tabSelectionUrl(assetTabUrl("compressor","summary"),url.href),url.origin);
  assert.deepEqual(observationOrigin(back.searchParams,"compressor"),before);
  assert.deepEqual(before!.selection,selection);
  assert.equal(observationSnapshot(back.searchParams,"compressor"),12);
  const point=new URL(assetTabUrl("compressor","signals",null,null,"current"),url.origin);
  point.searchParams.set("monitor_from","selected-scatter-point");
  const linked=new URL(withObservation(point.href,back.href,"compressor"),url.origin);
  assert.equal(linked.searchParams.get("monitor_from"),"selected-scatter-point");
  assert.equal(linked.searchParams.get("monitor_channel"),"current");
  assert.deepEqual(observationOrigin(linked.searchParams,"compressor"),before);
  assert.equal(observationOrigin(back.searchParams,"other-asset"),null);
  assert.equal(observationSnapshot(back.searchParams,"other-asset"),null);
  back.searchParams.set("observation_snapshot","oops");
  assert.throws(()=>observationSnapshot(back.searchParams,"compressor"));
});

test("every detailed history read sends the selected snapshot and refuses a different version",async()=>{
  const {readTrends}=await import("./history.ts");
  const {readProfile}=await import("./comparison.ts");
  const {readRelation}=await import("./relation.ts");
  const original=globalThis.fetch,signal=new AbortController().signal;
  const periods={a:{from:"2026-11-19T00:00:00Z",to:"2026-11-19T01:00:00Z"},b:{from:stream.startAt,to:stream.endAt}};
  const paths:string[]=[];
  globalThis.fetch=async input=>{
    const url=new URL(String(input),"http://local");
    assert.equal(url.searchParams.get("snapshot"),"11");paths.push(url.pathname);
    return new Response(JSON.stringify(body));
  };
  try{
    for(const read of [()=>readTrends("compressor",["voltage"],periods.b,"latest",signal,"csv-meter",11),
      ()=>readProfile("compressor","voltage",periods,signal,null,11),
      ()=>readRelation("compressor","voltage","current",periods,signal,11)])
      await assert.rejects(read(),/선택한 관측의 분석 결과/);
    assert.deepEqual(paths,["/api/v1/history/trend","/api/v1/explore/profile","/api/v1/explore/relation"]);
  }finally{globalThis.fetch=original;}
});
