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
