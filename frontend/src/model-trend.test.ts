import assert from "node:assert/strict";
import {test} from "node:test";
import type {ModelBinding} from "./model-evidence.ts";
import {mergeSeries,parseWaveform,parseWindow,trendSummary,type TrendPoint} from "./model-trend.ts";

const binding={bindingId:"anomaly-a",stepKind:"acquisition-snapshot"} as ModelBinding;
const step=(position:number,state:"analyzed"|"skipped",score?:number)=>({position,state,step_key:"k"+position,
  analysis_run_id:"run-"+position,change_seq:position,reason:state==="skipped"?"warm-up":null,
  event_start:null,output:state==="analyzed"?{score,threshold:2,exceeds_threshold:(score??0)>2}:{}});

test("stored scores merge by input order; a skipped step has no score",()=>{
  const known=new Map<number,TrendPoint>();
  const page=mergeSeries({schema_version:1,binding:{binding_id:"anomaly-a"},change_seq:3,has_more:false,
    steps:[step(1,"skipped"),step(2,"analyzed",0.5),step(3,"analyzed",3.1)],
    intervals:[{start_position:3,end_position:3,step_count:1,peak_score:3.1,open:true}]},binding,known);
  assert.equal(page.cursor,3);
  assert.equal(known.get(1)!.score,null);
  assert.equal(known.get(3)!.exceeds,true);
  assert.deepEqual(trendSummary({points:[...known.values()],intervals:page.intervals,truncated:false}),
    {analyzed:2,skipped:1,exceeded:1,open:1});
  assert.throws(()=>mergeSeries({schema_version:1,binding:{binding_id:"other"},steps:[],intervals:[]},binding,known),/형식/);
});

test("raw input previews keep unreadable and unusable values apart from data",()=>{
  assert.deepEqual(parseWaveform({position:3,available:false,reason:"sha mismatch"},3),{available:false,reason:"sha mismatch"});
  const wave=parseWaveform({position:3,available:true,file_name:"3.csv",sampling_rate_hz:25600,sample_count:800,samples_per_bin:2,
    channels:[{channel:"h",envelope:[[-1,1],[-2,2]]}]},3);
  assert.equal(wave.available&&wave.channels[0].bands.length,2);
  assert.throws(()=>parseWaveform({position:4,available:true},3),/형식/);
  const window=parseWindow({position:7,available:true,start:"2026-10-17T00:00:00Z",end:"2026-10-17T00:05:00Z",
    channels:[{channel_id:"current_r",unit:"A",points:[{at:"2026-10-17T00:00:01Z",value:5,quality:"good"},
      {at:"2026-10-17T00:00:02Z",value:9,quality:"conflict"}]}]},7);
  assert.deepEqual(window.available&&window.channels[0].points.map(p=>p.value),[5,null]);
});
