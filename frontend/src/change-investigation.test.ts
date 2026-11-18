import assert from "node:assert/strict";
import {test} from "node:test";
import {readChangeDiscussion} from "./change-investigation.ts";

test("a question's answer stays on its selected change, including when model and end measurement coincide",async()=>{
  const original=globalThis.fetch,key="a".repeat(64);
  const record={id:"explanation-one",status:"complete",context:{asset_id:"bearing",change_id:key,question:"일시적인가요?"},answer:{summary:"높은 상태가 이어집니다.",actions:["spectrum","compare"],source:"model"}};
  let body:unknown={schema_version:1,asset_id:"bearing",change_id:key,explanations:[record]};
  globalThis.fetch=async()=>new Response(JSON.stringify(body),{headers:{"content-type":"application/json"}});
  try{
    const signal=new AbortController().signal;
    assert.deepEqual((await readChangeDiscussion("bearing",key,signal))[0].answer?.actions,["spectrum","compare"]);
    body={schema_version:1,asset_id:"bearing",change_id:key,explanations:[{...record,context:{...record.context,change_id:"b".repeat(64)}}]};
    await assert.rejects(readChangeDiscussion("bearing",key,signal),/대상/);
    body={schema_version:1,asset_id:"bearing",change_id:key,explanations:[{...record,answer:{...record.answer,actions:["arbitrary-url"]}}]};
    await assert.rejects(readChangeDiscussion("bearing",key,signal),/다음 분석/);
    body={schema_version:1,asset_id:"other",change_id:key,explanations:[record]};
    await assert.rejects(readChangeDiscussion("bearing",key,signal),/다른 변화/);
  }finally{globalThis.fetch=original;}
});
