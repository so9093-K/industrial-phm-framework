import assert from "node:assert/strict";
import {test} from "node:test";
import {parseRelation} from "./relation.ts";
const good=()=>({
  schema_version:1,asset_id:"motor",kind:"history",x:"current",y:"voltage",
  pairing:"same-source-point-and-timestamp",
  groups:[
    {period:"a",source_id:"src-1",measurement_point_id:"p1",meaning_id:"hash1",
     x_unit:"A",y_unit:"V",x_usable_count:4,y_usable_count:4,pair_count:2,
     pearson:0.8,spearman:0.9,sampled:false,
     points:[["2026-10-01T00:00:00Z",1,2],["2026-10-01T00:01:00Z",2,3]]},
    {period:"a",source_id:"src-2",measurement_point_id:"p2",meaning_id:"hash2",
     x_unit:"A",y_unit:"V",x_usable_count:2,y_usable_count:2,pair_count:1,
     pearson:null,spearman:null,sampled:false,points:[["2026-10-01T00:02:00Z",3,4]]},
  ],
});
test("only exact asset/channels and same-source-point-timestamp pairing",()=>{
  const p=parseRelation(good(),"motor","current","voltage");
  assert.equal(p.groups.length,2);
  assert.notEqual(p.groups[0].id,p.groups[1].id);
  assert.throws(()=>parseRelation(good(),"other","current","voltage"),/일치하지/);
  assert.throws(()=>parseRelation({...good(),pairing:"nearest-time"},"motor","current","voltage"),/일치하지/);
  assert.throws(()=>parseRelation(good(),"motor","current","current"),/일치하지/);
});
test("missing/unreliable correlation stays unavailable and is not zero",()=>{
  const p=parseRelation(good(),"motor","current","voltage");
  assert.equal(p.groups[1].pearson,null);
  assert.equal(p.groups[0].pearson,0.8);
  assert.equal(p.groups[1].points[0].x,3);
});
test("reject mixed or invalid pair evidence",()=>{
  const duplicated=good();
  duplicated.groups.push({...duplicated.groups[0]});
  assert.throws(()=>parseRelation(duplicated,"motor","current","voltage"),/중복/);
  const invalid=good();
  invalid.groups[0].pair_count=1;
  assert.throws(()=>parseRelation(invalid,"motor","current","voltage"),/측정 짝 수/);
  const badCoefficient=good();
  badCoefficient.groups[0].pearson=1.4;
  assert.throws(()=>parseRelation(badCoefficient,"motor","current","voltage"),/계수/);
  const badTime=good();
  badTime.groups[0].points[0][0]="2026-10-01";
  assert.throws(()=>parseRelation(badTime,"motor","current","voltage"),/시각/);
});
