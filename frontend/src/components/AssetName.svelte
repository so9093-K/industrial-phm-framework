<script lang="ts">
  import {assetNameParts} from "../monitor";
  let {label}: {label: string} = $props();
  const parts = $derived(assetNameParts(label));
</script>
<span class="asset-name">{parts.name}{#if parts.number}<span class="number">{parts.number}</span>{/if}</span>
<style>
  .asset-name{display:inline-flex;align-items:baseline;gap:7px;flex-wrap:wrap}.number{font-size:.8em;font-weight:550;color:var(--color-ink-muted);font-variant-numeric:tabular-nums}
</style>
