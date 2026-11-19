import assert from "node:assert/strict";
import {test} from "node:test";
import {nearestPosition,movePosition} from "./plot-selection.ts";
test("plot selection uses stored measurements across gaps and clamps outside the chart",()=>{
  assert.equal(nearestPosition([1,4,9],6),4);
  assert.equal(nearestPosition([1,4,9],8),9);
  assert.equal(nearestPosition([1,4,9],-10),1);
  assert.equal(nearestPosition([1,4,9],20),9);
  assert.equal(nearestPosition([],1),null);
});
test("keyboard selection visits adjacent stored measurements including the oldest",()=>{
  assert.equal(movePosition([1,4,9],9,"ArrowLeft"),4);
  assert.equal(movePosition([1,4,9],1,"ArrowLeft"),1);
  assert.equal(movePosition([1,4,9],4,"Home"),1);
  assert.equal(movePosition([1,4,9],1,"End"),9);
  assert.equal(movePosition([1,4,9],4,"Escape"),null);
});
