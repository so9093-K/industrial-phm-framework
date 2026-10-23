import assert from "node:assert/strict";
import {test} from "node:test";
import {parseReviewAssetIndex} from "./review-index.ts";

const base={schema_version:1, meaning:"stored-human-review-asset-identities-not-health"};

test("server-owned asset index preserves sorted identities and a bounded continuation",()=>{
  const first=parseReviewAssetIndex({...base,asset_ids:["asset-a","asset-b"],total_assets:3,next_after:"asset-b"});
  assert.deepEqual(first.assets,["asset-a","asset-b"]);
  assert.equal(first.nextAfter,"asset-b");
  assert.equal(parseReviewAssetIndex({...base,asset_ids:[],total_assets:0,next_after:null}).nextAfter,null);
});

test("index cannot silently accept another owner's cursor, duplicates or invalid IDs",()=>{
  for(const value of [
    {...base,asset_ids:["asset-b","asset-a"],total_assets:2,next_after:null},
    {...base,asset_ids:["asset-a","asset-a"],total_assets:2,next_after:null},
    {...base,asset_ids:["asset-a"],total_assets:1,next_after:"asset-b"},
    {...base,asset_ids:["asset-a\n"],total_assets:1,next_after:null},
    {...base,asset_ids:[],total_assets:0,next_after:"asset-a"},
  ])assert.throws(()=>parseReviewAssetIndex(value),/검토/);
});
