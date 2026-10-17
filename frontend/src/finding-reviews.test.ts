import assert from "node:assert/strict";
import {test} from "node:test";
import {findingUrl,modelResultUrl,parseFindingReviews} from "./finding-reviews.ts";

const uuid=(n:string)=>n.repeat(8)+"-"+n.repeat(4)+"-4"+n.repeat(3)+"-8"+n.repeat(3)+"-"+n.repeat(12);
const event=(n:string,action:string,note="")=>({event_id:"finding-review-event-"+uuid(n),action,note,
  recorded_at:"2026-10-17T00:0"+n+":00+00:00"});
function item(extra:Record<string,unknown>={}){
  return {finding_id:"finding-1",subject:"analysis",analysis_run_id:"run-1",evidence_ids:["evidence-1"],
    capability_id:"phase-unbalance",measurement_point_id:"bus",observed_at:"2026-10-16T09:00:00+00:00",
    status:"open",model:null,events:[],events_total:0,...extra};
}
const page=(...items:unknown[])=>({schema_version:1,asset_id:"motor-a",
  meaning:"human-review-records-not-maintenance-or-diagnosis",
  reviews:{items,total:items.length,truncated:false}});

test("analysis and model reviews keep their exact subject and history",()=>{
  const model=item({finding_id:"finding-phm-run-2",subject:"model",analysis_run_id:"run-2",
    evidence_ids:["phm-result-run-2"],model:{binding_id:"anomaly-a",position:7},status:"acknowledged",
    events:[event("1","note","배선 확인"),event("2","acknowledge")],events_total:2});
  const parsed=parseFindingReviews(page(item(),model),"motor-a");
  assert.equal(parsed.items[0].subject,"analysis");
  assert.equal(parsed.items[0].model,null);
  assert.deepEqual(parsed.items[1].model,{bindingId:"anomaly-a",position:7});
  assert.deepEqual(parsed.items[1].events.map(e=>e.note),["배선 확인",""]);
});

test("a review list of another asset or a forged history is refused",()=>{
  assert.throws(()=>parseFindingReviews(page(item()),"motor-b"),/다른 설비/);
  assert.throws(()=>parseFindingReviews(page(item({status:"closed",events:[event("1","note","a")],events_total:1})),
    "motor-a"),/일치하지/);
  // Only part of a long history is shown: the status cannot be replayed, but stays bounded.
  assert.equal(parseFindingReviews(page(item({status:"closed",events:[event("1","close")],events_total:3})),
    "motor-a").items[0].status,"closed");
  assert.throws(()=>parseFindingReviews(page(item({model:{binding_id:"m",position:1}})),"motor-a"),/모델 결과 위치/);
  assert.throws(()=>parseFindingReviews(page(item({events:[{...event("1","note","a"),event_id:"other"}],
    events_total:1})),"motor-a"),/식별자/);
  assert.throws(()=>parseFindingReviews(page(item(),item()),"motor-a"),/식별자/);
  const truncated={...page(item()),reviews:{items:[item()],total:3,truncated:false}};
  assert.throws(()=>parseFindingReviews(truncated,"motor-a"),/항목 수/);
});

test("review links open the queue item or the exact stored model result",()=>{
  const queue=new URL(findingUrl("a & b","finding-1"),"http://local");
  assert.equal(queue.searchParams.get("page"),"maintenance");
  assert.equal(queue.searchParams.get("finding_id"),"finding-1");
  const model=new URL(modelResultUrl("a & b",{bindingId:"anomaly-a",position:7}),"http://local");
  assert.equal(model.searchParams.get("tab"),"anomaly");
  assert.equal(model.searchParams.get("method"),"model");
  assert.equal(model.searchParams.get("model_binding"),"anomaly-a");
  assert.equal(model.searchParams.get("model_position"),"7");
});
