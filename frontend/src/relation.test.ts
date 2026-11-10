import assert from "node:assert/strict";
import {test} from "node:test";
import {movedAtSameX,parseRelation,sameXRanges,strength} from "./relation.ts";
import {relationMessage,sameXText} from "./analysis-messages.ts";
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
  assert.throws(()=>parseRelation(good(),"other","current","voltage"),/맞지 않아/);
  assert.throws(()=>parseRelation({...good(),pairing:"nearest-time"},"motor","current","voltage"),/맞지 않아/);
  assert.throws(()=>parseRelation(good(),"motor","current","current"),/맞지 않아/);
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

test("a correlation is described in words without hiding its sign or size",()=>{
  assert.equal(strength(0.91),"같은 방향으로 강하게 함께 움직임");
  assert.equal(strength(-0.5),"반대 방향으로 어느 정도 함께 움직임");
  assert.equal(strength(0.1),"함께 움직이는 경향이 거의 없음");
  assert.equal(strength(-0.7),"반대 방향으로 강하게 함께 움직임");
});

test("y is compared at the same x, and a shift there is said even when the correlation held",()=>{
  const range=(bin:number,low:number,high:number,pairs:number,median:number,q1:number,q3:number)=>
    ({bin,x_low:low,x_high:high,pair_count:pairs,y_median:median,y_q1:q1,y_q3:q3});
  const body=good();
  const a={...body.groups[0],pair_count:9000,by_x:[range(0,8.1,10.6,985,222,222,223),range(1,10.6,13,350,222,221,223),
    range(4,29.8,32.5,4762,220,219,221),range(5,32.5,35,400,220,219,221)]};
  const b={...a,period:"b",by_x:[range(0,8.1,10.6,270,227,226,228),range(1,10.6,13,116,222.5,222,223),
    range(4,29.8,32.5,581,224,223,225),range(5,32.5,35,15,224,223,225)]};
  const relation=parseRelation({...body,groups:[a,b]},"motor","current","voltage");
  const [ga,gb]=relation.groups;
  // A range with too few pairs on one side is not compared.
  const ranges=sameXRanges(ga,gb);
  assert.deepEqual(ranges.map(item=>[item.low,item.high]),[[8.1,10.6],[10.6,13],[29.8,32.5]]);
  // The best supported of the ranges that moved is quoted, with how many moved.
  const moved=movedAtSameX(ranges)!;
  assert.deepEqual([moved.shown.low,moved.outside,moved.total],[29.8,2,3]);
  const x={name:"전류평균",unit:"A"},y={name:"R상전압",unit:"V"};
  const said=sameXText(moved,x,y);
  assert.equal(said,"같은 전류평균 29.8~32.5 A에서 R상전압 중앙값은 220 → 224 V로, 기간 A의 가운데 50%(219~221 V) 밖입니다(견준 범위 3개 중 2개에서 밖).");
  const all=movedAtSameX(ranges.filter(item=>item.low!==10.6))!;
  assert.equal(sameXText(all,x,y),"같은 전류평균끼리 견준 범위 2개 모두에서 기간 B의 R상전압 중앙값이 기간 A의 가운데 50% 밖입니다. "
    +"짝이 가장 많은 29.8~32.5 A에서는 220 → 224 V입니다(기간 A 가운데 50% 219~221 V).");
  const held=relationMessage("current","voltage",{pearson:-0.77,spearman:-0.8,pairs:900},{pearson:-0.76,spearman:-0.71,pairs:900},null,[],said)!;
  assert.match(held.headline,/반대 방향으로 강하게 함께 움직입니다 \(기간 A 피어슨 -0.77 · 기간 B 피어슨 -0.76\)\. 다만 같은 전류평균/);
  assert.doesNotMatch(held.headline,/관계는 그대로/);
  // Inside A's middle 50% everywhere is no shift; responses without ranges compare nothing.
  assert.equal(movedAtSameX(ranges.filter(item=>item.low===10.6)),null);
  assert.deepEqual(parseRelation(good(),"motor","current","voltage").groups[0].byX,[]);
  const broken={...body,groups:[{...a,by_x:[range(0,4.2,10.6,400,222,223,221)]}]};
  assert.throws(()=>parseRelation(broken,"motor","current","voltage"),/같은 범위 비교/);
});

test("two periods without a relation are not a changed relation, whatever their coefficients",()=>{
  const none=relationMessage("current","voltage",{pearson:0.05,spearman:0.04,pairs:900},{pearson:-0.21,spearman:-0.2,pairs:80},null)!;
  assert.match(none.headline,/^두 기간 모두 두 값은 뚜렷한 관계가 없습니다 \(기간 A 피어슨 0.05 · 기간 B 피어슨 -0.21\)\.$/);
});

