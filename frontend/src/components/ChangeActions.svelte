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
    {label:focus.item.unit==="V"?"상전압·전류 추이":"같은 시각의 관련 신호",href:links.signal},
    {label:"전후 분포 비교",href:links.compare},
    {label:"추세 전망·기준 도달",href:links.outlook},
  ]:[
    {label:"달라진 주파수 대역",href:links.spectrum},
    {label:"전후 진동 비교",href:links.compare},
    {label:"추세 전망·기준 도달",href:links.outlook},
  ]);
</script>
<!-- 다른 화면에서 이어 볼 분석: 같은 폭·같은 높이의 줄로. 판단은 이 아래 따로 둔다. -->
<nav aria-label="관련 분석">
  <h3>관련 분석</h3>
  <ul>
    {#each rows as row(row.label)}{#if row.href}<li><a href={row.href}
      onclick={event=>{onInvestigate?.();event.currentTarget.href=tabSelectionUrl(event.currentTarget.href,location.href);}}><span>{row.label}</span><i aria-hidden="true">→</i></a></li>{/if}{/each}
  </ul>
</nav>
<style>
  nav{display:grid;gap:6px}
  h3{margin:0;font-size:var(--font-label);font-weight:650;color:var(--color-ink-muted)}
  ul{display:grid;margin:0;padding:0;list-style:none;border:1px solid var(--color-border);border-radius:8px;overflow:hidden}
  li+li{border-top:1px solid var(--color-border)}
  a{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:38px;padding:0 12px;font-size:var(--font-small);font-weight:650;color:var(--color-action);text-decoration:none;background:var(--color-surface)}
  a:hover{background:var(--color-surface-selected)}
  a:focus-visible{outline:2px solid var(--color-action);outline-offset:-2px}
  i{font-style:normal;color:var(--color-ink-muted)}
</style>
