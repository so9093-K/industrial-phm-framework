import assert from "node:assert/strict";
import {test} from "node:test";
import {bearingStep, bearingSteps, parseDemoJourney} from "./demo-journey.ts";

const raw = {dataset:"synthetic",asset_id:"bearing-a",bindings:["forest-a","lstm-a"],
  first:1,last:96,feature:"feature.horizontal.rms",other_feature:"feature.vertical.rms"};

test("every investigation step keeps the same asset, exact feature and two comparison periods", () => {
  const context=parseDemoJourney(raw)!;
  const steps=bearingSteps(context);
  assert.equal(steps.length,7);
  for(const [index,step] of steps.entries()){
    const url=new URL(step.href,"http://local");
    assert.equal(url.searchParams.get("monitor_asset"),"bearing-a");
    assert.equal(bearingStep(url.search),index);
  }
  // Monitor, operations and investigation records are outside the guided steps.
  for(const page of ["monitor","system","investigations"])
    assert.equal(bearingStep("?page="+page+"&tab=summary"),-1);
  assert.equal(bearingStep("?page=maintenance"),6);
  const compare=new URL(steps[3].href,"http://local").searchParams;
  assert.equal(compare.get("acquisition_feature"),raw.feature);
  assert.equal(compare.get("feature_a_to"),"48");
  assert.equal(compare.get("feature_b_from"),"49");
  const relation=new URL(steps[4].href,"http://local").searchParams;
  assert.equal(relation.get("acq_relation_y"),raw.other_feature);
  assert.equal(relation.get("acq_b_to"),"96");
  const review=new URL(steps[6].href,"http://local");
  assert.equal(review.searchParams.get("model_binding"),"forest-a");
  assert.equal(review.hash,"#model-review");
});

test("unreadable or incomplete example context never opens an invented investigation", () => {
  for(const value of [null,{}, {...raw,last:0}, {...raw,bindings:["one"]},
    {...raw,dataset:"unknown"}, {...raw,first:1.5}]) assert.equal(parseDemoJourney(value),null);
  assert.equal(parseDemoJourney({...raw,dataset:"xjtu-sy"})?.dataset,"xjtu-sy");
});

test("interactive model, feature and period choices follow the next task without leaking another asset", () => {
  const context=parseDemoJourney(raw)!;
  let search="?page=assets&tab=anomaly&monitor_asset=bearing-a&model_binding=lstm-a&model_position=80";
  const signal=new URL(bearingSteps(context,search)[2].href,"http://local");
  signal.searchParams.set("vibration_feature",raw.other_feature);
  const compare=new URL(bearingSteps(context,signal.search)[3].href,"http://local");
  assert.equal(compare.searchParams.get("acquisition_feature"),raw.other_feature);
  compare.searchParams.set("feature_b_from","60");
  const relation=new URL(bearingSteps(context,compare.search)[4].href,"http://local");
  assert.equal(relation.searchParams.get("acq_b_from"),"60");
  assert.equal(relation.searchParams.get("acq_relation_x"),raw.other_feature);
  assert.equal(relation.searchParams.get("acq_relation_y"),raw.feature);
  const review=new URL(bearingSteps(context,relation.search)[6].href,"http://local");
  assert.equal(review.searchParams.get("model_binding"),"lstm-a");
  assert.equal(review.searchParams.get("model_position"),"80");
  search=relation.search.replace("bearing-a","other-asset");
  const clean=new URL(bearingSteps(context,search)[6].href,"http://local");
  assert.equal(clean.searchParams.get("model_binding"),"forest-a");
  assert.equal(clean.searchParams.get("model_position"),"96");
});

test("real dataset guidance describes one held-out run and retains the workspace return path", () => {
  const context=parseDemoJourney({...raw,dataset:"xjtu-sy",asset_id:"Bearing1_1",last:100})!;
  const search="?monitor_asset=Bearing1_1&return_to="+encodeURIComponent("http://127.0.0.1:2718/web/?page=system");
  const steps=bearingSteps(context,search);
  assert.match(steps[0].question,/Bearing1_1.*1~100/);
  assert.doesNotMatch(steps[0].question,/일정한 기록/);
  for (const step of steps) assert.equal(new URL(step.href,"http://local").searchParams.get("return_to"),"http://127.0.0.1:2718/web/?page=system");
  const local=new URL(bearingSteps(context,"?monitor_asset=Bearing1_1&return_to="+encodeURIComponent("http://localhost:2718/web/?page=system"))[1].href,"http://local");
  assert.equal(local.searchParams.get("return_to"),"http://localhost:2718/web/?page=system");
  for (const invalid of ["https://evil.example/web/","http://127.0.0.1:2718/other","invalid"]) {
    assert.equal(new URL(bearingSteps(context,"?return_to="+encodeURIComponent(invalid))[1].href,"http://local").searchParams.has("return_to"),false);
  }
});
