import assert from "node:assert/strict";
import {test} from "node:test";
import {parseAnalysisRecords} from "./analysis-records.ts";

const phase={analysis_run_id:"run-1",evidence_id:"evidence-1",asset_id:"motor-7",source_id:"bus",
  measurement_point_id:"panel",capability_id:"phase-unbalance",algorithm_version:"v1",
  observed_start_at:"2026-10-16T00:00:00Z",observed_end_at:"2026-10-16T00:05:00Z",completed_at:"2026-10-16T00:06:00Z",
  data_quality:{state:"warning",issue_codes:["gap"]},
  quantities:[{quantity:"current",unit:"%",evaluated_samples:300,excluded_samples:{missing:2},
    median_percent:1.2,p95_percent:2.5,max_percent:3.1,max_at:"2026-10-16T00:03:00Z"}]};
const file={analysis_run_id:"run-2",evidence_id:"evidence-2",asset_id:"pump-1",source_id:"csv",
  measurement_point_id:null,capability_id:"file-features",feature_set_id:"stats-v1",
  observed_start_at:null,observed_end_at:null,completed_at:"2026-10-17T00:00:00Z",
  data_quality:{state:"pass",issue_codes:[]},source_snapshot_sha256:"a".repeat(64),
  features:[{name:"x.mean",value:0.5},{name:"x.rms",value:null}]};
const list=(...items:unknown[])=>({items,total:items.length,truncated:false});

test("stored analyses keep their exact identity, newest first",()=>{
  const parsed=parseAnalysisRecords({phase_unbalance_analyses:list(phase),file_feature_analyses:list(file),
    skipped_analysis_attempts:list({asset_id:"motor-7",source_id:"bus",measurement_point_id:"panel",
      capability_id:"phase-unbalance",reason:"phase binding missing",observed_start_at:null,observed_end_at:null,
      recorded_at:"2026-10-16T00:07:00Z"})});
  assert.deepEqual(parsed.records.map(item=>item.runId),["run-2","run-1"]);
  assert.equal(parsed.records[1].quality,"warning");
  assert.deepEqual(parsed.records[1].quantities[0].excluded,{missing:2});
  assert.equal(parsed.records[0].features[1].value,null);
  assert.equal(parsed.records[0].sha256,"a".repeat(64));
  assert.equal(parsed.skipped[0].reason,"phase binding missing");
  assert.equal(parsed.truncated,false);
  assert.equal(parsed.skippedComplete,true);
});

test("a missing or partial list is never shown as no analyses",()=>{
  assert.equal(parseAnalysisRecords({phase_unbalance_analyses:list(phase)}).available,false);
  const partial=parseAnalysisRecords({phase_unbalance_analyses:{...list(phase),truncated:true},
    file_feature_analyses:list(),skipped_analysis_attempts:list()});
  assert.equal(partial.truncated,true);
  const noSkipped=parseAnalysisRecords({phase_unbalance_analyses:list(phase),file_feature_analyses:list()});
  assert.equal(noSkipped.truncated,false);
  assert.equal(noSkipped.skippedComplete,false);
  assert.throws(()=>parseAnalysisRecords({phase_unbalance_analyses:list(phase,phase),
    file_feature_analyses:list(),skipped_analysis_attempts:list()}),/두 번/);
  assert.throws(()=>parseAnalysisRecords({phase_unbalance_analyses:list({...phase,evidence_id:""}),
    file_feature_analyses:list()}),/분석 근거/);
});
