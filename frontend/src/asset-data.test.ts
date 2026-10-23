import assert from "node:assert/strict";
import {test} from "node:test";
import {defaultKind, kindsOf, methodsFor, parseAssetData} from "./asset-data.ts";

test("an asset's stored data kinds choose the default analysis, never another asset's", () => {
  const vibrationOnly = parseAssetData({schema_version: 1, asset_id: "bearing-a", history: null,
    acquisition: {count: 64, first: 1, last: 64, series: []}}, "bearing-a");
  assert.deepEqual(vibrationOnly, {history: null, vibration: {measurements: 64, first: 1, last: 64}});
  assert.deepEqual(kindsOf(vibrationOnly), ["vibration"]);
  assert.equal(defaultKind(vibrationOnly), "vibration");
  const both = parseAssetData({schema_version: 1, asset_id: "m", history: {series: [{key: "R"}]},
    acquisition: {count: 3, first: 1, last: 3}}, "m");
  assert.deepEqual(kindsOf(both), ["history", "vibration"]);
  const historyOnly = parseAssetData({schema_version: 1, asset_id: "m", history: {series: []}}, "m");
  assert.equal(defaultKind(historyOnly), "history");
  assert.throws(() => parseAssetData({schema_version: 1, asset_id: "other", history: null}, "m"), /설비/);
  assert.throws(() => parseAssetData({schema_version: 1, asset_id: "m", history: {}}, "m"), /형식/);
});

test("unknown, absent and mixed data never invent a default kind", () => {
  assert.deepEqual(kindsOf(null), []);
  assert.deepEqual(kindsOf({history: null, vibration: null}), []);
  assert.equal(defaultKind(null), null);
  assert.equal(defaultKind({history: null, vibration: null}), null);
  assert.equal(defaultKind({history: {signals: 2}, vibration: {measurements: 4, first: 1, last: 4}}), null);
});

test("only the methods an asset's data supports are offered", () => {
  const vibration = {history: null, vibration: {measurements: 100, first: 1, last: 100}};
  const csv = {history: {signals: 2}, vibration: null};
  assert.deepEqual(methodsFor("anomaly", vibration), ["model"]);
  assert.deepEqual(methodsFor("change", vibration), ["compare", "relation", "spectrum"]);
  assert.deepEqual(methodsFor("change", csv), ["compare", "relation", "electrical"]);
  assert.deepEqual(methodsFor("anomaly", null), []);
  assert.deepEqual(methodsFor("change", {history: null, vibration: null}), []);
  assert.deepEqual(methodsFor("signals", csv), []);
});

test("elapsed measurement time carries its source and requires a valid recorded interval", () => {
  const read = (period_seconds: unknown) => parseAssetData({schema_version:1, asset_id:"m", history:null,
    acquisition:{count:10,first:1,last:10,source_id:"bench",period_seconds}}, "m");
  assert.deepEqual(read(60).vibration?.timing, {sourceId:"bench",periodSeconds:60});
  for (const period of [null, undefined, 0, -1, NaN, Infinity, "60"])
    assert.equal(read(period).vibration?.timing, undefined);
});
