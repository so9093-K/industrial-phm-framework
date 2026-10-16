<script lang="ts">
  import type { Asset } from "../monitor";
  import StatusNotice from "./StatusNotice.svelte";

  type Props = {
    asset: Asset | undefined;
    observed: (at: string | null) => string;
    detailUrl: (assetId: string) => string;
  };
  let { asset, observed, detailUrl }: Props = $props();
</script>

<section class="detail ui-panel" aria-labelledby="detail-title">
  <h2 id="detail-title">선택한 설비의 관측 사실</h2>
  {#if asset}
    <dl class="facts">
      <div><dt>설비 식별자</dt><dd>{asset.assetId}</dd></div>
      <div><dt>마지막 관측 시각</dt><dd>{observed(asset.lastObservedAt)}</dd></div>
      <div><dt>데이터 흐름 상태(서버 제공 값)</dt><dd>{asset.flow}</dd></div>
      <div><dt>확인 항목 수</dt><dd>{asset.attentionCount ?? "미확인"}</dd></div>
    </dl>
    <p class="explain">수집 상태와 설비의 정상·고장 상태는 다릅니다. 이 화면은 고장 진단이나 실시간 경보가 아닙니다.</p>
    <nav class="detail-actions" aria-label="관측 근거 이동">
      <a class="ui-link-primary detail-link" href={"/web-next/?view=signals&monitor_asset=" + encodeURIComponent(asset.assetId)}>저장 신호 탐색하기 →</a>
      <a class="legacy-link" href={detailUrl(asset.assetId)}>기존 운영 화면에서 원본 신호 확인 →</a>
    </nav>
  {:else}
    <StatusNotice message="설비를 선택하면 마지막 관측 근거를 표시합니다." />
  {/if}
</section>

<style>
  .facts {
    margin: 0;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: var(--space-4);
  }
  .facts div { padding-bottom: var(--space-3); border-bottom: 1px solid var(--color-border); min-width: 0; }
  dt { font-size: var(--font-small); color: var(--color-ink-muted); }
  dd { margin: var(--space-2) 0 0; font-weight: 650; overflow-wrap: anywhere; }
  .explain { color: var(--color-ink-muted); margin-block: var(--space-6) var(--space-4); }
  .detail-actions { display: grid; justify-items: start; gap: var(--space-3); }
  .detail-link { margin-top: var(--space-4); }
  .legacy-link { color: var(--color-action); }
  @media (max-width: 440px) { .facts { grid-template-columns: 1fr; } }
</style>
