import assert from "node:assert/strict";
import {test} from "node:test";
import {filterReviewItems, selectReviewItem, type ReviewListItem} from "./review-selection.ts";

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
