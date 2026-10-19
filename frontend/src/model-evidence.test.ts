import assert from "node:assert/strict";
import {test} from "node:test";
import {modelName,modelNames,scoreSummary,parseModelBindings,parseModelTrace,parseModelRun} from "./model-evidence.ts";
import type {ModelBinding} from "./model-evidence.ts";
const digest="a".repeat(64);
const binding=()=>({
  binding_id:"bind-a",package_id:"model-v1",source_id:"source-a",asset_id:"bearing-a",
  measurement_point_id:null,step_kind:"acquisition-snapshot",recorded_replay:true,
  health:"ok",package:{package_id:"model-v1",recipe_id:"research-v1",output:{task:"anomaly-score"}},
  latest_analyzed:{position:4,state:"analyzed"},
  latest_processed:{position:4,state:"analyzed"},
});
const bindings=()=>({schema_version:1,change_seq:10,bindings:[binding()]});
const step=()=>({
  position:4,step_key:"snapshot:4",state:"analyzed",reason:null,
  analysis_run_id:"model-run-a",change_seq:10,replay:true,
  input_reference:{kind:"acquisition-snapshot",source_id:"source-a",asset_id:"bearing-a",
    ordinal:4,sha256:digest},
  event_start:null,event_end:null,processed_at:"2026-10-16T00:00:00+00:00",
  output:{score:0.75,exceeds_threshold:false},features:{"feature.rms":0.12},
});
const pointers=()=>({schema_version:1,binding_id:"bind-a",limit:64,steps:[step()]});
test("only the selected asset's explicitly bound model appears",()=>{
  const result=parseModelBindings({...bindings(),bindings:[binding(),{...binding(),
    binding_id:"bind-b",asset_id:"other"}]},"bearing-a");
  assert.equal(result.length,1);
  assert.equal(result[0].bindingId,"bind-a");
  assert.equal(result[0].lastAnalyzed,4);
  assert.equal(result[0].task,"anomaly-score");
  assert.throws(()=>parseModelBindings({...bindings(),bindings:[binding(),binding()]},"bearing-a"),/두 번/);
});
test("selected immutable run matches binding, trace identity, input ordinal and hash",()=>{
  const model=parseModelBindings(bindings(),"bearing-a")[0];
  const trace=parseModelTrace(pointers(),model);
  const result=parseModelRun({schema_version:1,binding_id:"bind-a",step:step()},model,trace.steps[0]);
  assert.equal(result.runId,"model-run-a");
  assert.equal(result.inputReference.sha256,digest);
  assert.equal(result.replay,true);
  assert.equal(result.evidenceKind,"acquisition-snapshot");
});
test("cross-asset, forged run, source or ordinal evidence cannot render",()=>{
  const model=parseModelBindings(bindings(),"bearing-a")[0];
  const pointer=parseModelTrace(pointers(),model).steps[0];
  assert.throws(()=>parseModelRun({schema_version:1,binding_id:"other",step:step()},model,pointer),/적용 모델/);
  assert.throws(()=>parseModelRun({schema_version:1,binding_id:"bind-a",step:{...step(),
    analysis_run_id:"other"}},model,pointer),/모델 실행 기록/);
  assert.throws(()=>parseModelRun({schema_version:1,binding_id:"bind-a",step:{...step(),
    input_reference:{...step().input_reference,source_id:"other"}}},model,pointer),/출처/);
  assert.throws(()=>parseModelRun({schema_version:1,binding_id:"bind-a",step:{...step(),
    input_reference:{...step().input_reference,ordinal:3}}},model,pointer),/입력 파일/);
  assert.throws(()=>parseModelRun({schema_version:1,binding_id:"bind-a",step:{...step(),
    input_reference:{...step().input_reference,sha256:"unknown"}}},model,pointer),/입력 파일/);
});
test("window evidence requires exactly matching source, point and digest",()=>{
  const raw={...binding(),step_kind:"observation-window",measurement_point_id:"point-a"};
  const model=parseModelBindings({...bindings(),bindings:[raw]},"bearing-a")[0];
  const state={...step(),position:100,input_reference:{
    kind:"observation-window",source_id:"source-a",asset_id:"bearing-a",
    measurement_point_id:"point-a",window_id:"window-a",input_digest:digest,
  }};
  const pointer=parseModelTrace({...pointers(),steps:[state]},model).steps[0];
  assert.equal(parseModelRun({schema_version:1,binding_id:"bind-a",step:state},model,pointer)
    .inputReference.window_id,"window-a");
  const wrong={...state,input_reference:{...state.input_reference,measurement_point_id:"other"}};
  assert.throws(()=>parseModelRun({schema_version:1,binding_id:"bind-a",step:wrong},
    model,pointer),/측정 위치/);
});
test("skipped steps remain explicit and cannot be interpreted as scored runs",()=>{
  const model=parseModelBindings(bindings(),"bearing-a")[0];
  const skipped={...step(),state:"skipped",reason:"sequence warm-up",
    features:null,output:{}};
  const pointer=parseModelTrace({...pointers(),steps:[skipped]},model).steps[0];
  const result=parseModelRun({schema_version:1,binding_id:"bind-a",step:skipped},model,pointer);
  assert.equal(result.state,"skipped");
  assert.equal(result.reason,"sequence warm-up");
  assert.deepEqual(result.output,{});
  assert.throws(()=>parseModelRun({schema_version:1,binding_id:"bind-a",step:{
    ...skipped,features:{"feature.rms":0.7}
  }},model,pointer),/제외/);
});
test("trace does not accept duplicated positions, other bindings or too many steps",()=>{
  const model=parseModelBindings(bindings(),"bearing-a")[0];
  assert.throws(()=>parseModelTrace({...pointers(),binding_id:"other"},model),/적용 모델/);
  assert.throws(()=>parseModelTrace({...pointers(),steps:[step(),step()]},model),/두 번/);
  assert.throws(()=>parseModelTrace({...pointers(),steps:Array(65).fill(step())},model),/목록/);
});

test("a stored score is summarized only from the fields the output carries",()=>{
  assert.deepEqual(scoreSummary({score:2.169,threshold:2,exceeds_threshold:true}),
    {score:2.169,threshold:2,exceeds:true});
  assert.deepEqual(scoreSummary({score:0.5}),{score:0.5,threshold:null,exceeds:null});
  assert.deepEqual(scoreSummary({score:"high",threshold:Number.NaN,exceeds_threshold:"yes"}),
    {score:null,threshold:null,exceeds:null});
});

test("a connected model is named by its recipe, or its package without the content hash",()=>{
  assert.equal(modelName({recipeId:"rms-score-v1",packageId:"rms-score-v1-24d7cd85d97f"}),"rms-score-v1");
  assert.equal(modelName({recipeId:null,packageId:"synthetic-rms-score-v1-24d7cd85d97f"}),"synthetic-rms-score-v1");
  assert.equal(modelName({recipeId:null,packageId:"plain-package"}),"plain-package");
});

test("a model of a known method is named by the method; two of one method keep their recipe",()=>{
  const lstm={recipeId:"xjtu-lstm-autoencoder-fold-1-development-v1",packageId:"p-0268a8265bdf",estimatorKind:"lstm-autoencoder-v1"};
  assert.equal(modelName(lstm),"LSTM 오토인코더");
  assert.equal(modelName({...lstm,estimatorKind:"future-kind-v1"}),lstm.recipeId);
  const one={bindingId:"a",recipeId:"site-a-iforest",packageId:"pa",estimatorKind:"isolation-forest-refit-v1"} as ModelBinding;
  const two={...one,bindingId:"b",recipeId:"site-b-iforest"};
  const lone={...one,bindingId:"c",estimatorKind:"lstm-autoencoder-v1"};
  assert.deepEqual([...modelNames([one,two,lone]).values()],
    ["Isolation Forest · site-a-iforest","Isolation Forest · site-b-iforest","LSTM 오토인코더"]);
});
