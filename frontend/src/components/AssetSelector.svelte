<script lang="ts">
  import type { Asset } from "../monitor";
  type Props = {
    assets: Asset[];
    selectedId: string;
    onSelect: (id: string) => void;
    observed: (at: string | null) => string;
  };
  let { assets, selectedId, onSelect, observed }: Props = $props();
</script>

<section class="asset-list ui-panel" aria-labelledby="asset-title">
  <h2 id="asset-title">조회된 설비 <span>{assets.length}개</span></h2>
  <div class="asset-choices">
    {#each assets as asset (asset.assetId)}
      <button
        class="ui-button"
        type="button"
        class:active={selectedId === asset.assetId}
        aria-pressed={selectedId === asset.assetId}
        onclick={() => onSelect(asset.assetId)}
      >
        <strong>{asset.assetId}</strong>
        <span>마지막 관측: {observed(asset.lastObservedAt)}</span>
      </button>
    {/each}
  </div>
</section>

<style>
  h2 span { font-weight: 400; color: var(--color-ink-muted); font-size: var(--font-small); }
  .asset-choices { display: grid; gap: var(--space-2); }
  .asset-choices button {
    display: grid;
    gap: var(--space-1);
    text-align: left;
    overflow-wrap: anywhere;
    min-width: 0;
    background: var(--color-surface);
  }
  .asset-choices button span { font-size: var(--font-label); color: var(--color-ink-muted); }
  .asset-choices button.active {
    background: var(--color-surface-selected);
    border: 2px solid var(--color-action);
  }
</style>
