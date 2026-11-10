<script lang="ts">
  import {onMount} from "svelte";
  import {readReviewAssetIndex} from "../review-index";
  import {routeUrl} from "../routes";

  /** The way back to stored human reviews from 관측 현황; 정비 검토 is not a top menu. The link is
   * always there: the review page finds an asset's reviews by its ID even when the list cannot be
   * read, so a failed count only says the count is unknown, never that there are none. */
  let total: number | null = $state(null);
  let readState: "loading" | "ready" | "failed" = $state("loading");
  const href = routeUrl({page: "maintenance", assetId: "", tab: "summary", method: null, data: null});
  onMount(() => {
    const request = new AbortController();
    void readReviewAssetIndex(request.signal)
      .then((index) => { if (!request.signal.aborted) { total = index.totalAssets; readState = "ready"; } })
      .catch(() => { if (!request.signal.aborted) readState = "failed"; });
    return () => request.abort();
  });
</script>

<p class="review-entry">
  {#if readState === "ready"}{(total ? "저장한 검토가 있는 설비 " + total + "곳" : "저장한 검토가 없습니다") + " · "}{:else if readState === "failed"}{"저장한 검토 건수를 확인하지 못했습니다. 검토함에서 설비 ID로 찾을 수 있습니다 · "}{/if}<a {href}>정비 검토함 열기 →</a>
</p>

<style>
  .review-entry { margin: 0 0 var(--space-4); padding: var(--space-3) var(--space-4); background: var(--color-surface);
    border: 1px solid var(--color-border); border-radius: var(--radius-panel); overflow-wrap: anywhere; }
</style>
