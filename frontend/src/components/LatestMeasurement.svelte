<script lang="ts">
  import type {OverviewRow} from "../asset-overview";
  import {changeValue} from "../record-findings";
  import {measurementLabel} from "../time-axis";
  let {main}:{main:OverviewRow["main"]}=$props();
  const latest=$derived(main?.latest);
  const clock=$derived(latest?.at?new Date(latest.at).toLocaleString("ko-KR",{timeZone:"Asia/Seoul",year:"numeric",month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit",hour12:false}):null);
</script>
{#if main && latest}
<p class="last-reading" aria-label="마지막 저장값">
  <span>마지막 저장값 · {main.label}</span> <strong class="latest">{changeValue(latest.value,main.unit)}</strong>
  <span class="when">{clock??(latest.position!==null?measurementLabel(latest.position,main.periodSeconds):"측정 시각 기록 없음")}</span>
</p>
{/if}
<style>
  .last-reading{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px var(--space-2);margin:var(--space-2) 0;font-size:var(--font-small);color:var(--color-ink-muted);overflow-wrap:anywhere}
  strong{color:var(--color-ink);font-variant-numeric:tabular-nums}.when{font-size:var(--font-label)}
</style>
