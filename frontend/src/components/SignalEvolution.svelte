<script lang="ts">
  import type {SignalEvolution} from "../signal-evolution";
  import {measure} from "../chart-axis";
  import {versusStart} from "../change-story";
  let {data,unit}:{data:SignalEvolution;unit:string|null}=$props();
  const samples=$derived(data.rateUnit==="acquisition"?"회":"개 구간");
  const rows=$derived([{name:"직전 "+data.ratePoints+samples,value:data.earlierRate},{name:"최근 "+data.ratePoints+samples,value:data.rate}]);
  // 진동 측정은 마지막 측정이 지금의 상태다. 대표값(중앙값)은 마지막 급상승을 가려 AI·관제 카드와 다른 배수를 낸다.
  const counted=$derived(data.rateUnit==="acquisition"&&data.latest!==null);
  const limit=$derived(Math.max(Math.abs(data.rate),Math.abs(data.earlierRate??0),1e-12));
  const suffix=$derived((unit?unit+"/":"/")+({acquisition:"회",hour:"시간",day:"일"}[data.rateUnit]));
  const rate=(v:number)=>(v>0?"+":"")+measure(v,suffix);
  const relative=$derived(versusStart(data.recentMedian,data.baselineMedian,unit));
</script>
<section class="evolution" aria-label="실제로 측정된 값의 변화 속도">
  {#if counted}
    <header><h4>측정값 변화 속도</h4><span>마지막 측정 <b>{measure(data.latest!,unit)}</b></span></header>
  {:else}
    <!-- 대표값(중앙값)과 속도(기울기의 중앙값)는 마지막 급등을 가린다. 마지막 값을 함께 둔다. -->
    <header><h4>측정값 변화 속도</h4><span>최근 {data.recentPoints}{samples} 대표값 <b>{measure(data.recentMedian,unit)}</b>
      {#if relative} · {relative}{/if}{#if data.latest!==null}{" · 마지막 값 "}<b>{measure(data.latest,unit)}</b>{/if}</span></header>
  {/if}
  <div class="rates">
    {#each rows as row,i(row.name)}
      <div class="rate" class:recent={i===1}><span>{row.name}</span>
        <div class="track"><i class="zero"></i>{#if row.value!==null}<i class="bar" style:left={(row.value<0?50-Math.abs(row.value)/limit*50:50)+"%"} style:width={Math.abs(row.value)/limit*50+"%"}></i>{/if}</div>
        <strong>{row.value===null?"비교할 기록 부족":rate(row.value)}</strong></div>
    {/each}
  </div>
</section>
<style>
  .evolution{display:grid;gap:var(--space-2);margin:var(--space-3) 0;padding:var(--space-3) 0;border-block:1px solid var(--color-border)}
  header{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:var(--space-2)}
  h4{font-size:var(--font-small);margin:0}header span{font-size:var(--font-label);color:var(--color-ink-muted)}
  .rates{display:grid;gap:6px}.rate{display:grid;grid-template-columns:5.5rem minmax(40px,1fr) 8.5rem;gap:var(--space-3);align-items:center;font-size:var(--font-label)}
  strong{font-weight:650;font-variant-numeric:tabular-nums;text-align:right}.track{position:relative;height:14px;background:var(--color-surface-selected)}
  .zero{position:absolute;left:50%;height:100%;border-left:1px solid var(--color-control-border)}.bar{position:absolute;top:3px;height:8px;background:var(--color-ink-muted)}
  .recent .bar{background:var(--color-action)}
</style>
