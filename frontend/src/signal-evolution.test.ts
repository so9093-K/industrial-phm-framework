import assert from "node:assert/strict";
import {test} from "node:test";
import {parseSignalEvolution} from "./signal-evolution.ts";
const data={axis:"acquisition",rate_unit:"acquisition",degradation:{recent:{from:100,to:123,points:24,median:2.48},change_ratio:2.98,rate:.0138,earlier_rate:.0463}};
test("observed rate keeps its sign and original per-measurement unit",()=>{
  const result=parseSignalEvolution(data);
  assert.equal(result?.rate,.0138);assert.equal(result?.earlierRate,.0463);
  assert.equal(result?.recentFrom,100);assert.equal(result?.changeRatio,2.98);
  assert.equal(parseSignalEvolution({...data,degradation:{...data.degradation,rate:-.01}})?.rate,-.01);
});
test("unavailable rates in old captures and invalid statistics never become zero",()=>{
  assert.equal(parseSignalEvolution({}),null);
  assert.equal(parseSignalEvolution({...data,rate_unit:"second"}),null);
  assert.equal(parseSignalEvolution({...data,degradation:{...data.degradation,rate:NaN}}),null);
  const flat=parseSignalEvolution({...data,degradation:{...data.degradation,rate:0,earlier_rate:null,change_ratio:null}});
  assert.equal(flat?.rate,0);assert.equal(flat?.earlierRate,null);assert.equal(flat?.changeRatio,null);
});
test("the rate names how many measurements it was measured over, falling back to the recent window", () => {
  assert.equal(parseSignalEvolution({...data,degradation:{...data.degradation,rate_points:10}})?.ratePoints,10);
  assert.equal(parseSignalEvolution(data)?.ratePoints,24);
});
test("the last value travels beside the robust representative value, never invented", () => {
  assert.equal(parseSignalEvolution({...data,degradation:{...data.degradation,latest:7.27}})?.latest,7.27);
  assert.equal(parseSignalEvolution(data)?.latest,null);
});
