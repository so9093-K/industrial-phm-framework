import assert from "node:assert/strict";
import {test} from "node:test";
import {parseModelExplanations,parseModelReview} from "./model-explanations.ts";
import type {ModelBinding,ModelRun} from "./model-evidence.ts";

const binding={bindingId:"anomaly-a",assetId:"bearing-a"} as ModelBinding;
const run={position:3,runId:"phm-run-3"} as ModelRun;
const RMS="feature.Horizontal_vibration_signals.rms";
function record(extra:Record<string,unknown>={}){
  return {id:"explanation-1",binding_id:"anomaly-a",position:3,analysis_run_id:"phm-run-3",
    status:"complete",model:"local-main",requested_at:"2026-10-17T00:00:00+00:00",
    context:{question:"이전 측정과 비교해 어떤 측정값이 함께 변했는지 설명해 주세요.",
      signal_comparison:{previous_position:2,previous_output:{score:0.4},
        features:[{feature:RMS,label:"수평 진동 RMS",current:3.0,previous:0.6,change:2.4,relative_change_percent:400}]}},
    answer:{summary:"이상 점수가 오르며 수평 진동 RMS가 함께 커졌습니다.",
      observations:[{feature:RMS,relation:"increased"}],next_signals:[],next_step:"두 측정의 원본 파형을 비교해 보세요.",
      checks:{summary_source:"model"}},...extra};
}

test("an explanation shows the comparison the server stored and checked",()=>{
  const [item]=parseModelExplanations({schema_version:1,explanations:[record()]},binding,run);
  assert.equal(item.comparePosition,2);
  assert.equal(item.previousScore,0.4);
  assert.deepEqual(item.features[0],{feature:RMS,label:"수평 진동 RMS",current:3,previous:0.6,relativePercent:400,unit:null});
  assert.equal(item.answer?.source,"model");
  assert.equal(item.answer?.modelUnavailable,false);
});

test("explanations of another run are hidden and unchecked features refused",()=>{
  const other=record({analysis_run_id:"phm-run-old"});
  assert.deepEqual(parseModelExplanations({schema_version:1,explanations:[other]},binding,run),[]);
  const unknown=record({answer:{...record().answer,observations:[{feature:"feature.other.rms",relation:"increased"}]}});
  assert.throws(()=>parseModelExplanations({schema_version:1,explanations:[unknown]},binding,run),/언급한 측정값/);
  const pending=record({status:"pending",answer:null});
  assert.equal(parseModelExplanations({schema_version:1,explanations:[pending]},binding,run)[0].answer,null);
  const fallback=record({answer:{...record().answer,checks:{summary_source:"verified-comparison",model_unavailable:true}}});
  assert.equal(parseModelExplanations({schema_version:1,explanations:[fallback]},binding,run)[0].answer?.modelUnavailable,true);
});

test("a model result's review is either absent or one exact status",()=>{
  assert.deepEqual(parseModelReview({finding_id:null,status:null,events:[]}),{findingId:null,status:null});
  assert.deepEqual(parseModelReview({finding_id:"finding-phm-phm-run-3",status:"open",events:[]}),
    {findingId:"finding-phm-phm-run-3",status:"open"});
  assert.throws(()=>parseModelReview({finding_id:"f",status:"done"}),/검토 상태/);
});
