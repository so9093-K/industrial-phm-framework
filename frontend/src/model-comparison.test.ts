import assert from "node:assert/strict";
import {test} from "node:test";
import {parseComparison,parseRange,shapeText} from "./model-comparison.ts";
import type {ModelBinding,ModelRun} from "./model-evidence.ts";
const binding={bindingId:"b"} as ModelBinding,run={position:8,runId:"r8"} as ModelRun;
const raw={schema_version:1,binding_id:"b",position:8,analysis_run_id:"r8",compare_position:1,previous_analysis_run_id:"r1",previous_score:0.5,
  features:[{feature:"feature.h.rms",label:"수평 RMS",current:4,previous:1,relative_change_percent:300}]};
const flat={count:8,trend:"flat",largest_step:null,level_shift:null};
const range={schema_version:1,binding_id:"b",first:1,last:8,steps:8,points:8,sampled:false,flow_basis:"all-results",
  largest_step_basis:"adjacent-analyzed-results-in-full-range",primary:{...flat,trend:"increasing",steady:true,
    largest_step:{from:3,to:4,direction:"increase"},level_shift:{at:4,direction:"increase"}},features:{"feature.h.rms":flat}};
test("only exact stored comparison and server-described range shapes are displayed",()=>{
  const comparison=parseComparison(raw,binding,run,1);
  assert.equal(comparison.features[0].relativePercent,300);
  const parsed=parseRange(range,binding,run,1,comparison);
  assert.equal(shapeText(parsed.primary),"꾸준히 증가");assert.equal(parsed.primary.shift?.at,4);
  assert.equal(parsed.features[0].label,"수평 RMS");
  for(const mutation of [{binding_id:"other"},{analysis_run_id:"wrong"},{compare_position:2}])
    assert.throws(()=>parseComparison({...raw,...mutation},binding,run,1));
  for(const mutation of [{binding_id:"other"},{first:2},{points:9},{flow_basis:"invented"},{features:{unknown:flat}},
    {primary:{...flat,level_shift:{at:9,direction:"increase"}}}])
    assert.throws(()=>parseRange({...range,...mutation},binding,run,1,comparison));
});
