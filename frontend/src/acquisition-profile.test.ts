import assert from "node:assert/strict";
import {test} from "node:test";
import {parseFeatureSource,parseFeatureProfile,type FeatureSource} from "./acquisition-profile.ts";
import type {Spans} from "./spectrum.ts";

const source:FeatureSource={
 assetId:"motor",sourceId:"source-A",bindingId:"binding-A",
 first:1,last:40,count:40,features:[{id:"feature.R.rms",label:"R RMS"}],
};
const spans:Spans={a:{from:1,to:20},b:{from:21,to:40}};
const period=(measured:number,sampled:boolean)=>({
 observation_count:20,usable_count:measured,analyzed_count:20,
 missing_count:1,unanalyzed_count:0,first_position:1,last_position:20,
 sampled,mean:measured?2:null,quantiles:measured?[1,1.5,2,2.5,3]:null,
});
const payload=()=>({
 schema_version:1,asset_id:"motor",kind:"acquisition",
 meaning:"stored-measurements-compared-not-asset-health",
 periods:{a:{from:1,to:20},b:{from:21,to:40}},
 series:[{kind:"acquisition",key:"feature.R.rms",label:"R RMS",
  source_id:"source-A",binding_id:"binding-A",
  periods:{a:period(20,false),b:period(12,true)},
  comparison:{median_change:0,b_outside_a_band_percent:25},
 }],
});
test("acquisition feature names and server scope are exact",()=>{
 const options={schema_version:1,asset_id:"motor",history:null,acquisition:{
  source_id:"source-A",binding_id:"binding-A",first:1,last:40,count:40,
  features:[{key:"feature.R.rms",label:"R RMS"}],
 }};
 assert.deepEqual(parseFeatureSource(options,"motor")?.features,source.features);
 assert.throws(()=>parseFeatureSource(options,"other"),/일치하지/);
});
test("ordinal periods, sampled metrics and provenance are retained",()=>{
 const x=parseFeatureProfile(payload(),"motor",source,"feature.R.rms",spans);
 assert.equal(x.a.delivered,20);
 assert.equal(x.b.usable,12);
 assert.equal(x.b.sampled,true);
 assert.equal(x.b.missingAcquisitions,1);
 assert.equal(x.medianChange,0);
});
test("mixed asset, binding and range reject the entire comparison",()=>{
 assert.throws(()=>parseFeatureProfile({...payload(),asset_id:"different"},
  "motor",source,"feature.R.rms",spans),/일치하지/);
 const wrong=payload();wrong.series[0].binding_id="other";
 assert.throws(()=>parseFeatureProfile(wrong,"motor",source,"feature.R.rms",spans),/출처/);
 assert.throws(()=>parseFeatureProfile(payload(),"motor",source,"feature.R.rms",
  {a:{from:2,to:20},b:spans.b}),/계산 기간/);
});
test("no median cannot be mistaken for zero, and response counters must be consistent",()=>{
 const none=payload();
 none.series[0].periods.b=period(0,false);
 assert.throws(()=>parseFeatureProfile(none,"motor",source,"feature.R.rms",spans),/중앙값 근거/);
 const changed=payload();
 changed.series[0].periods.a.analyzed_count=2;
 assert.throws(()=>parseFeatureProfile(changed,"motor",source,"feature.R.rms",spans),/모순/);
});
