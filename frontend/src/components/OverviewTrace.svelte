<script lang="ts">
  import {tracePath, type OverviewRow} from "../asset-overview";
  import {yTicks} from "../chart-axis";
  import ValueAxis from "./ValueAxis.svelte";
  import XAxis from "./XAxis.svelte";
  import ModelRugs from "./ModelRugs.svelte";
  import type {ModelRug} from "../model-context";
  /** 기록 추이 하나. 변화가 있으면 변화 판단 범위(처음 30% 기준)(띠), 변화 구간(음영), 꼭 봐야 할 측정(표시)을
   * 그래프 위에 직접 그린다. 설명 문장은 여기 그려진 것을 가리키기만 한다. */
  type Mark = {at: number; value: number; label: string};
  let {main, range = null, usual = null, marks = [], rugs = [], height = 180}: {height?: number; main: NonNullable<OverviewRow["main"]>;
    range?: {from: number; to: number} | null; usual?: {low: number; high: number} | null; marks?: Mark[]; rugs?: ModelRug[]} = $props();
  const points=$derived(main.trace);
  // 처음 범위도 세로축 안에 들어야 값이 그 범위를 얼마나 벗어났는지 보인다.
  const lo=$derived(Math.min(...points.map(point=>point.value), usual?.low ?? Infinity));
  const hi=$derived(Math.max(...points.map(point=>point.value), usual?.high ?? -Infinity));
  const pad=$derived(hi>lo?(hi-lo)*.1:Math.max(Math.abs(lo)*.05,1));
  const first=$derived(Math.min(...points.map(point=>point.x)));
  const last=$derived(Math.max(...points.map(point=>point.x)));
  const x=(value:number)=>(value-first)/Math.max(last-first,1)*600;
  const y=(value:number)=>height-(value-lo+pad)/(hi-lo+2*pad)*height;
  // Missing continuity metadata is displayed as points, never an assumed continuous record.
  const path=$derived(tracePath(points.map(point=>({x:x(point.x),y:y(point.value),join:point.join}))));
  const left=(at:number)=>Math.min(100,Math.max(0,x(at)/6));
</script>

{#if points.length>1}
<figure class="overview-trend" aria-label={main.label+" 기록 추이"}>
  <ValueAxis ticks={yTicks(lo-pad,hi+pad,0,height)} {height} unit={main.unit}>
    <div class="plot">
      <svg viewBox={"0 0 600 "+height} style:height={height+"px"} preserveAspectRatio="none" role="img" aria-label={main.label+" · 측정 공백은 연결하지 않은 기록 추이"}>
        {#each yTicks(lo-pad,hi+pad,0,height) as tick(tick.value)}<line x1="0" x2="600" y1={tick.y} y2={tick.y} class="grid"/>{/each}
        {#if usual}<rect x="0" width="600" y={y(usual.high)} height={Math.max(1,y(usual.low)-y(usual.high))} class="usual"/>{/if}
        {#if range}<rect x={x(Math.max(first,range.from))} width={Math.max(2,x(Math.min(last,range.to))-x(Math.max(first,range.from)))} y="0" height={height} class="interval"/>{/if}
      {#each marks as mark (mark.at)}<line x1={x(mark.at)} x2={x(mark.at)} y1="0" y2={height} class="mark"/>{/each}
        <path d={path}/>
        {#each points as point,i(i)}<circle cx={x(point.x)} cy={y(point.value)} r="2"/>{/each}
      </svg>
      {#if usual}<span class="tag usual-tag" style:left="4px" style:top={(y(usual.high)/height*100)+"%"}>초기 범위</span>{/if}
      {#if range}<span class="tag interval-tag" style:left={left(Math.max(first, range.from))+"%"}>변화 구간</span>{/if}
      {#each marks as mark (mark.at)}
        <span class="note" class:right={left(mark.at)>55} style:left={left(mark.at)+"%"} style:top={Math.min(88,Math.max(4,y(mark.value)/height*100))+"%"}>{mark.label}</span>
      {/each}
    </div>
    {#snippet footer()}<XAxis lo={first} hi={last} scale={main.axis==="time"?{kind:"clock"}:main.periodSeconds?{kind:"elapsed",period:main.periodSeconds}:{kind:"order"}}/>
      <ModelRugs {rugs} lo={first} hi={last}/>{/snippet}
  </ValueAxis>
  <figcaption>{main.label} · {main.axis==="time"?"구간별 평균":"측정별 값"}{usual ? " · 초기 = 기록 처음 30%" : ""}</figcaption>
</figure>
{/if}
<style>
  .plot{position:relative}
  .usual{fill:var(--color-ink);fill-opacity:.08}
  .interval{fill:var(--color-caution-ink);fill-opacity:.16}
  .mark{stroke:var(--color-caution-ink);stroke-width:1.5;stroke-dasharray:4 4;vector-effect:non-scaling-stroke}
  .note{position:absolute;transform:translate(6px,-50%);font-size:var(--font-label);font-weight:650;color:var(--color-ink);background:var(--color-surface);padding:1px 4px;border-radius:3px;white-space:nowrap;pointer-events:none}
  .note.right{transform:translate(calc(-100% - 6px),-50%)}
  .tag{position:absolute;transform:translateY(-50%);font-size:var(--font-label);color:var(--color-ink-muted);pointer-events:none;white-space:nowrap}
  .usual-tag{transform:translateY(-110%)}
  .interval-tag{top:10px;transform:translateX(6px);color:var(--color-caution-ink);font-weight:650}
  figure{max-width:100%;min-width:0;margin:var(--space-4) 0}svg{width:100%;display:block}path{fill:none;stroke:var(--color-action);stroke-width:2;vector-effect:non-scaling-stroke}circle{fill:var(--color-action)}.grid{stroke:var(--color-border);stroke-width:1;vector-effect:non-scaling-stroke}
  figcaption{font-size:var(--font-small);color:var(--color-ink-muted);margin-top:var(--space-2)}
</style>
