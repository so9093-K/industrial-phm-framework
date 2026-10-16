import assert from "node:assert/strict";
import {test} from "node:test";
import {defaultKind, kindsOf, parseAssetData} from "./asset-data.ts";

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

test("unknown or empty availability offers both kinds instead of hiding one", () => {
  assert.deepEqual(kindsOf(null), ["history", "vibration"]);
  assert.deepEqual(kindsOf({history: null, vibration: null}), ["history", "vibration"]);
  assert.equal(defaultKind(null), "history");
});
