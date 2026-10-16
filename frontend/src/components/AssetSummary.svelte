<script lang="ts">
  import {flowLabel, type Asset} from "../monitor";
  import type {AssetData} from "../asset-data";
  import {assetTabUrl, routeUrl} from "../routes";
  import CautionNote from "./CautionNote.svelte";
  type Props = {
    asset: Asset;
    data: AssetData | null;
    dataState: "loading" | "ready" | "failed";
    pendingReviews: number | null;
    observed: (at: string | null) => string;
  };
  let {asset, data, dataState, pendingReviews, observed}: Props = $props();
  const stored = $derived.by(() => {
    if (dataState === "loading") return "확인하는 중";
    if (dataState === "failed" || !data) return "확인하지 못함";
    const parts: string[] = [];
    if (data.history) parts.push("시계열 신호 " + data.history.signals + "개");
    if (data.vibration) parts.push("진동 측정 " + data.vibration.measurements + "회 (측정 순서 #"
      + data.vibration.first + "~#" + data.vibration.last + ")");
    return parts.length ? parts.join(" · ") : "분석할 저장 데이터 없음";
  });
  function attention(count: number | null): string {
    if (count === null) return "확인하지 못함";
    return count ? count + "건" : "없음";
  }
</script>

<section class="ui-panel" aria-labelledby="summary-title">
  <h2 id="summary-title">기록 현황</h2>
  <dl class="facts">
    <div><dt>마지막 측정</dt><dd>{observed(asset.lastObservedAt)}</dd></div>
    <div><dt>수신 상태</dt><dd>{flowLabel(asset.flow)}</dd></div>
    <div><dt>확인할 항목</dt><dd>{attention(asset.attentionCount)}</dd></div>
    <div><dt>저장된 데이터</dt><dd>{stored}</dd></div>
  </dl>
  <CautionNote message="수신 상태와 확인할 항목은 기록 현황입니다. 설비의 고장 여부를 판정하지 않습니다." />
</section>

<section class="ui-panel next" aria-labelledby="next-title">
  <h2 id="next-title">다음 할 일</h2>
  <ul>
    <li><a href={assetTabUrl(asset.assetId, "anomaly")}>이상 징후 보기 →</a></li>
    <li><a href={assetTabUrl(asset.assetId, "signals")}>측정 신호 보기 →</a></li>
    <li><a href={assetTabUrl(asset.assetId, "change", "compare")}>두 기간 비교하기 →</a></li>
    <li><a href={assetTabUrl(asset.assetId, "outlook")}>기준 도달 전망 계산하기 →</a></li>
    {#if pendingReviews}
      <li><a href={routeUrl({page: "maintenance", assetId: asset.assetId, tab: "summary", method: null, data: null})}>
        검토 대기 {pendingReviews}건 보기 →</a></li>
    {/if}
  </ul>
</section>

<style>
  .facts {
    margin: 0;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: var(--space-4);
  }
  .facts div { padding-bottom: var(--space-3); border-bottom: 1px solid var(--color-border); min-width: 0; }
  dt { font-size: var(--font-small); color: var(--color-ink-muted); }
  dd { margin: var(--space-2) 0 0; font-weight: 700; overflow-wrap: anywhere; }
  .next { margin-top: var(--space-4); }
  ul { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: var(--space-3); }
  li a {
    display: inline-flex;
    align-items: center;
    min-height: 44px;
    padding: var(--space-2) var(--space-4);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-control);
    text-decoration: none;
    color: var(--color-ink);
    background: var(--color-surface);
  }
  li a:hover { background: var(--color-surface-selected); }
</style>
