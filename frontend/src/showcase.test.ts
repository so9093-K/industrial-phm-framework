import test from "node:test";
import assert from "node:assert/strict";
import {requestKey,snapshotResponse} from "./showcase/runtime.ts";
import {steps,currentStep} from "./showcase/guide.ts";

test("showcase names the exact query, including duplicate values and numeric settings",()=>{
  const url=new URL("http://local/api/v1/outlook?series=b&asset_id=pump&series=a&limit=13");
  assert.equal(requestKey(url),"/api/v1/outlook?asset_id=pump&limit=13&series=a&series=b");
  const recorded={status:200,body:{limit:13,value:12}};
  const snapshot={schema_version:1,responses:{[requestKey(url)]:recorded}};
  assert.deepEqual(snapshotResponse(snapshot,url,"GET"),recorded);
  url.searchParams.set("limit","15");
  assert.equal(snapshotResponse(snapshot,url,"GET").status,404);
  assert.equal(snapshotResponse(snapshot,url,"POST").status,403);
});

test("guide stays tied to the asset and task when loading a direct link",()=>{
  assert.equal(steps.length,5);
  assert.equal(currentStep(new URL(steps[3].href,"http://local").search),3);
  assert.equal(currentStep("?page=maintenance"),4);
  assert.ok(steps.slice(1).every(step=>step.href.includes("monitor_asset=demo-pump-change")));
});
