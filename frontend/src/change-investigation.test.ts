import assert from "node:assert/strict";
import {test} from "node:test";
import {parseRecordFindings} from "./record-findings.ts";
import {readChangeDiscussion,readSteps,changeActionLinks,investigationLinks} from "./change-investigation.ts";

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
    assert.equal((await readChangeDiscussion("bearing",key,signal))[0].answer?.next_step,undefined);
    body={schema_version:1,asset_id:"bearing",change_id:key,explanations:[{...record,answer:{...record.answer,next_step:"주파수 비교에서 에너지 비중이 커진 대역을 확인하세요."}}]};
    assert.match((await readChangeDiscussion("bearing",key,signal))[0].answer!.next_step!,/에너지 비중/);
    body={schema_version:1,asset_id:"bearing",change_id:key,explanations:[{...record,context:{...record.context,change_id:"b".repeat(64)}}]};
    await assert.rejects(readChangeDiscussion("bearing",key,signal),/대상/);
    body={schema_version:1,asset_id:"bearing",change_id:key,explanations:[{...record,answer:{...record.answer,actions:["arbitrary-url"]}}]};
    await assert.rejects(readChangeDiscussion("bearing",key,signal),/다음 분석/);
    body={schema_version:1,asset_id:"other",change_id:key,explanations:[record]};
    await assert.rejects(readChangeDiscussion("bearing",key,signal),/다른 변화/);
  }finally{globalThis.fetch=original;}
});


test("an electrical suggestion opens the chosen voltage interval instead of the latest day",()=>{
  const span={from:"2020-10-01T00:00:00Z",to:"2020-10-05T00:00:00Z"};
  const record=parseRecordFindings({schema_version:1,asset_id:"compressor",meaning:"departures-from-the-first-30-percent-not-fault-diagnosis",baseline:{from:span.from,to:"2020-10-02T00:00:00Z"},record:span,bucket_seconds:60,judged:1,unchecked:0,interval_count:1,
    signals:[{channel:"R상전압",label:"R상전압",unit:"V",state:"scored"}],
    intervals:[{channel:"R상전압",label:"R상전압",unit:"V",start:"2020-10-03T00:00:00Z",end:"2020-10-03T01:00:00Z",direction:"up",value:225,usual:{low:219,high:221},within:[]}]},"compressor");
  const link=investigationLinks("compressor",{kind:"history",record,item:record.intervals[0],condition:null},["electrical"])[0];
  const q=new URL(link.href,"http://local").searchParams;
  assert.equal(q.get("tab"),"change");assert.equal(q.get("method"),"electrical");
  const picked=q.get("monitor_pick")!.split("~").map(Date.parse);
  assert.deepEqual(picked,[Date.parse("2020-10-03T00:00:00Z"),Date.parse("2020-10-03T01:00:00Z")]);
});

test("the checked rows point at what the chart draws, and a row without a drawing is still listed",()=>{
  const steps=readSteps({
    steps:[{fact:"feature_0",label:"R상전압",result:"222 → 226 V"},{fact:"operating_level",label:"같은 운전 수준끼리 비교",result:"약 11 A 운전"},
      {fact:"model_0",label:"LSTM 오토인코더",result:"기준 초과 52회 중 48회"},{fact:1,label:"x",result:"y"}],
    targets:{feature_0:{kind:"change",review_key:"a",label:"R상전압",before:222,after:226,unit:"V",where:"10월 4일"},
      operating_level:{kind:"operation",label:"운전 수준",detail:"약 11 A 운전 중인 측정끼리 비교"}},
  });
  assert.deepEqual(steps.map(row=>[row.label,row.result,row.target?.kind??null]),[
    ["R상전압","222 → 226 V","change"],["같은 운전 수준끼리 비교","약 11 A 운전","operation"],["LSTM 오토인코더","기준 초과 52회 중 48회",null]]);
  assert.equal(steps[0].target?.fact,"feature_0");
  assert.deepEqual(readSteps(undefined),[]);
  assert.deepEqual(readSteps({facts:{}}),[]);
});
