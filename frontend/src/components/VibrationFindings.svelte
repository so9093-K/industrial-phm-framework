<script lang="ts">
  import OverviewTrace from "./OverviewTrace.svelte";
  import {measurementLabel} from "../time-axis";
  import {changeValue} from "../record-findings";
  import {CHANGE_WHY, changeHeadline} from "../change-story";
  import {tick,untrack} from "svelte";
  import ChangeReview from "./ChangeReview.svelte";
  import ChangeNumbers from "./ChangeNumbers.svelte";
  import {vibrationLinks, type VibrationChange, type VibrationFindings} from "../vibration-findings";

  /** 진동 측정 기록에서 고른 변화 하나. 그래프는 이미 기록 전체를 측정 회차로 보여 준다. */
  let {assetId, record, change,onReviewed=()=>{},draftNote=null}: {assetId: string; record: VibrationFindings; change: VibrationChange;onReviewed?:()=>void;draftNote?:{sequence:number;text:string}|null} = $props();
  let reviewOpen=$state(false),reviewPanel:HTMLDetailsElement|null=$state(null);
  async function openReview(){reviewOpen=true;await tick();reviewPanel?.querySelector('summary')?.focus();reviewPanel?.scrollIntoView({block:'nearest'});}
  $effect(()=>{if(draftNote)untrack(()=>void openReview());});
  const place = (at: number) => measurementLabel(at, record.periodSeconds);
  const links = $derived(vibrationLinks(assetId, change));
</script>

<h3 class="change-sentence">{changeHeadline(change)}</h3>
<p class="context">{place(change.from)}부터 {change.to===record.last?"마지막 측정":place(change.to)}까지 · {change.to-change.from+1}회</p>
<div class="card-top">
  <ChangeNumbers facts={change} fallback={"가장 " + (change.direction === "up" ? "높을" : "낮을") + " 때 " + changeValue(change.value, change.unit)} />
  <div class="finding-actions"><a class="ui-button ui-button-primary" href={links.signal}>변화가 시작된 측정 보기 →</a>
    <a href={links.compare}>처음 30%와 비교 →</a>
    {#if change.reviewKey}<button type="button" class="ui-button" onclick={()=>void openReview()}>판단·메모</button>{/if}</div>
</div>
{#if change.reviewKey}<details class="review" bind:open={reviewOpen} bind:this={reviewPanel}><summary>이 변화의 판단·메모</summary>
  {#if reviewOpen}<ChangeReview {assetId} finding={change} {draftNote} onCommitted={onReviewed}/>{/if}
</details>{/if}
<OverviewTrace main={{label:change.label,unit:change.unit,axis:"acquisition",periodSeconds:record.periodSeconds,latest:null,trace:change.trace.map(point=>({x:point.at,value:point.value,join:point.join}))}} range={change} height={260}/>
<div class="card-foot">
  {#if change.related.length}<p><strong>같은 측정에서 함께 달라진 특징</strong> {change.related.map(other => other.label + " " + changeValue(other.reference, null) + " → " + changeValue(other.current, other.unit)).join(" · ")}</p>{/if}
  <p class="context">비교한 처음 30% · {place(change.baseline.from)} ~ {place(change.baseline.to)}{#if change.reason} · {CHANGE_WHY[change.reason]}{/if}</p>
</div>

<style>
  .card-foot { display: grid; gap: var(--space-1); font-size: var(--font-small); }
  .card-foot p { margin: 0; overflow-wrap: anywhere; }
  .context { color: var(--color-ink-muted); }
</style>
