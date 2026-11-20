<script lang="ts">
  import {findingLinks} from "../record-findings";
  import {vibrationLinks} from "../vibration-findings";
  import {assetTabUrl, tabSelectionUrl} from "../routes";
  import type {EvidenceFocus} from "../change-evidence";
  let {assetId, focus}: {assetId: string; focus: EvidenceFocus} = $props();
  const links = $derived.by(() => {
    if (focus.kind === "history") {
      const own = findingLinks(assetId, focus.item, focus.record.baseline, focus.record.bucketSeconds, focus.record.record);
      return {compare: own.compare ?? own.previous, signal: own.signal, relation: own.relation?.href, spectrum: null, outlook: own.outlook};
    }
    const own = vibrationLinks(assetId, focus.change), related = focus.change.related[0];
    return {compare: own.compare, signal: own.signal, spectrum: own.spectrum, outlook: own.outlook,
      relation: related ? assetTabUrl(assetId, "change", "relation", "vibration") : null};
  });
  const rows = $derived([
    {label: "변화 구간 비교", href: links.compare, primary: true},
    {label: "원본 신호", href: links.signal},
    {label: "주파수", href: links.spectrum},
    {label: "신호 관계", href: links.relation},
    {label: "전망·예상 여유", href: links.outlook},
  ]);
</script>
<nav aria-label="이 변화의 분석">
  {#each rows as row(row.label)}{#if row.href}<a class:primary={row.primary} class:ui-button={row.primary} class:ui-button-primary={row.primary} href={row.href}
    onclick={event=>event.currentTarget.href=tabSelectionUrl(event.currentTarget.href,location.href)}>{row.label}{row.primary?" →":""}</a>{/if}{/each}
</nav>
<style>
  nav{display:flex;flex-wrap:wrap;align-items:center;gap:var(--space-2) var(--space-4)}
  a{font-size:var(--font-small);font-weight:650;color:var(--color-action);text-underline-offset:3px;padding-block:6px}
  .primary{display:inline-flex;align-items:center;padding:var(--control-padding);color:var(--color-action-ink);text-decoration:none}
</style>
