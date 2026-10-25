<script lang="ts">
  import {onMount} from "svelte";
  import {readReviewAssetIndex} from "../review-index";
  import {routeUrl} from "../routes";

  /** The way back to stored human reviews from 관측 현황; 정비 검토 is not a top menu.
   * Shown only when the server lists an asset with a review subject; an unread index stays silent. */
  let total: number | null = $state(null);
  const href = routeUrl({page: "maintenance", assetId: "", tab: "summary", method: null, data: null});
  onMount(() => {
    const request = new AbortController();
    void readReviewAssetIndex(request.signal)
      .then((index) => { if (!request.signal.aborted) total = index.totalAssets; })
      .catch(() => {});
    return () => request.abort();
  });
</script>

{#if total}
  <p class="review-entry">검토 요청이 있는 설비 {total}곳 · <a {href}>정비 검토함 열기 →</a></p>
{/if}

<style>
  .review-entry { margin: 0 0 var(--space-4); padding: var(--space-3) var(--space-4); background: var(--color-surface);
    border: 1px solid var(--color-border); border-radius: var(--radius-panel); overflow-wrap: anywhere; }
</style>
