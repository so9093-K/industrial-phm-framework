import assert from "node:assert/strict";
import {test} from "node:test";
import {connectPlace,fact,nothingStored,parseCapabilities,place} from "./capabilities.ts";

const MEANING="what-the-stored-data-supports-not-asset-health";
const item=(id:string,status:string,reason:string,facts:Record<string,unknown>={},
  target:{view:string;goal:string|null;data?:string}|null=null)=>({id,status,reason,target,facts});
function body(capabilities:unknown[],data:Record<string,unknown>={}){
  return {schema_version:1,asset_id:"motor",meaning:MEANING,capabilities,
    data:{history:{channel_count:2,measurement_count:80,start_at:"2026-10-14T00:00:00Z",end_at:"2026-10-14T00:39:00Z"},
      acquisition:null,waiting_sources:0,...data}};
}

test("each analysis opens its own place with the asset and data kind kept",()=>{
  const parsed=parseCapabilities(body([
    item("measurements","ready","history",{channels:2},{view:"signals",goal:"trend",data:"history"}),
    item("period-compare","ready","acquisition",{}, {view:"signals",goal:"compare",data:"vibration"}),
    item("relation","ready","history",{channels:3},{view:"signals",goal:"relation",data:"history"}),
    item("spectrum","unavailable","no-waveform"),
    item("forecast","ready","outlook-only",{}, {view:"forecast",goal:null,data:"history"}),
    item("anomaly","ready","explore",{packages:2},{view:"anomaly",goal:"baseline"}),
    item("ai-question","ready","outlook",{}, {view:"forecast",goal:"ask"}),
  ]),"motor");
  const [measurements,compare,relation,spectrum,forecast,anomaly,ask]=parsed.items;
  assert.match(place(measurements,"motor")!,/tab=signals/);
  assert.match(place(compare,"motor")!,/tab=change&method=compare&data=vibration/);
  assert.match(place(relation,"motor")!,/method=relation&data=history/);
  assert.equal(place(spectrum,"motor"),null);
  assert.match(place(forecast,"motor")!,/tab=outlook&data=history/);
  assert.match(place(anomaly,"motor")!,/tab=anomaly&method=baseline/);
  assert.match(connectPlace(anomaly,"motor")!,/tab=anomaly&method=model/);
  assert.equal(connectPlace(measurements,"motor"),null);
  assert.match(place(ask,"motor")!,/tab=outlook/);
  assert.match(fact(measurements,parsed),/^시계열 신호 2개 · 2026\. 10\. 14\./);
  assert.equal(fact(relation,parsed),"시계열 신호 3개 중 2개 선택");
  assert.equal(fact(anomaly,parsed),"모델 없이 기준 구간에서 벗어난 값 찾기 · 맞는 모델 2개 연결 가능");
  assert.equal(fact(spectrum,parsed),"원본 진동 파형 없음");
});

test("a model one connection away opens model connect; nothing stored is one line",()=>{
  const parsed=parseCapabilities(body([item("anomaly","needs-connection","compatible-model",{packages:1},{view:"anomaly",goal:null}),
    item("forecast","unavailable","input-mismatch",{details:["channels differ",3]})],
  {acquisition:{first:1,last:8,sampling_rate_hz:25600}}),"motor");
  assert.match(place(parsed.items[0],"motor")!,/tab=anomaly&method=model/);
  assert.equal(fact(parsed.items[1],parsed),"모델 입력 조건이 맞지 않음 (channels differ)");
  assert.equal(nothingStored(parsed),null);
  const empty=parseCapabilities(body([item("measurements","unavailable","not-received",{}, {view:"connect",goal:null})],{history:null}),"motor");
  assert.equal(nothingStored(empty),"not-received");
  assert.match(place(empty.items[0],"motor")!,/page=system&section=connections/);
});

test("an answer about another asset or a health verdict is refused",()=>{
  assert.throws(()=>parseCapabilities(body([]),"pump"),/형식/);
  assert.throws(()=>parseCapabilities({...body([]),meaning:"asset-health"},"motor"),/형식/);
  assert.throws(()=>parseCapabilities(body([item("diagnosis","ready","history")]),"motor"),/형식/);
});

test("unknown or absent targets never produce a fabricated analysis route",()=>{
  const [absent,unknown]=parseCapabilities(body([
    item("measurements","ready","acquisition"),
    item("anomaly","waiting","waiting-results",{}, {view:"anomaly",goal:null}),
  ]),"motor").items;
  assert.equal(place(absent,"motor"),null);
  assert.equal(place(unknown,"motor"),null);
  assert.throws(()=>parseCapabilities(body([item("measurements","ready","history",{}, {view:"invalid",goal:"trend"})]),"motor"),/형식/);
});
