/** User-facing review selection: a filtered list cannot silently display another item. */
export type ReviewKind = "analysis" | "outlook";
export type ReviewStatus = "open" | "acknowledged" | "closed";

export interface ReviewListItem {
  key: string;
  assetId: string;
  kind: ReviewKind;
  status: ReviewStatus;
}

export function filterReviewItems<T extends ReviewListItem>(
  items: readonly T[],
  status: ReviewStatus | "all",
  kind: ReviewKind | "all",
): T[] {
  return items.filter((item) =>
    (status === "all" || item.status === status) && (kind === "all" || item.kind === kind));
}

export function selectReviewItem<T extends ReviewListItem>(
  visible: readonly T[],
  exact: {key: string; assetId: string} | null,
  keptKey: string | null,
): T | undefined {
  if (exact?.key) {
    const found = visible.find((item) => item.key === exact.key && item.assetId === exact.assetId);
    if (found) return found;
    return undefined; // Never substitute a different subject for a requested bookmark.
  }
  return visible.find((item) => item.key === keptKey) ?? visible[0];
}
