import assert from "node:assert/strict";
import {test} from "node:test";
import {modelTitle,noModelReason,parseModelChoices} from "./model-connect.ts";

const stream={source_id:"bench",measurement_point_id:null,kind:"acquisition-snapshot",name:"bench",channels:["h","v"],
  sampling_rate_hz:25600,input_state:"stored-input"};
function body(packages:unknown[],streams:unknown[]=[stream]){
  return {schema_version:1,asset_id:"bearing-a",meaning:"model-packages-and-asset-input-streams",packages,streams};
}
const pkg=(id:string,candidate:Record<string,unknown>,task="anomaly-score")=>({package_id:id,recipe_id:"lstm-"+id,task,
  candidates:[{source_id:"bench",measurement_point_id:null,compatible:true,connected:false,reason:null,...candidate}]});

test("only anomaly packages that fit and are not connected yet are offered",()=>{
  const choices=parseModelChoices(body([
    pkg("a",{}),pkg("b",{connected:true}),pkg("c",{compatible:false,reason:"채널 구성이 다릅니다"}),pkg("d",{},"forecast"),
  ]),"bearing-a");
  assert.deepEqual(choices.ready.map(item=>item.packageId),["a"]);
  assert.deepEqual(choices.blocked,[{packageId:"c",recipeId:"lstm-c",reason:"채널 구성이 다릅니다"}]);
  assert.equal(choices.packages,3);
  assert.equal(choices.ready[0].stream.stored,true);
  assert.throws(()=>parseModelChoices(body([]),"other-asset"),/형식/);
});

test("the reason nothing can be connected names what is missing",()=>{
  assert.match(noModelReason(parseModelChoices(body([],[]),"bearing-a")),/진동 파형이나 OPC UA/);
  assert.match(noModelReason(parseModelChoices(body([]),"bearing-a")),/models 폴더/);
  assert.match(noModelReason(parseModelChoices(body([pkg("c",{compatible:false})]),"bearing-a")),/맞는 이상 탐지 모델이 없습니다/);
  assert.equal(modelTitle("lstm-a","acquisition-snapshot"),"진동 변화 탐지 · LSTM 기반");
  assert.equal(modelTitle("synthetic-rms","observation-window"),"관측 신호 변화 탐지");
});
