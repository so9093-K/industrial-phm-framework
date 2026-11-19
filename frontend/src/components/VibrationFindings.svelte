<script lang="ts">
  import OverviewTrace from "./OverviewTrace.svelte";
  import {measurementLabel} from "../time-axis";
  import {changeValue} from "../record-findings";
  import {changeConclusion, latestNumber} from "../change-story";
  import ChangeNumbers from "./ChangeNumbers.svelte";
  import {vibrationLinks, type VibrationChange, type VibrationFindings} from "../vibration-findings";

  /** 진동 측정 기록에서 고른 변화 하나: 결론, 숫자, 기록 전체를 측정 회차로 그린 그래프 하나. */
  let {assetId, record, change}: {assetId: string; record: VibrationFindings; change: VibrationChange} = $props();
  const place = (at: number) => measurementLabel(at, record.periodSeconds);
  const links = $derived(vibrationLinks(assetId, change));
  // 변화가 기록 끝까지 이어졌으면 마지막 측정의 값이 '지금'이다.
  const last = $derived(change.to === record.last ? change.trace.at(-1) : undefined);
  const latest = $derived(last && last.at === record.last
    ? latestNumber("마지막 측정", last.value, change.typical, change.unit) : null);
</script>

<div class="change-lead"><div class="lead-copy"><h3 class="change-sentence">{changeConclusion(change, latest && last ? {latest: {caption: "마지막 측정값", value: last.value}}
  : {span: place(change.from) + "부터 " + place(change.to) + "까지 " + (change.to - change.from + 1) + "회 동안"})}</h3>
{#if latest}<p class="context">{place(change.from)}부터 마지막 측정까지 · {change.to-change.from+1}회</p>{/if}
</div>
<ChangeNumbers facts={change} {latest} fallback={"가장 " + (change.direction === "up" ? "높을" : "낮을") + " 때 " + changeValue(change.value, change.unit)} />
</div>
<OverviewTrace main={{label:change.label,unit:change.unit,axis:"acquisition",periodSeconds:record.periodSeconds,latest:null,trace:change.trace.map(point=>({x:point.at,value:point.value,join:point.join}))}} range={change} height={240}/>
<p class="chart-link"><a href={links.signal}>변화가 시작된 측정의 원본 보기 →</a></p>

<style>
  .context { margin: 0; color: var(--color-ink-muted); }
  .chart-link { margin: 0; font-size: var(--font-small); }
</style>
