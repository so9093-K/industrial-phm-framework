<script lang="ts">
  import {findingLinks,relatedSignalHref} from "../record-findings";
  import {vibrationLinks} from "../vibration-findings";
  import {tabSelectionUrl} from "../routes";
  import type {EvidenceFocus} from "../change-evidence";
  let {assetId, focus,onInvestigate}: {assetId: string; focus: EvidenceFocus;onInvestigate?:()=>void} = $props();
  const links = $derived.by(() => {
    if (focus.kind === "history") {
      const own = findingLinks(assetId, focus.item, focus.record.baseline, focus.record.bucketSeconds, focus.record.record);
      return {compare: own.compare ?? own.previous, signal: own.signal?relatedSignalHref(own.signal,focus.item,focus.record.signals):null, spectrum: null, outlook: own.outlook};
    }
    const own = vibrationLinks(assetId, focus.change);
    return {compare: own.compare, signal: own.signal, spectrum: own.spectrum, outlook: own.outlook,
      };
  });
  const rows = $derived(focus.kind==="history"?[
    {label:focus.item.unit==="V"?"다른 상전압·전류 함께 보기":"같은 시각의 관련 신호",href:links.signal,primary:true},
    {label:"전후 값·분포 비교",href:links.compare},
    {label:"추세·기준까지의 여유",href:links.outlook},
  ]:[
    {label:"변화한 주파수 대역 확인",href:links.spectrum,primary:true},
    {label:"전후 진동 비교",href:links.compare},
    {label:"추세·기준까지의 여유",href:links.outlook},
  ]);
</script>
<nav aria-label="이 특이사항의 분석">
  {#each rows as row(row.label)}{#if row.href}<a class="ui-button" class:primary={row.primary} class:ui-button-primary={row.primary} href={row.href}
    onclick={event=>{onInvestigate?.();event.currentTarget.href=tabSelectionUrl(event.currentTarget.href,location.href);}}>{row.label}{row.primary?" →":""}</a>{/if}{/each}
</nav>
<style>
  nav{display:flex;flex-wrap:wrap;align-items:center;gap:var(--space-2) var(--space-4)}
  /* 동작은 두 모양뿐: 주요 동작 하나(채움)와 나머지(테두리). 화면 이동과 창 열기를 모양으로 나누지 않는다. */
  a{display:inline-flex;align-items:center;font-size:var(--font-small);font-weight:650;text-decoration:none}
  a:not(.primary){color:var(--color-action)}
  .primary{color:var(--color-action-ink)}
</style>
