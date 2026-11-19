<script lang="ts">
  import XAxis from "./XAxis.svelte";
  import {measure,niceTicks} from "../chart-axis";
  import {frequencyText} from "../spectrum";
  import {frequencyLabel,type FrequencyRange} from "../frequency-view";
  let {frequencies,series,domain,band=null,height=190,unit="dB",floor=-60,ceiling=0,label}:{
    frequencies:number[];series:{label:string;values:number[];comparison?:boolean}[];
    domain:FrequencyRange;band?:FrequencyRange|null;height?:number;unit?:string;
    floor?:number;ceiling?:number;label:string;
  }=$props();
  const clip=$props.id();
  const ticks=$derived(unit==="dB"?[-60,-40,-20,0]:niceTicks(floor,ceiling));
  const x=(value:number)=>800*(value-domain.from)/(domain.to-domain.from);
  const y=(value:number)=>180-180*(value-floor)/Math.max(ceiling-floor,1e-300);
  const highlight=$derived(band?{left:Math.max(0,(band.from-domain.from)/(domain.to-domain.from)),right:Math.min(1,(band.to-domain.from)/(domain.to-domain.from))}:null);
  let hovered:{index:number;left:number;top:number}|null=$state(null);
  $effect(()=>{domain;series;hovered=null;});
  function hover(event:PointerEvent){
    const box=(event.currentTarget as SVGElement).getBoundingClientRect();
    const at=domain.from+(event.clientX-box.left)/box.width*(domain.to-domain.from);
    const index=frequencies.reduce((best,hz,i)=>Math.abs(hz-at)<Math.abs(frequencies[best]-at)?i:best,0);
    hovered={index,left:Math.min(65,Math.max(0,(event.clientX-box.left)/box.width*100)),top:Math.min(height-50,Math.max(0,event.clientY-box.top+8))};
  }
  function trace(values:number[]):string {
    return frequencies.flatMap((hz,i)=>
      (hz>=domain.from&&hz<=domain.to)||(hz<domain.from&&(frequencies[i+1]??-Infinity)>=domain.from)
        ||(hz>domain.to&&(frequencies[i-1]??Infinity)<=domain.to)
      ?[x(hz).toFixed(2)+","+y(values[i]).toFixed(2)]:[]).join(" ");
  }
</script>
<div class="frequency-plot" data-hz-from={domain.from} data-hz-to={domain.to}>
  <div class="value-labels" aria-hidden="true" style:height={height+"px"}>
    <span class="unit">{unit}</span>
    {#each ticks as tick(tick)}<span style:top={(100*(ceiling-tick)/Math.max(ceiling-floor,1e-300))+"%"}>{measure(tick,null)}</span>{/each}
  </div>
  <div class="curve">
    <svg role="img" aria-label={label} viewBox="0 0 800 180" preserveAspectRatio="none" style:height={height+"px"} onpointermove={hover} onpointerleave={()=>hovered=null}>
      <defs><clipPath id={clip}><rect x="0" y="0" width="800" height="180"/></clipPath></defs>
      {#if highlight&&highlight.right>highlight.left}<rect x={highlight.left*800} width={(highlight.right-highlight.left)*800} y="0" height="180" class="band"/>{/if}
      {#each ticks as tick(tick)}<line x1="0" x2="800" y1={y(tick)} y2={y(tick)} class="grid"/>{/each}
      <g clip-path={"url(#"+clip+")"}>
        {#each series as line(line.label)}<polyline points={trace(line.values)} class:comparison={line.comparison} class:baseline={series.length>1&&!line.comparison}><title>{line.label}</title></polyline>{/each}
      </g>
    </svg>
    {#if band&&highlight&&highlight.right>highlight.left}<span class="band-label" style:left={"clamp(4.5rem,"+((highlight.left+highlight.right)/2)*100+"%,calc(100% - 4.5rem))"}>{frequencyLabel(band.from)}–{frequencyLabel(band.to)} Hz</span>{/if}
    {#if hovered}<div class="tip" style:left={"min("+hovered.left+"%,max(0px,calc(100% - 240px)))"} style:top={hovered.top+"px"}><strong>{frequencyText(frequencies[hovered.index])} Hz</strong>
      {#each series as line(line.label)}<span>{line.label} · {measure(line.values[hovered.index],unit)}</span>{/each}
    </div>{/if}
    <XAxis lo={domain.from} hi={domain.to} scale={{kind:"value"}} suffix="Hz"/>
  </div>
</div>
<style>
  .frequency-plot{display:grid;grid-template-columns:var(--frequency-gutter,4.25rem) minmax(0,1fr);gap:var(--space-2);padding-top:var(--space-5);min-width:0}
  .value-labels{position:relative;font-size:12px;color:var(--color-ink-muted);font-variant-numeric:tabular-nums}
  .value-labels>span{position:absolute;right:0;transform:translateY(-50%);line-height:1;white-space:nowrap}
  .value-labels .unit{top:-20px;transform:none;font-size:11px}.curve{position:relative;min-width:0}
  svg{display:block;width:100%;overflow:visible}polyline{fill:none;stroke:var(--color-action);stroke-width:1.8;vector-effect:non-scaling-stroke}
  polyline.baseline{stroke:var(--color-ink-muted)}polyline.comparison{stroke-dasharray:5 3}
  .grid{stroke:var(--color-border);stroke-width:1;vector-effect:non-scaling-stroke}.band{fill:var(--color-surface-selected)}
  .band-label{position:absolute;top:-21px;transform:translateX(-50%);font-size:12px;white-space:nowrap;color:var(--color-ink);max-width:100%}
  .tip{position:absolute;z-index:1;display:grid;padding:var(--space-2);font-size:12px;background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius-control);box-shadow:0 2px 8px #0002;pointer-events:none;width:max-content;max-width:min(240px,100%);overflow-wrap:anywhere}
</style>
