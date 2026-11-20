<script lang="ts">
  import {assetOptionLabel,type Asset} from "../monitor";
  import AssetName from "./AssetName.svelte";
  let {assets,href,selected=""}:{assets:Asset[];href:(id:string)=>string;selected?:string}=$props();
</script>
<nav class="asset-switch" aria-label="관측할 설비 선택">
  <a class="all" href="/web/">← 전체 설비</a>
  <div class="choices">{#each assets as asset(asset.assetId)}<a href={href(asset.assetId)} aria-current={selected===asset.assetId?"page":undefined}><AssetName label={assetOptionLabel(assets,asset.assetId)}/></a>{/each}</div>
</nav>
<style>
  .asset-switch{display:flex;align-items:center;gap:16px;min-width:0}.all{flex:none;font-size:var(--font-small);font-weight:650;color:var(--color-action)}.choices{display:flex;gap:6px;overflow-x:auto;min-width:0}.choices a{display:inline-flex;align-items:baseline;gap:4px;padding:8px 12px;white-space:nowrap;border-radius:var(--radius-control);border:1px solid transparent;color:var(--color-ink-muted);text-decoration:none;font-size:var(--font-small)}.choices a[aria-current="page"]{color:var(--color-action);background:var(--color-surface-selected);border-color:var(--color-border);font-weight:650}.choices a:hover{border-color:var(--color-action)}
</style>
