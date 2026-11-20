import assert from "node:assert/strict";
import {test} from "node:test";
import {investigationContext} from "./investigation-context.ts";
import {summarySelectionUrl,tabSelectionUrl,investigationOriginUrl} from "./routes.ts";

const query=(key:unknown,label?:string)=>new URLSearchParams({summary_change:JSON.stringify(key),...(label?{summary_label:label}:{})}).toString();
test("analysis tabs retain the observed change separately from edited comparison periods",()=>{
  const base="http://local/web/?page=assets&monitor_asset=Bearing1_1";
  const picked=base+"&"+query(["vibration","vertical.rms",72,123],"수직 진동 크기 (RMS)")+"&feature_b_from=72&feature_b_to=123";
  const summary=summarySelectionUrl(base,picked,JSON.stringify(["vibration","vertical.rms",72,123]),"vibration");
  const comparison=new URL(tabSelectionUrl(base+"&tab=change&method=compare","http://local"+summary),base);
  comparison.searchParams.set("feature_b_from","90");
  const model=new URL(tabSelectionUrl(base+"&tab=anomaly&method=model",comparison.href),base);
  assert.deepEqual(investigationContext(model.search),{label:"수직 진동 크기 (RMS)",span:"72–123번째 측정"});
});
test("missing labels and invalid addresses never expose internal feature IDs or invented periods",()=>{
  assert.equal(investigationContext(""),null);
  assert.equal(investigationContext("summary_change=%5Bbroken"),null);
  for(const key of [["vibration","internal.feature",0,3],["vibration","internal.feature",4,3],["vibration","x",1.5,3],["history","secret","invalid","invalid"],["history","x","2026-01-02","2026-01-01"]])assert.equal(investigationContext(query(key)),null);
  assert.deepEqual(investigationContext(query(["vibration","internal.feature",1,123])),{label:"선택한 변화",span:"1–123번째 측정"});
  assert.match(investigationContext(query(["history","internal.source","2020-10-04T00:19:00Z","2020-10-05T22:31:00Z"],"R상전압"))!.span,/10월 4일/);
});

test("AI actions keep their own target measurement while retaining the observed phenomenon",()=>{
  const current="http://local/web/?monitor_asset=bearing&summary_change=selected&summary_kind=vibration&summary_label=RMS&model_position=123";
  const target="/web/?page=assets&monitor_asset=bearing&tab=anomaly&model_position=72&model_binding=lstm";
  const next=new URL(investigationOriginUrl(target,current),current);
  assert.equal(next.searchParams.get("model_position"),"72");
  assert.equal(next.searchParams.get("model_binding"),"lstm");
  assert.equal(next.searchParams.get("summary_change"),"selected");
  const other=new URL(investigationOriginUrl(target.replace("bearing","other"),current),current);
  assert.equal(other.searchParams.has("summary_change"),false);
});
