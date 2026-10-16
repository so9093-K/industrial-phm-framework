import assert from "node:assert/strict";
import {test} from "node:test";
import {parseReviewInbox} from "./reviews.ts";
const envelope=(items:unknown[],analysis:unknown[]=[])=>( {
  review_requests:{items,total:items.length,truncated:false},
  phase_unbalance_analyses:{items:analysis,total:analysis.length,truncated:false},
  file_feature_analyses:{items:[],total:0,truncated:false},
  system_error_scopes:[],
});
const item=(evidence:string,asset="motor")=>({
  finding_id:"finding-1",asset_id:asset,analysis_run_id:"run-1",
  status:"open",evidence_ids:[evidence],
});
const record=(asset="motor")=>({
  analysis_run_id:"run-1",evidence_id:"evidence-1",asset_id:asset,
  source_id:"source-1",measurement_point_id:"point-1",
  capability_id:"phase-unbalance",completed_at:"2026-10-10T00:00:00Z",
  data_quality:{state:"usable"},
});
test("review links only exact run, evidence and asset identities",()=>{
  const match=parseReviewInbox(envelope([item("evidence-1")],[record()]));
  assert.equal(match.reviews[0].linked.length,1);
  assert.equal(match.reviews[0].linked[0].pointId,"point-1");
  const wrongAsset=parseReviewInbox(envelope([item("evidence-1")],[record("other")]));
  assert.equal(wrongAsset.reviews[0].linked.length,0);
  assert.deepEqual(wrongAsset.reviews[0].missing,["evidence-1"]);
});
test("truncated or missing evidence cannot be silently treated as complete",()=>{
  const truncated=envelope([item("evidence-1")],[record()]);
  truncated.phase_unbalance_analyses.truncated=true;
  assert.equal(parseReviewInbox(truncated).partial,true);
  assert.equal(parseReviewInbox({}).available,false);
  const lost=envelope([item("evidence-1")]);
  assert.equal(parseReviewInbox(lost).reviews[0].missing.length,1);
});
test("invalid review status and duplicate finding/evidence fail closed",()=>{
  const x=envelope([item("evidence-1"),item("evidence-1")],[record()]);
  assert.throws(()=>parseReviewInbox(x),/중복된 검토/);
  const y=envelope([{...item("evidence-1"),status:"resolved"}]);
  assert.throws(()=>parseReviewInbox(y),/검토 상태/);
  const z=envelope([{...item("evidence-1"),evidence_ids:["evidence-1","evidence-1"]}]);
  assert.throws(()=>parseReviewInbox(z),/중복/);
});
