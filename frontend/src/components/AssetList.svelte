<script lang="ts">
  import {assetOptionLabel, flowLabel, type Asset} from "../monitor";
  type Props = {
    assets: Asset[];
    observed: (at: string | null) => string;
    href: (assetId: string) => string;
    /** Model attention items per asset from 관측 현황, added to the monitor's own count. */
    notes?: Record<string, number>;
  };
  let {assets, observed, href, notes = {}}: Props = $props();
  const count = (asset: Asset): number | null =>
    asset.attentionCount === null && notes[asset.assetId] === undefined ? null : (asset.attentionCount ?? 0) + (notes[asset.assetId] ?? 0);
  // Assets with something to check come first; the server order is kept otherwise.
  const ordered = $derived(assets
    .map((asset, index) => ({asset, index}))
    .sort((a, b) => (count(b.asset) ?? 0) - (count(a.asset) ?? 0) || a.index - b.index)
    .map(({asset}) => asset));
  function attention(count: number | null): string {
    if (count === null) return "확인할 항목 미확인";
    return count ? "확인할 항목 " + count + "건" : "확인할 항목 없음";
  }
</script>

<section class="ui-panel" aria-labelledby="asset-list-title">
  <h2 id="asset-list-title">설비 <span>{assets.length}개</span></h2>
  <p class="context">확인할 항목이 있는 설비를 먼저 보여 줍니다. 건수는 확인할 작업량이며 고장 위험도나 정비 우선순위는 아닙니다.</p>
  <ul class="rows">
    {#each ordered as asset (asset.assetId)}
      <li>
        <a class="row" href={href(asset.assetId)}>
          <strong>{assetOptionLabel(assets, asset.assetId)}</strong>
          <span>마지막 측정 {observed(asset.lastObservedAt)}</span>
          <span>{flowLabel(asset.flow)}</span>
          <span class:attention={!!count(asset)}>{attention(count(asset))}</span>
        </a>
        {#if (notes[asset.assetId] ?? 0) > 0}
          <a class="reason-link" href={"#attention-" + encodeURIComponent(asset.assetId)}>
            이 설비의 확인 사유와 다음 행동 보기 →
          </a>
        {/if}
      </li>
    {/each}
  </ul>
</section>

<style>
  h2 span { font-weight: 400; color: var(--color-ink-muted); font-size: var(--font-small); }
  .context { color: var(--color-ink-muted); }
  .rows { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-2); }
  .row {
    display: grid;
    grid-template-columns: minmax(0, 1.4fr) minmax(0, 1.4fr) minmax(0, 1fr) minmax(0, 1fr);
    gap: var(--space-2) var(--space-4);
    align-items: center;
    padding: var(--space-4);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-control);
    color: var(--color-ink);
    text-decoration: none;
    overflow-wrap: anywhere;
  }
  .row:hover { background: var(--color-surface-selected); }
  .row span { color: var(--color-ink-muted); font-size: var(--font-small); }
  .reason-link { display: inline-block; padding: var(--space-2) var(--space-3); margin-top: var(--space-1);
    color: var(--color-action); font-weight: 650; text-decoration: underline; }
  .row .attention { color: var(--color-ink); font-weight: 700; }
  @media (max-width: 720px) { .row { grid-template-columns: 1fr; } }
</style>
