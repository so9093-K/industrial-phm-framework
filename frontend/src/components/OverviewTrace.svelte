<script lang="ts">
  import {tracePath, type OverviewRow} from "../asset-overview";
  import {yTicks} from "../chart-axis";
  import ValueAxis from "./ValueAxis.svelte";
  import XAxis from "./XAxis.svelte";
  let {main, range = null, height=180}: {height?:number; main: NonNullable<OverviewRow["main"]>; range?: {from: number; to: number} | null} = $props();
  const points=$derived(main.trace);
  const lo=$derived(Math.min(...points.map(point=>point.value)));
  const hi=$derived(Math.max(...points.map(point=>point.value)));
  const pad=$derived(hi>lo?(hi-lo)*.1:Math.max(Math.abs(lo)*.05,1));
  const first=$derived(Math.min(...points.map(point=>point.x)));
  const last=$derived(Math.max(...points.map(point=>point.x)));
  const x=(value:number)=>(value-first)/Math.max(last-first,1)*600;
  const y=(value:number)=>height-(value-lo+pad)/(hi-lo+2*pad)*height;
  // Missing continuity metadata is displayed as points, never an assumed continuous record.
  const path=$derived(tracePath(points.map(point=>({x:x(point.x),y:y(point.value),join:point.join}))));
</script>

{#if points.length>1}
<figure class="overview-trend" aria-label={main.label+" 기록 추이"}>
  <ValueAxis ticks={yTicks(lo-pad,hi+pad,0,height)} {height} unit={main.unit}>
    <svg viewBox={"0 0 600 "+height} style:height={height+"px"} preserveAspectRatio="none" role="img" aria-label={main.label+" · 측정 공백은 연결하지 않은 기록 추이"}>
      {#each yTicks(lo-pad,hi+pad,0,height) as tick(tick.value)}<line x1="0" x2="600" y1={tick.y} y2={tick.y} class="grid"/>{/each}
      {#if range}<rect x={x(Math.max(first,range.from))} width={Math.max(2,x(Math.min(last,range.to))-x(Math.max(first,range.from)))} y="0" height={height} class="interval"/>{/if}
      <path d={path}/>
      {#each points as point,i(i)}<circle cx={x(point.x)} cy={y(point.value)} r="2"/>{/each}
    </svg>
    {#snippet footer()}<XAxis lo={first} hi={last} scale={main.axis==="time"?{kind:"clock"}:main.periodSeconds?{kind:"elapsed",period:main.periodSeconds}:{kind:"order"}}/>{/snippet}
  </ValueAxis>
  <figcaption>{main.label} · {main.axis==="time"?"구간별 평균":"측정별 특징값"}{range?" · 음영은 발견한 변화":""}</figcaption>
</figure>
{/if}
<style>
  .interval{fill:var(--color-caution-ink);fill-opacity:.16}
  figure{max-width:100%;min-width:0;margin:var(--space-4) 0}svg{width:100%;display:block}path{fill:none;stroke:var(--color-action);stroke-width:2;vector-effect:non-scaling-stroke}circle{fill:var(--color-action)}.grid{stroke:var(--color-border);stroke-width:1;vector-effect:non-scaling-stroke}figcaption{font-size:var(--font-small);color:var(--color-ink-muted);margin-top:var(--space-2)}
</style>
