import assert from "node:assert/strict";
import {test} from "node:test";
import {askChange,newChangeConversation,readChangeDiscussion} from "./change-investigation.ts";

test("a conversation only reads replies from this opening and selected change",async()=>{
  const original=globalThis.fetch,key="a".repeat(64),conversation=newChangeConversation();
  assert.notEqual(conversation,newChangeConversation());
  const record={id:"explanation-one",status:"complete",context:{asset_id:"bearing",change_id:key,conversation_id:conversation,question:"문제 있어?"},answer:{summary:"지금도 커지고 있습니다."}};
  let body:unknown={schema_version:1,asset_id:"bearing",change_id:key,conversation_id:conversation,explanations:[record]};
  globalThis.fetch=async()=>new Response(JSON.stringify(body),{headers:{"content-type":"application/json"}});
  try{
    const signal=new AbortController().signal;
    assert.deepEqual((await readChangeDiscussion("bearing",key,conversation,signal))[0].answer,{summary:"지금도 커지고 있습니다."});
    // 같은 변화를 눌러도 다른 창의 문답은 들어오지 않는다.
    body={schema_version:1,asset_id:"bearing",change_id:key,conversation_id:conversation,explanations:[{...record,answer:{summary:"높은 상태가 이어집니다.",next_step:"주파수를 견주면 알 수 있습니다.",actions:["spectrum"],evidence:[{fact:"x"}],source:"computed"}}]};
    assert.deepEqual((await readChangeDiscussion("bearing",key,conversation,signal))[0].answer,{summary:"높은 상태가 이어집니다."});
    body={schema_version:1,asset_id:"bearing",change_id:key,conversation_id:conversation,explanations:[{...record,context:{...record.context,change_id:"b".repeat(64)}}]};
    await assert.rejects(readChangeDiscussion("bearing",key,conversation,signal),/대상/);
    body={schema_version:1,asset_id:"bearing",change_id:key,conversation_id:conversation,explanations:[{...record,context:{...record.context,conversation_id:newChangeConversation()}}]};
    await assert.rejects(readChangeDiscussion("bearing",key,conversation,signal),/대상/);
    body={schema_version:1,asset_id:"other",change_id:key,conversation_id:conversation,explanations:[record]};
    await assert.rejects(readChangeDiscussion("bearing",key,conversation,signal),/다른 변화/);
  }finally{globalThis.fetch=original;}
});

test("a question is just what the person asked, and a follow-up names the answer it continues",async()=>{
  const original=globalThis.fetch,key="a".repeat(64),conversation=newChangeConversation(),sent:Record<string,unknown>[]=[];
  const json=(value:unknown)=>new Response(JSON.stringify(value),{headers:{"content-type":"application/json"}});
  globalThis.fetch=async(url,init)=>{
    if(String(url)==="/api/v1/session")return json({schema_version:1,can_change:true,write_scope:"supervisor-owned-source-control",csrf_token:"t".repeat(16)});
    sent.push(JSON.parse(String(init?.body)));
    return json({schema_version:1,explanation_id:"x",status:"pending",change_id:key});
  };
  try{
    const signal=new AbortController().signal;
    await askChange("bearing",key,conversation,"문제 있어?",null,signal);
    await askChange("bearing",key,conversation,"왜 그래?","x",signal);
    assert.deepEqual(sent[0],{asset_id:"bearing",change_id:key,conversation_id:conversation,question:"문제 있어?"});
    assert.deepEqual(sent[1],{asset_id:"bearing",change_id:key,conversation_id:conversation,question:"왜 그래?",parent_id:"x"});
  }finally{globalThis.fetch=original;}
});

test("a bearing answer leads to the comparison of the change it talked about, not a model verdict",async()=>{
  const {changeFollowup}=await import("./change-evidence.ts");
  const change={feature:"vertical.rms",label:"수직 진동 RMS",unit:"g",direction:"up" as const,reason:"record-end" as const,kind:"departure" as const,
    from:72,to:123,baseline:{from:1,to:37},reference:0.623,typical:2.3,value:5.78,usual:{low:0.57,high:0.65},trace:[],related:[]};
  const record={sourceId:"bearing-file",bindingId:"binding-1",assetId:"Bearing1_1",first:1,last:123,periodSeconds:60,judged:1,features:1,intervals:[change]};
  for(const replaying of [false,true]){
    const link=changeFollowup("Bearing1_1",{kind:"vibration",change,record},replaying)!;
    const q=new URL(link.href,"http://local").searchParams;
    // 대화가 말한 변화(초기 1–37번째 대 72–123번째)를 그대로 비교한다. 이상 점수 화면이 아니다.
    assert.equal(q.get("feature_a_from"),"1");assert.equal(q.get("feature_b_to"),"123");
    assert.equal(q.get("model_binding"),null);
    assert.equal(link.label,replaying?"이 시점까지의 진동 비교":"초기와 변화 구간의 진동 비교");
  }
});
