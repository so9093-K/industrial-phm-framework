import assert from "node:assert/strict";
import {test} from "node:test";
import {askChange,readChangeDiscussion} from "./change-investigation.ts";

test("a conversation stays on its selected change, and an older answer still reads as its sentence",async()=>{
  const original=globalThis.fetch,key="a".repeat(64);
  const record={id:"explanation-one",status:"complete",context:{asset_id:"bearing",change_id:key,question:"문제 있어?"},answer:{summary:"지금도 커지고 있습니다."}};
  let body:unknown={schema_version:1,asset_id:"bearing",change_id:key,explanations:[record]};
  globalThis.fetch=async()=>new Response(JSON.stringify(body),{headers:{"content-type":"application/json"}});
  try{
    const signal=new AbortController().signal;
    assert.deepEqual((await readChangeDiscussion("bearing",key,signal))[0].answer,{summary:"지금도 커지고 있습니다.",evidence:[]});
    // 예전 답(다음에 볼 것·후속 분석·계산 요약)도 문장만 읽는다.
    body={schema_version:1,asset_id:"bearing",change_id:key,explanations:[{...record,answer:{summary:"높은 상태가 이어집니다.",next_step:"주파수를 견주면 알 수 있습니다.",actions:["spectrum"],source:"computed"}}]};
    assert.deepEqual((await readChangeDiscussion("bearing",key,signal))[0].answer,{summary:"높은 상태가 이어집니다.",evidence:[]});
    body={schema_version:1,asset_id:"bearing",change_id:key,explanations:[{...record,context:{...record.context,change_id:"b".repeat(64)}}]};
    await assert.rejects(readChangeDiscussion("bearing",key,signal),/대상/);
    body={schema_version:1,asset_id:"other",change_id:key,explanations:[record]};
    await assert.rejects(readChangeDiscussion("bearing",key,signal),/다른 변화/);
  }finally{globalThis.fetch=original;}
});

test("the first question carries the notice the screen showed, and a follow-up continues the thread instead",async()=>{
  const original=globalThis.fetch,key="a".repeat(64),sent:Record<string,unknown>[]=[];
  const json=(value:unknown)=>new Response(JSON.stringify(value),{headers:{"content-type":"application/json"}});
  globalThis.fetch=async(url,init)=>{
    if(String(url)==="/api/v1/session")return json({schema_version:1,can_change:true,write_scope:"supervisor-owned-source-control",csrf_token:"t".repeat(16)});
    sent.push(JSON.parse(String(init?.body)));
    return json({schema_version:1,explanation_id:"x",status:"pending",change_id:key});
  };
  try{
    const signal=new AbortController().signal;
    await askChange("bearing",key,"문제 있어?",null,signal,null,"수직 진동 RMS가 초기의 약 9.3배입니다.");
    await askChange("bearing",key,"왜 그래?","x",signal,null,"수직 진동 RMS가 초기의 약 9.3배입니다.");
    assert.equal(sent[0].opening,"수직 진동 RMS가 초기의 약 9.3배입니다.");
    assert.equal(sent[1].parent_id,"x");
    assert.equal(sent[1].opening,undefined);
  }finally{globalThis.fetch=original;}
});
