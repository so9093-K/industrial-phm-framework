import assert from "node:assert/strict";
import {test} from "node:test";
import {filterReviewItems, selectReviewItem, selectReviewAssets, type ReviewListItem} from "./review-selection.ts";

const entries: ReviewListItem[] = [
  {key: "finding:one", assetId: "pump-a", kind: "analysis", status: "open"},
  {key: "capture:two", assetId: "pump-b", kind: "outlook", status: "acknowledged"},
  {key: "finding:three", assetId: "pump-b", kind: "analysis", status: "closed"},
];

test("review status and kind filters keep a consistent detail selection", () => {
  const open = filterReviewItems(entries, "open", "all");
  assert.deepEqual(open.map((item) => item.key), ["finding:one"]);
  assert.equal(selectReviewItem(open, null, "capture:two")?.key, "finding:one");
  const outlooks = filterReviewItems(entries, "all", "outlook");
  assert.equal(selectReviewItem(outlooks, null, null)?.key, "capture:two");
});

test("bookmark never borrows a subject from another asset or an unseen record", () => {
  assert.equal(selectReviewItem(entries, {assetId: "pump-a", key: "capture:two"}, null), undefined);
  assert.equal(selectReviewItem(entries, {assetId: "pump-a", key: "finding:missing"}, null), undefined);
  assert.equal(selectReviewItem(entries, {assetId: "pump-b", key: "capture:two"}, null)?.status, "acknowledged");
});

test("after review is updated, explicit selection remains visible under all-status filter", () => {
  const all = filterReviewItems(entries, "all", "all");
  assert.equal(selectReviewItem(all, null, "finding:three")?.key, "finding:three");
});

test("limited review queue reports omitted assets and permits exact-owner direct access", () => {
  const ids = Array.from({length: 22}, (_, index) => "asset-" + index);
  const general = selectReviewAssets([...ids, "asset-0"], "", 20);
  assert.equal(general.assets.length, 20);
  assert.equal(general.partial, true);
  const scoped = selectReviewAssets(ids, "asset-21", 20);
  assert.deepEqual(scoped.assets, ["asset-21"]);
  assert.equal(scoped.partial, true);
  assert.deepEqual(selectReviewAssets(["asset-a", "asset-a"], "asset-a", 20).assets, ["asset-a"]);
});

