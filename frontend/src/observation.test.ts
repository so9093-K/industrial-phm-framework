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
