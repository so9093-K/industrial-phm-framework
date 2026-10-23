import assert from "node:assert/strict";
import {test} from "node:test";
import {defaultKind, kindsOf, methodsFor, parseAssetData} from "./asset-data.ts";
import type {Capabilities, CapabilityStatus} from "./capabilities.ts";

test("an asset's stored data kinds choose the default analysis, never another asset's", () => {
  const vibrationOnly = parseAssetData({schema_version: 1, asset_id: "bearing-a", history: null,
    acquisition: {count: 64, first: 1, last: 64, features: []}}, "bearing-a");
  assert.deepEqual(vibrationOnly, {history: null, vibration: {measurements: 64, first: 1, last: 64}});
  assert.deepEqual(kindsOf(vibrationOnly), ["vibration"]);
  assert.equal(defaultKind(vibrationOnly), "vibration");
  const both = parseAssetData({schema_version: 1, asset_id: "m", history: {channels: ["R"]},
    acquisition: {count: 3, first: 1, last: 3, features: []}}, "m");
  assert.deepEqual(kindsOf(both), ["history", "vibration"]);
  const historyOnly = parseAssetData({schema_version: 1, asset_id: "m", history: {channels: []}, acquisition: null}, "m");
  assert.equal(defaultKind(historyOnly), "history");
  assert.throws(() => parseAssetData({schema_version: 1, asset_id: "other", history: null}, "m"), /설비/);
  assert.throws(() => parseAssetData({schema_version: 1, asset_id: "m", history: {}}, "m"), /형식/);
  assert.deepEqual(parseAssetData({schema_version: 1, asset_id: "m",
    history: {channels: ["temperature"], measurement_count: 2}, acquisition: null}, "m"),
    {history: {signals: 1}, vibration: null});
});

test("unknown, absent and mixed data never invent a default kind", () => {
  assert.deepEqual(kindsOf(null), []);
  assert.deepEqual(kindsOf({history: null, vibration: null}), []);
  assert.equal(defaultKind(null), null);
  assert.equal(defaultKind({history: null, vibration: null}), null);
  assert.equal(defaultKind({history: {signals: 2}, vibration: {measurements: 4, first: 1, last: 4}}), null);
});

test("server eligibility restricts methods for each data kind", () => {
  const vibration = {history:null,vibration:{measurements:100,first:1,last:100}};
  const csv = {history:{signals:1},vibration:null};
  const mixed = {history:{signals:1},vibration:vibration.vibration};
  const cap = (compare:CapabilityStatus,relation:CapabilityStatus,spectrum:CapabilityStatus):Capabilities => ({
    assetId:"m",history:null,acquisition:null,items:[
      {id:"period-compare",status:compare,reason:"history",target:null,facts:{by_kind:{history:"unavailable",vibration:"ready"}}},
      {id:"relation",status:relation,reason:"single-signal",target:null,facts:{by_kind:{history:"unavailable",vibration:"ready"}}},
      {id:"spectrum",status:spectrum,reason:"no-waveform",target:null,facts:{}},
      {id:"anomaly",status:"ready",reason:"explore",target:null,facts:{}},
    ],
  });
  assert.deepEqual(methodsFor("change",csv,cap("unavailable","unavailable","unavailable"),"history"),[]);
  assert.deepEqual(methodsFor("change",mixed,cap("ready","ready","ready"),"history"),[]);
  assert.deepEqual(methodsFor("change",mixed,cap("ready","ready","ready"),"vibration"),["compare","relation","spectrum"]);
  assert.deepEqual(methodsFor("change",vibration,cap("ready","ready","unavailable"),"vibration"),["compare","relation"]);
  assert.deepEqual(methodsFor("anomaly",null,cap("ready","ready","ready")),[]);
  assert.deepEqual(methodsFor("change",mixed,null),[]);
  assert.deepEqual(methodsFor("change",{history:{signals:3},vibration:null},
    cap("unavailable","unavailable","unavailable"),"history"),["electrical"]);
});

test("elapsed measurement time carries its source and requires a valid recorded interval", () => {
  const read = (period_seconds: unknown) => parseAssetData({schema_version:1, asset_id:"m", history:null,
    acquisition:{count:10,first:1,last:10,source_id:"bench",period_seconds,features:[]}}, "m");
  assert.deepEqual(read(60).vibration?.timing, {sourceId:"bench",periodSeconds:60});
  for (const period of [null, undefined, 0, -1, NaN, Infinity, "60"])
    assert.equal(read(period).vibration?.timing, undefined);
});
