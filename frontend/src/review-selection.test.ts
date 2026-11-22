import assert from "node:assert/strict";
import {test} from "node:test";
import {filterReviewItems, firstGroup, reviewGroup, selectReviewItem, type ReviewListItem} from "./review-selection.ts";

const entries: ReviewListItem[] = [
  {key: "finding:one", assetId: "pump-a", kind: "analysis", status: "open", group: "pending"},
  {key: "capture:two", assetId: "pump-b", kind: "outlook", status: "acknowledged", group: "inspect"},
  {key: "finding:three", assetId: "pump-b", kind: "analysis", status: "closed", group: "done"},
];

test("review judgment and kind filters keep a consistent detail selection", () => {
  const open = filterReviewItems(entries, "pending", "all");
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

test("reviews are grouped by what the person decided, and open on the first group with work", () => {
  assert.equal(reviewGroup("acknowledged", "inspect"), "inspect");
  assert.equal(reviewGroup("acknowledged", "observe"), "observe");
  assert.equal(reviewGroup("open", null), "pending");
  assert.equal(reviewGroup("acknowledged", null), "pending");
  assert.equal(reviewGroup("acknowledged", "no-action"), "done");
  assert.equal(reviewGroup("closed", "inspect"), "done");
  assert.equal(firstGroup({inspect: 0, observe: 2, pending: 1, done: 3}), "pending");
  assert.equal(firstGroup({inspect: 1, observe: 0, pending: 1, done: 0}), "inspect");
  assert.equal(firstGroup({inspect: 0, observe: 0, pending: 0, done: 4}), "all");
});
