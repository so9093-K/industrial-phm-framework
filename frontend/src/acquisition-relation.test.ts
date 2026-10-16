import assert from "node:assert/strict";
import {test} from "node:test";
import {parseAcquisitionRelation} from "./acquisition-relation.ts";
import type {FeatureSource} from "./acquisition-profile.ts";
import type {Spans} from "./spectrum.ts";

const source:FeatureSource={assetId:"a",sourceId:"source-a",bindingId:"binding-a",
  first:1,last:20,count:20,features:[{id:"rms",label:"RMS"},{id:"peak",label:"peak"}]};
const spans:Spans={a:{from:1,to:10},b:{from:11,to:20}};
const group=(period:"a"|"b")=>({
  period,source_id:"source-a",binding_id:"binding-a",measurement_point_id:null,
  analyzed_count:10,x_usable_count:1,y_usable_count:1,pair_count:1,
  pearson:null,spearman:null,sampled:true,points:[[period==="a"?1:20,0.2,0.5]],
});
const payload=()=>({
  schema_version:1,asset_id:"a",kind:"acquisition",pairing:"same-acquisition",
  x:"rms",y:"peak",groups:[group("a"),group("b")],
});
test("identical source/binding and ordinal pairs retain a sampled comparison",()=>{
  const result=parseAcquisitionRelation(payload(),"a",source,"rms","peak",spans);
  assert.equal(result.groups[1].points[0].ordinal,20);
  assert.equal(result.groups[0].pairs,1);
  assert.equal(result.groups[0].pearson,null);
  assert.equal(result.groups[0].sampled,true);
});
test("different binding, asset or pairing must not reuse analysis evidence",()=>{
  const changed=payload();
  changed.groups[1].binding_id="another-binding";
  assert.throws(()=>parseAcquisitionRelation(changed,"a",source,"rms","peak",spans),/binding/);
  assert.throws(()=>parseAcquisitionRelation(payload(),"other",source,"rms","peak",spans),/계약/);
  assert.throws(()=>parseAcquisitionRelation({...payload(),pairing:"same-time"},
    "a",source,"rms","peak",spans),/계약/);
});
test("non-ordinal, duplicated and out-of-range pairs are rejected",()=>{
  const changed=payload();
  changed.groups[0].points=[[11,0.2,0.5]];
  assert.throws(()=>parseAcquisitionRelation(changed,"a",source,"rms","peak",spans),/범위/);
  const twice=payload();
  twice.groups[1].period="a";
  assert.throws(()=>parseAcquisitionRelation(twice,"a",source,"rms","peak",spans),/중복/);
});
test("zero pairs are not mistaken for a zero correlation or a diagnosis",()=>{
  const empty=payload();
  empty.groups[0]={...empty.groups[0],analyzed_count:0,x_usable_count:0,
    y_usable_count:0,pair_count:0,pearson:null,spearman:null,points:[]};
  const result=parseAcquisitionRelation(empty,"a",source,"rms","peak",spans);
  assert.equal(result.groups[0].pairs,0);
  assert.equal(result.groups[0].pearson,null);
  const invalid=payload();
  invalid.groups[0].pearson=0.2;
  invalid.groups[0].pair_count=0;
  invalid.groups[0].x_usable_count=0;
  invalid.groups[0].y_usable_count=0;
  invalid.groups[0].points=[];
  assert.throws(()=>parseAcquisitionRelation(invalid,"a",source,"rms","peak",spans),/계수/);
});
