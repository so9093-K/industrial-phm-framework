<script lang="ts">
  import ValueAxis from "./ValueAxis.svelte";
  import XAxis from "./XAxis.svelte";
  import {nearestPosition,movePosition} from "../plot-selection";
  import {snapSpan,type Span} from "../signal-selection";
  import {clockText} from "../asset-timeline";
  import type {SignalChart} from "../history";
  let {chart,origin,step,unit,label,picked,intervals=[],reference=null,onFreeze,onSelect}:{chart:SignalChart;
    origin:number;step:number|null;unit:string|null;label:string;picked:Span|null;intervals?:Span[];reference?:Span|null;
    onFreeze:()=>void;onSelect:(span:Span)=>void}=$props();
  let drag:{from:number;to:number;x:number}|null=$state(null);
  const positions=$derived(chart.marks.map(mark=>Date.parse(mark.bucket.bucketStart)));
  const point=(event:PointerEvent)=>{
    const box=event.currentTarget instanceof HTMLElement?event.currentTarget.getBoundingClientRect():null;
    return box?chart.start+Math.max(0,Math.min(1,(event.clientX-box.left)/box.width))*(chart.end-chart.start):chart.start;
  };
  const band=(span:Span)=>({x:Math.max(0,(span.from-chart.start)/(chart.end-chart.start)*chart.width),
    width:Math.max(0,(Math.min(chart.end,span.to)-Math.max(chart.start,span.from))/(chart.end-chart.start)*chart.width)});
  function press(event:PointerEvent){
    if(event.button!==0)return;
    event.currentTarget instanceof HTMLElement&&event.currentTarget.focus();
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    onFreeze();drag={from:point(event),to:point(event),x:event.clientX};
  }
  function release(event:PointerEvent){
    if(!drag)return;
    const prior=drag;drag=null;
    const at=nearestPosition(positions,point(event));
    if(at===null)return;
    onSelect(Math.abs(event.clientX-prior.x)<5?snapSpan(at,at,origin,chart.end,step):snapSpan(prior.from,point(event),origin,chart.end,step));
  }
  function keydown(event:KeyboardEvent){
    const at=movePosition(positions,picked?.from??null,event.key);
    if(at===null)return;event.preventDefault();onFreeze();onSelect(snapSpan(at,at,origin,chart.end,step));
  }
</script>
<ValueAxis ticks={chart.ticks} height={chart.height} {unit}>
  <div class="selectable" role="slider" tabindex="0" aria-label={label+"의 조사 구간 선택"}
    aria-valuemin={positions[0]} aria-valuemax={positions.at(-1)} aria-valuenow={picked?.from??positions.at(-1)}
    aria-valuetext={picked?clockText(picked.from)+"부터 "+clockText(picked.to)+"까지":"방향키로 측정 구간 선택"}
    onpointerdown={press} onpointermove={event=>{if(drag)drag={...drag,to:point(event)};}}
    onpointerup={release} onpointercancel={()=>drag=null} onkeydown={keydown}>
    <svg viewBox={"0 0 "+chart.width+" "+chart.height} style:height={chart.height+"px"} preserveAspectRatio="none" role="img" aria-label={label+" · 구간 평균과 최소·최대, 측정이 없는 구간은 연결하지 않음"}>
      {#each chart.ticks as tick(tick.value)}<line x1="0" x2={chart.width} y1={tick.y} y2={tick.y} class="grid"/>{/each}
      {#if reference}{@const shade=band(reference)}<rect x={shade.x} width={shade.width} height={chart.height} class="reference"/>{/if}
      {#each intervals as interval(interval.from)}{@const shade=band(interval)}<rect x={shade.x} width={shade.width} height={chart.height} class="change"/>{/each}
      {#each chart.marks as mark(mark.bucket.bucketStart)}<line x1={mark.x} x2={mark.x} y1={mark.min} y2={mark.max} class="range"/><circle cx={mark.x} cy={mark.mean} r="2"/>{/each}
      <path d={chart.path} class="trace"/>
      {#if picked}{@const shade=band(picked)}<rect x={shade.x} width={Math.max(2,shade.width)} height={chart.height} class="picked"/>{/if}
      {#if drag}{@const shade=band({from:Math.min(drag.from,drag.to),to:Math.max(drag.from,drag.to)})}<rect x={shade.x} width={Math.max(2,shade.width)} height={chart.height} class="picked"/>{/if}
    </svg>
  </div>
  {#snippet footer()}<XAxis lo={chart.start} hi={chart.end} scale={{kind:"clock"}}/>{/snippet}
</ValueAxis>
<style>
  .selectable{cursor:crosshair;touch-action:pan-y;outline-offset:3px}.selectable:focus-visible{outline:2px solid var(--color-action)}svg{width:100%;display:block}
  line,path{vector-effect:non-scaling-stroke}.grid{stroke:var(--color-border);stroke-width:1}.trace{fill:none;stroke:var(--color-action);stroke-width:2}circle{fill:var(--color-action)}.range{stroke:var(--color-action);opacity:.3;stroke-width:3}.reference{fill:var(--color-action);opacity:.07}.change{fill:var(--color-caution-ink);opacity:.13}.picked{fill:var(--color-action);opacity:.16;stroke:var(--color-action);stroke-width:1}
</style>
