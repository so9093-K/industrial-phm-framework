import assert from "node:assert/strict";
import {test} from "node:test";
import {readChangeDiscussion,changeActionLinks} from "./change-investigation.ts";

test("an answer's follow-up uses the selected feature and periods, and opens the exact model at onset",()=>{
  const change={feature:"vertical.rms",baseline:{from:3,to:12},from:23,to:41};
  const links=changeActionLinks("bearing B",change,"second-model",["compare","spectrum","onset","model"]);
  const urls=Object.fromEntries(links.map(row=>[row.key,new URL(row.href,"http://local")]));
  assert.equal(urls.compare.searchParams.get("acquisition_feature"),"vertical.rms");
  for(const [key,expected] of Object.entries({a_from:3,a_to:12,b_from:23,b_to:41})){
    assert.equal(urls.compare.searchParams.get("feature_"+key),String(expected));
    assert.equal(urls.spectrum.searchParams.get("spectrum_"+key),String(expected));
  }
  for(const url of Object.values(urls))assert.equal(url.searchParams.get("monitor_asset"),"bearing B");
  for(const key of ["onset","model"]){
    assert.equal(urls[key].searchParams.get("model_binding"),"second-model");
    assert.equal(urls[key].searchParams.get("model_position"),"23");
  }
  assert.equal(urls.onset.hash,"#selected-model-input");
  assert.deepEqual(changeActionLinks("bearing B",change,null,["model","onset"]),[]);
});

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
