<script lang="ts">
  import ValueAxis from "./ValueAxis.svelte";
  import XAxis from "./XAxis.svelte";
  import {nearestPosition,movePosition} from "../plot-selection";
  import {snapSpan,type Span} from "../signal-selection";
  import {clockText} from "../asset-timeline";
  import {measure} from "../chart-axis";
  import type {SignalChart} from "../history";
  let {chart,origin,step,unit,label,picked,intervals=[],reference=null,referenceValue=null,onFreeze,onSelect,onCancel,onClear}:{chart:SignalChart;
    origin:number;step:number|null;unit:string|null;label:string;picked:Span|null;intervals?:Span[];reference?:Span|null;referenceValue?:number|null;
    onFreeze:()=>void;onSelect:(span:Span)=>void;onCancel:()=>void;onClear:()=>void}=$props();
  let drag:{from:number;to:number;x:number}|null=$state(null);
  let hover:number|null=$state(null),keyFocus:number|null=null,keyAnchor:number|null=null;
  const positions=$derived(chart.marks.map(mark=>Date.parse(mark.bucket.bucketStart)));
  const hovered=$derived(chart.marks.find(mark=>Date.parse(mark.bucket.bucketStart)===hover)??null);
  const baselineY=$derived(referenceValue===null?null:chart.valueY(referenceValue));
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
    onFreeze();keyFocus=null;keyAnchor=null;drag={from:point(event),to:point(event),x:event.clientX};
  }
  function move(event:PointerEvent){
    const at=point(event),nearest=nearestPosition(positions,at);
    const start=nearest!==null&&step&&nearest>at?positions[positions.indexOf(nearest)-1]??null:nearest;
    // In a measurement gap, do not offer an unrelated point from the other side of the gap.
    hover=start!==null&&(!step||at>=start&&at<start+step)?start:null;
    if(drag)drag={...drag,to:at};
  }
  function release(event:PointerEvent){
    if(!drag)return;
    const prior=drag,at=point(event);drag=null;
    onSelect(Math.abs(event.clientX-prior.x)<5?snapSpan(at,at,origin,chart.end,step):snapSpan(prior.from,at,origin,chart.end,step));
  }
  function keydown(event:KeyboardEvent){
    if(event.key==="Escape"){event.preventDefault();event.stopPropagation();drag=null;hover=null;keyFocus=null;keyAnchor=null;onClear();return;}
    if(!picked||keyFocus!==null&&(keyFocus<picked.from||keyFocus>=picked.to)){keyFocus=picked?.from??null;keyAnchor=null;}
    const at=movePosition(positions,keyFocus??picked?.from??null,event.key);
    if(at===null)return;
    event.preventDefault();onFreeze();
    if(event.shiftKey)keyAnchor??=picked?.from??at;else keyAnchor=null;
    keyFocus=at;hover=at;
    const anchor=keyAnchor??at;
    onSelect(snapSpan(Math.min(anchor,at),Math.max(anchor,at)+(step??1000)/2,origin,chart.end,step));
  }
</script>
<ValueAxis ticks={chart.ticks} height={chart.height} {unit}>
  <div class="selectable" role="slider" tabindex="0" aria-label={label+"의 조사 구간 선택"}
    aria-valuemin={positions[0]} aria-valuemax={positions.at(-1)} aria-valuenow={picked?.from??positions.at(-1)}
    aria-valuetext={picked?clockText(picked.from)+"부터 "+clockText(picked.to)+"까지":"방향키로 측정 선택, Shift와 함께 누르면 구간 선택"}
    onfocus={()=>{keyFocus=picked?.from??null;keyAnchor=null;}}
    onpointerdown={press} onpointermove={move} onpointerleave={()=>{if(!drag)hover=null;}}
    onpointerup={release} onpointercancel={()=>{drag=null;onCancel();}} onkeydown={keydown}>
    <svg viewBox={"0 0 "+chart.width+" "+chart.height} style:height={chart.height+"px"} preserveAspectRatio="none" role="img" aria-label={label+" · 구간 평균과 최소·최대, 측정이 없는 구간은 연결하지 않음"}>
      {#each chart.ticks as tick(tick.value)}<line x1="0" x2={chart.width} y1={tick.y} y2={tick.y} class="grid"/>{/each}
      {#if reference}{@const shade=band(reference)}<rect x={shade.x} width={shade.width} height={chart.height} class="reference"/>{/if}
      {#each intervals as interval(interval.from)}{@const shade=band(interval)}<rect x={shade.x} width={shade.width} height={chart.height} class="change"/>
        <line x1={shade.x} x2={shade.x} y1="0" y2={chart.height} class="change-start"/>{/each}
      {#if baselineY!==null&&referenceValue!==null}
        {@const visible=baselineY>=0&&baselineY<=chart.height}
        {#if visible}<line x1="0" x2={chart.width} y1={baselineY} y2={baselineY} class="reference-line"/>{/if}
      {/if}
      {#each chart.marks as mark(mark.bucket.bucketStart)}<line x1={mark.x} x2={mark.x} y1={mark.min} y2={mark.max} class="range"/><circle cx={mark.x} cy={mark.mean} r="2"/>{/each}
      <path d={chart.path} class="trace"/>
      {#if picked}{@const shade=band(picked)}<rect x={shade.x} width={Math.max(2,shade.width)} height={chart.height} class="picked"/>{/if}
      {#if drag}{@const shade=band({from:Math.min(drag.from,drag.to),to:Math.max(drag.from,drag.to)})}<rect x={shade.x} width={Math.max(2,shade.width)} height={chart.height} class="picked"/>{/if}
      {#if hovered}<line x1={hovered.x} x2={hovered.x} y1="0" y2={chart.height} class="cursor"/><circle cx={hovered.x} cy={hovered.mean} r="4"/>{/if}
    </svg>
    {#if baselineY!==null&&referenceValue!==null}<div class="reference-label" title="비교 구간 평균들의 중앙값" style:top={Math.max(4,Math.min(chart.height-22,baselineY-20))+"px"}>
      {baselineY<0?"↑ ":baselineY>chart.height?"↓ ":""}기준 {measure(referenceValue,unit,4)}</div>{/if}
    {#if hovered}<div class="tooltip" style:--tooltip-x={hovered.x/chart.width*100+"%"}>
      <span>{clockText(Date.parse(hovered.bucket.bucketStart))}</span><strong>평균 {measure(hovered.bucket.mean!,unit,4)}</strong>
    </div>{/if}
  </div>
  {#snippet footer()}<XAxis lo={chart.start} hi={chart.end} scale={{kind:"clock"}}/>{/snippet}
</ValueAxis>
<style>
  .selectable { position:relative; cursor:crosshair; touch-action:pan-y; outline-offset:3px; }
  .selectable:focus-visible { outline:2px solid var(--color-action); }
  svg { width:100%; display:block; }
  line,path { vector-effect:non-scaling-stroke; }
  .grid { stroke:var(--color-border); stroke-width:1; }
  .trace { fill:none; stroke:var(--color-action); stroke-width:2; }
  circle { fill:var(--color-action); }
  .range { stroke:var(--color-action); opacity:.3; stroke-width:3; }
  .reference { fill:var(--color-action); opacity:.06; }
  .reference-line { stroke:var(--color-ink-muted); stroke-dasharray:5 4; stroke-width:1.5; }
  .reference-label { position:absolute; right:4px; padding:2px 6px; background:var(--color-surface); color:var(--color-ink-muted); opacity:.95; font-size:var(--font-label); pointer-events:none; }
  .change { fill:var(--color-caution-ink); opacity:.12; }
  .change-start { stroke:var(--color-caution-ink); stroke-dasharray:3 4; stroke-width:1; opacity:.7; }
  .picked { fill:var(--color-action); fill-opacity:.09; stroke:var(--color-action); stroke-width:1.5; }
  .cursor { stroke:var(--color-ink-muted); stroke-width:1; stroke-dasharray:3 3; }
  .tooltip { position:absolute; top:6px; left:clamp(4px,var(--tooltip-x),max(4px,calc(100% - 200px))); width:196px; max-width:calc(100% - 8px); display:grid; gap:2px; padding:7px 10px; background:var(--color-surface); border:1px solid var(--color-border); border-radius:var(--radius-control); box-shadow:0 2px 8px rgb(0 0 0 / .08); pointer-events:none; font-size:var(--font-label); white-space:nowrap; }
  .tooltip span { color:var(--color-ink-muted); }
</style>
