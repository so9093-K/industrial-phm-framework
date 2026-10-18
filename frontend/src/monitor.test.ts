import assert from "node:assert/strict";
import { test } from "node:test";

import { assetLabel, assetOptionLabel, attentionLabel, parseMonitor } from "./monitor.ts";

const observed = {
  assets: {
    items: [
      {
        asset_id: "pump-one",
        data_flow_status: "stored-history",
        last_data_at: null,
        attention_count: 0,
      },
    ],
    total: 1,
    truncated: false,
  },
  assessed_at: "2026-10-10T00:00:00Z",
  system_error_scopes: [],
};

test("the API's zero is an actual zero, not an implicit default", () => {
  const data = parseMonitor(observed);
  assert.equal(data.assets[0].attentionCount, 0);
  assert.equal(data.systemReadUncertain, false);
});

test("missing an attention value never becomes zero", () => {
  const data = parseMonitor({
    ...observed,
    assets: {
      ...observed.assets,
      items: [{ asset_id: "pump-one", data_flow_status: "waiting", last_data_at: null }],
    },
  });
  assert.equal(data.assets[0].attentionCount, null);
});

test("registered names label assets without changing stable IDs, and duplicate names remain selectable", () => {
  const assets = parseMonitor({...observed, assets: {...observed.assets, items: [
    {asset_id:"pump-one", asset_display_name:"순환 펌프"},
    {asset_id:"pump-two", asset_display_name:"순환 펌프"},
    {asset_id:"pump-three", asset_display_name:"   "},
  ]}}).assets;
  assert.equal(assetLabel(assets, "pump-one"), "순환 펌프");
  assert.equal(assets[0].assetId, "pump-one");
  assert.equal(assetOptionLabel(assets, "pump-one"), "순환 펌프 · pump-one");
  assert.equal(assetOptionLabel(assets, "pump-two"), "순환 펌프 · pump-two");
  assert.equal(assetLabel(assets, "pump-three"), "pump-three");
  assert.equal(assetLabel(assets, "unknown"), "unknown");
});

test("the measurement time is the stored event time, never when a file was read", () => {
  const data = parseMonitor({
    ...observed,
    assets: {
      ...observed.assets,
      items: [{ asset_id: "pump-one", data_flow_status: "stored-history",
        last_data_at: "2026-10-18T06:14:23Z", last_observed_at: "2026-10-12T14:50:00Z" }],
    },
  });
  assert.equal(data.assets[0].lastObservedAt, "2026-10-12T14:50:00Z");
  assert.equal(data.assets[0].lastReceivedAt, "2026-10-18T06:14:23Z");
});

test("missing error-scope evidence is not declared healthy", () => {
  const { system_error_scopes: _omitted, ...withoutErrors } = observed;
  const data = parseMonitor(withoutErrors);
  assert.equal(data.systemReadUncertain, true);
});

test("an invalid payload is not represented as an empty workspace", () => {
  assert.throws(() => parseMonitor({ assets: { total: 0 } }), /관측 응답/);
});

test("an unreadable analysis list is reported as such without hiding the assets", () => {
  const data = parseMonitor({
    ...observed,
    phase_unbalance_analyses: { items: [{ analysis_run_id: "" }], total: 1, truncated: false },
    file_feature_analyses: { items: [], total: 0, truncated: false },
  });
  assert.equal(data.assets.length, 1);
  assert.equal(data.analyses.available, false);
});

test("operational service faults retain their own destination without becoming asset diagnoses",()=>{
  const item={attention_id:"collection-down",title:"Collection service is not running",status:"error",destination:"system",asset_id:null,source_id:null,finding_id:null,occurred_at:"2026-10-17T00:00:00Z"};
  const result=parseMonitor({...observed,attention:{items:[item],truncated:false}});
  assert.equal(result.operationsAttention?.items[0].assetId,null);
  assert.equal(result.operationsAttention?.items[0].destination,"system");
  assert.equal(result.operationsAttention?.complete,true);
  assert.equal(parseMonitor({...observed,attention:{items:[{...item,attention_id:null}],truncated:false}}).operationsAttention?.complete,false);
});

test("server attention titles read in Korean; an unknown one falls back by where it leads", () => {
  const item = (title: string, destination: string) =>
    ({id: "a", title, status: "needs-attention", destination, assetId: null, sourceId: null, findingId: null, at: null});
  assert.equal(attentionLabel(item("Review waiting", "investigations")), "검토 대기");
  assert.equal(attentionLabel(item("No new data", "asset-signals")), "새 측정이 들어오지 않음");
  assert.equal(attentionLabel(item("Something new", "system")), "운영 서비스 확인 필요");
  assert.doesNotMatch(attentionLabel(item("Analysis service is not updating", "system")), /[A-Za-z]/);
});
