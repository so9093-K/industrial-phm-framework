import assert from "node:assert/strict";
import {test} from "node:test";
import {askChange,newChangeConversation,readChangeDiscussion} from "./change-investigation.ts";
import {parseRecordFindings} from "./record-findings.ts";
import {changeAnalyses} from "./change-evidence.ts";

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

test("an analysis the AI picks opens the screen for this change's own signal and period",()=>{
  const span={from:"2020-10-01T00:00:00Z",to:"2020-10-05T00:00:00Z"};
  const record=parseRecordFindings({schema_version:1,asset_id:"compressor",meaning:"departures-from-the-first-30-percent-not-fault-diagnosis",baseline:{from:span.from,to:"2020-10-02T00:00:00Z"},record:span,bucket_seconds:60,judged:1,unchecked:0,interval_count:1,
    signals:[{channel:"R상전압",label:"R상전압",unit:"V",state:"scored"}],
    intervals:[{channel:"R상전압",label:"R상전압",unit:"V",start:"2020-10-03T00:00:00Z",end:"2020-10-03T01:00:00Z",direction:"up",value:225,usual:{low:219,high:221},within:[]}]},"compressor");
  const history=changeAnalyses("compressor",{kind:"history",record,item:record.intervals[0],condition:null});
  // 3상 전력은 같은 구간을 연 채로 불평형 분석을 연다.
  const phases=new URL(history.open_phase_balance.href,"http://local").searchParams;
  assert.equal(phases.get("tab"),"change");assert.equal(phases.get("method"),"electrical");
  assert.deepEqual(phases.get("monitor_pick")!.split("~").map(Date.parse),[Date.parse("2020-10-03T00:00:00Z"),Date.parse("2020-10-03T01:00:00Z")]);
  assert.ok(history.open_compare&&history.open_signals);
  assert.equal(history.open_relation,undefined);// 함께 달라진 다른 신호가 없으면 신호 관계는 없다.
  const change={feature:"vertical.rms",label:"수직 진동 RMS",unit:"g",direction:"up" as const,reason:"record-end" as const,kind:"departure" as const,
    from:72,to:123,baseline:{from:1,to:37},reference:0.623,typical:2.3,value:5.78,usual:{low:0.57,high:0.65},trace:[],related:[]};
  const vibration=changeAnalyses("Bearing1_1",{kind:"vibration",change,record:{sourceId:"s",bindingId:"b",assetId:"Bearing1_1",first:1,last:123,periodSeconds:60,judged:1,features:1,intervals:[change]}});
  assert.deepEqual(Object.keys(vibration).sort(),["open_compare","open_signals","open_spectrum"]);
  assert.equal(new URL(vibration.open_spectrum.href,"http://local").searchParams.get("method"),"spectrum");
});

test("a question carries the place pointed on the chart, and the answer keeps what it opened",async()=>{
  const original=globalThis.fetch,key="a".repeat(64),conversation="c".repeat(32),sent:Record<string,unknown>[]=[];
  const json=(value:unknown)=>new Response(JSON.stringify(value),{headers:{"content-type":"application/json"}});
  globalThis.fetch=async(url,init)=>{
    if(String(url)==="/api/v1/session")return json({schema_version:1,can_change:true,write_scope:"supervisor-owned-source-control",csrf_token:"t".repeat(16)});
    if(String(url).startsWith("/api/v1/phm/change-explanations"))return json({schema_version:1,asset_id:"bearing",change_id:key,conversation_id:conversation,explanations:[
      {id:"one",status:"complete",context:{asset_id:"bearing",change_id:key,conversation_id:conversation,question:"여기는 어때?",pointed:"80번째 측정"},
        answer:{summary:"80번째 측정에서는 초기의 약 3배입니다.",analysis:"open_spectrum"}}]});
    sent.push(JSON.parse(String(init?.body)));
    return json({schema_version:1,explanation_id:"x",status:"pending",change_id:key});
  };
  try{
    const signal=new AbortController().signal;
    await askChange("bearing",key,conversation,"여기는 어때?",null,signal,null,false,{at:80,axis:"acquisition",label:"80번째 측정"});
    await askChange("compressor",key,conversation,"여기는?",null,signal,null,false,{at:Date.parse("2020-10-04T03:00:00Z"),axis:"time",label:"10월 4일 12:00"});
    assert.equal(sent[0].at,"80");
    assert.equal(sent[1].at,"2020-10-04T03:00:00.000Z");
    const [row]=await readChangeDiscussion("bearing",key,conversation,signal);
    assert.equal(row.pointed,"80번째 측정");assert.equal(row.analysis,"open_spectrum");
  }finally{globalThis.fetch=original;}
});
