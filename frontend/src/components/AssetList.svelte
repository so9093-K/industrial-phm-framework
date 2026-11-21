<script lang="ts">
  import {assetOptionLabel,type Asset} from "../monitor";
  import AssetName from "./AssetName.svelte";
  let {assets,href,selected=""}:{assets:Asset[];href:(id:string)=>string;selected?:string}=$props();
</script>
<!-- 다른 설비는 데이터셋 관제에서 고른다. 여기서는 돌아가는 길과 지금 설비 이름만. -->
<nav class="asset-switch" aria-label="설비 조사">
  <a class="all" href="/web/">← 데이터셋 관제</a>
  {#if selected}<a class="current" href={href(selected)} aria-current="page"><AssetName label={assetOptionLabel(assets,selected)}/></a>{/if}
</nav>
<style>
  .asset-switch{display:flex;align-items:baseline;gap:16px;min-width:0}.all{flex:none;font-size:var(--font-small);font-weight:650;color:var(--color-action)}.current{font-size:1.15rem;font-weight:700;color:var(--color-ink);text-decoration:none}
</style>
