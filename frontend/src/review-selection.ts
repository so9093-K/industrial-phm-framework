/** User-facing review selection: a filtered list cannot silently display another item. */
export type ReviewKind = "analysis" | "outlook" | "change";
export type ReviewStatus = "open" | "acknowledged" | "closed";

/** 사람이 할 일로 나눈 검토. 처리 상태(대기·확인·종료)가 아니라 남긴 판단으로 나눈다. */
export type ReviewGroup = "inspect" | "observe" | "pending" | "done";
export const REVIEW_GROUPS: readonly ReviewGroup[] = ["inspect", "observe", "pending", "done"];
export const GROUP_LABEL: Record<ReviewGroup, string> = {
  inspect: "추가 점검 필요", observe: "계속 관찰", pending: "판단 전", done: "점검 불필요·종료",
};
export function reviewGroup(status: ReviewStatus, decision: "inspect" | "observe" | "no-action" | null): ReviewGroup {
  if (status === "closed" || decision === "no-action") return "done";
  return decision ?? "pending";
}
/** 처음 여는 칸: 할 일이 있는 첫 칸(추가 점검 필요 → 판단 전 → 계속 관찰), 없으면 전체. */
export function firstGroup(counts: Record<ReviewGroup, number>): ReviewGroup | "all" {
  return (["inspect", "pending", "observe"] as const).find(group => counts[group] > 0) ?? "all";
}

export interface ReviewListItem {
  key: string;
  assetId: string;
  kind: ReviewKind;
  status: ReviewStatus;
  group: ReviewGroup;
}

export function filterReviewItems<T extends ReviewListItem>(
  items: readonly T[],
  group: ReviewGroup | "all",
  kind: ReviewKind | "all",
): T[] {
  return items.filter((item) =>
    (group === "all" || item.group === group) && (kind === "all" || item.kind === kind));
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
