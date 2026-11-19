import assert from "node:assert/strict";
import {test} from "node:test";
import {aroundBand,comparisonBand,frequencyCells,relativePower} from "./frequency-view.ts";
import type {SpectrumChannel} from "./spectrum.ts";

test("A/B uses one reference even when zooming to a much quieter band",()=>{
  const a=[100,1,.01],b=[10,10,0];
  const reference=Math.max(...a,...b);
  assert.deepEqual(relativePower(a,reference),[0,-20,-40]);
  assert.deepEqual(relativePower(b,reference),[-10,-10,-60]);
  assert.equal(relativePower(a,reference)[2],relativePower(a.slice(2),reference)[0]);
  assert.deepEqual(relativePower([0,0],0),[-60,-60]);
});

test("display bins fill a shared frequency domain without false gaps or axis stretching",()=>{
  const cells=frequencyCells([28.125,90.625,156.25],{from:60,to:170});
  assert.equal(cells[0].index,1);
  assert.equal(cells[0].left,0);
  assert.equal(cells.at(-1)!.left+cells.at(-1)!.width,1);
  assert.equal(cells[0].left+cells[0].width,cells[1].left);
  assert.ok(cells.every(cell=>cell.width>0));
});

test("band choice belongs to the selected channel and retains context around its edges",()=>{
  const channel:SpectrumChannel={id:"x",label:"x",a:[],b:[],bands:[],ratio:27,
    shares:[{from:0,to:794,a:.6,b:.2},{from:800,to:1594,a:.18,b:.63}]};
  assert.equal(comparisonBand(channel)?.from,800);
  assert.equal(comparisonBand(channel,0)?.from,0);
  assert.equal(comparisonBand({...channel,shares:[]}),null);
  assert.deepEqual(aroundBand(channel.shares[1],12800),{from:6,to:2388});
  assert.deepEqual(aroundBand({from:12000,to:12800},12800),{from:11200,to:12800});
});
