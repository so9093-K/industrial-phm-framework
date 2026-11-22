<script lang="ts">
  import ValueAxis from "./ValueAxis.svelte";
  import XAxis from "./XAxis.svelte";
  import {niceTicks,yTicks} from "../chart-axis";
  import {num} from "../format";
  type Period="a"|"b";
  type Point={x:number;y:number;label:string};
  let {groups,bounds,xLabel,yLabel,picked=null,band=null,onPick}:{
    groups:{period:Period;label:string;points:Point[]}[];
    bounds:{xmin:number;xmax:number;ymin:number;ymax:number};xLabel:string;yLabel:string;
    picked?:{period:Period;index:number}|null;band?:{low:number;high:number}|null;
    onPick:(period:Period,index:number)=>void;
  }=$props();
  let zoom:Period|null=$state(null);
  const visible=$derived(groups.filter(group=>zoom===null||group.period===zoom));
  const scale=$derived.by(()=>{
    const points=visible.flatMap(group=>group.points);
    const own=zoom!==null&&points.length?{xmin:Math.min(...points.map(p=>p.x)),xmax:Math.max(...points.map(p=>p.x)),ymin:Math.min(...points.map(p=>p.y)),ymax:Math.max(...points.map(p=>p.y))}:bounds;
    const xp=(own.xmax-own.xmin||Math.abs(own.xmin)*.05||1)*.06;
    const yp=(own.ymax-own.ymin||Math.abs(own.ymin)*.05||1)*.06;
    return {lo:own.xmin-xp,hi:own.xmax+xp,bottom:own.ymin-yp,top:own.ymax+yp};
  });
  const x=(v:number)=>800*(v-scale.lo)/(scale.hi-scale.lo);
  const y=(v:number)=>300-300*(v-scale.bottom)/(scale.top-scale.bottom);
  const selected=$derived(groups.find(group=>group.period===picked?.period));
  const point=$derived(picked?selected?.points[picked.index]:null);
  const navigated=$derived((zoom!==null?groups.find(group=>group.period===zoom):selected)??groups.find(group=>group.period==="b")??groups[0]);
  const index=$derived(picked?.period===navigated?.period?picked.index:0);
  const colors={a:"var(--color-reference-line)",b:"var(--color-action)"};
  function pick(event:MouseEvent){
    const box=(event.currentTarget as Element).getBoundingClientRect();let best:{period:Period;index:number}|null=null,dist=Infinity;
    for(const group of visible)group.points.forEach((point,index)=>{
      const dx=x(point.x)/800*box.width-(event.clientX-box.left),dy=y(point.y)/300*box.height-(event.clientY-box.top);
      if(dx*dx+dy*dy<dist){dist=dx*dx+dy*dy;best={period:group.period,index};}
    });
    if(best){const chosen=best as {period:Period;index:number};onPick(chosen.period,chosen.index);}
  }
</script>

<figure class="relation-plot">
  <header class="plot-toolbar"><div class="legend">{#each groups as group(group.period)}<span><i class:a={group.period==="a"} style:--series={colors[group.period]}></i>{group.label}</span>{/each}</div>
    <div class="zoom" role="group" aria-label="관계 그래프 확대"><button type="button" aria-pressed={zoom===null} onclick={()=>zoom=null}>전체 비교</button>{#each groups as group(group.period)}<button type="button" aria-pressed={zoom===group.period} onclick={()=>{zoom=group.period;if(picked?.period!==group.period&&group.points.length)onPick(group.period,0);}}>{group.label} 확대</button>{/each}</div>
  </header>
  <p class="axis-name">{yLabel}</p>
  <ValueAxis ticks={yTicks(scale.bottom,scale.top,0,300,5)} height={300} unit={null}>
    <svg viewBox="0 0 800 300" preserveAspectRatio="none" role="img" aria-label={xLabel+"과 "+yLabel+"의 전후 분포 비교"}>
      {#each yTicks(scale.bottom,scale.top,0,300,5) as tick(tick.value)}<line x1="0" x2="800" y1={tick.y} y2={tick.y} class="grid"/>{/each}
      {#each niceTicks(scale.lo,scale.hi) as tick(tick)}<line x1={x(tick)} x2={x(tick)} y1="0" y2="300" class="grid"/>{/each}
      {#if band&&zoom===null}<rect x={x(band.low)} y="0" width={Math.max(2,x(band.high)-x(band.low))} height="300" class="band"><title>같은 입력 범위의 측정 비교</title></rect>{/if}
      {#each visible as group(group.period)}{#each group.points as point,i(i)}<circle cx={x(point.x)} cy={y(point.y)} r={group.period==="a"?3.5:3} fill={group.period==="a"?"var(--color-surface)":colors[group.period]} stroke={colors[group.period]} stroke-width={group.period==="a"?1.2:0} opacity={group.period==="a"?.75:.7}>
        <title>{group.label} · {point.label} · {xLabel} {num(point.x)} · {yLabel} {num(point.y)}</title>
      </circle>{/each}{/each}
      {#if point&&picked&&(zoom===null||zoom===picked.period)}<circle cx={x(point.x)} cy={y(point.y)} r="7" class="picked"/>{/if}
      <rect x="0" y="0" width="800" height="300" class="hit" role="presentation" onclick={pick}/>
    </svg>
    {#snippet footer()}<XAxis lo={scale.lo} hi={scale.hi} scale={{kind:"value"}} note={xLabel}/>{/snippet}
  </ValueAxis>
  <footer class="navigation">
    {#if navigated&&navigated.points.length}<label>측정 선택 <select aria-label="점을 선택할 기간" value={navigated.period} onchange={e=>{const period=e.currentTarget.value as Period;if(zoom!==null)zoom=period;onPick(period,0);}}>{#each groups as group(group.period)}<option value={group.period}>{group.label}</option>{/each}</select></label>
      <button type="button" aria-label="이전 측정" disabled={index<=0} onclick={()=>onPick(navigated.period,index-1)}>←</button>
      <input type="range" aria-label="측정 순서로 점 선택" min="0" max={navigated.points.length-1} step="1" value={index} aria-valuetext={navigated.points[index]?.label} oninput={e=>onPick(navigated.period,Number(e.currentTarget.value))} onfocus={()=>{if(!picked||picked.period!==navigated.period)onPick(navigated.period,0);}}/>
      <button type="button" aria-label="다음 측정" disabled={index>=navigated.points.length-1} onclick={()=>onPick(navigated.period,index+1)}>→</button>
      <output>{point?.label??"점을 선택하면 측정값을 확인합니다"}</output>
    {/if}
  </footer>
</figure>
<style>
  .relation-plot{margin:0;min-width:0}.plot-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:12px}.legend{display:flex;gap:16px;font-size:var(--font-small);font-weight:600}.legend span{display:flex;gap:6px;align-items:center}.legend i{width:8px;height:8px;border-radius:50%;background:var(--series);border:1.5px solid var(--series)}.legend i.a{background:white}
  .zoom{display:flex;gap:3px}.zoom button{border:0;background:transparent;color:var(--color-ink-muted);border-radius:5px;padding:5px 8px;font:inherit;font-size:12px;cursor:pointer}.zoom button[aria-pressed="true"]{background:var(--color-surface-selected);color:var(--color-action);font-weight:650}
  .axis-name{margin:0 0 10px;font-size:12px;color:var(--color-ink-muted)}svg{display:block;width:100%;height:300px;overflow:hidden}.grid{stroke:var(--color-border);stroke-width:1}svg circle,svg line{vector-effect:non-scaling-stroke}.band{fill:var(--color-change-fill)}.picked{fill:none;stroke:var(--color-ink);stroke-width:2.5}.hit{fill:transparent;cursor:crosshair}
  .navigation{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin-top:8px;font-size:12px;color:var(--color-ink-muted)}.navigation label{display:flex;align-items:center;gap:6px}.navigation select,.navigation button{min-height:30px;padding:3px 8px;border:1px solid var(--color-control-border);border-radius:5px;color:var(--color-ink);background:var(--color-surface);font:inherit}.navigation input{width:140px;min-width:60px;accent-color:var(--color-action)}.navigation output{margin-left:auto;font-variant-numeric:tabular-nums}
  @media(max-width:600px){.navigation output{flex-basis:100%;margin-left:0}.plot-toolbar{align-items:start}.zoom{flex-wrap:wrap}svg{height:300px}}
</style>
