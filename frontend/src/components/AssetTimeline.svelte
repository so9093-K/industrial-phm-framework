<script lang="ts">
  import type {Snippet} from "svelte";
  import XAxis from "./XAxis.svelte";
  import PlotCursor from "./PlotCursor.svelte";
  import ModelScoreTracks from "./ModelScoreTracks.svelte";
  import ChangeNumbers from "./ChangeNumbers.svelte";
  import {measure,niceTicks} from "../chart-axis";
  import {measurementScale} from "../time-axis";
  import {bandName} from "../record-findings";
  import {versusStart} from "../change-story";
  import {clockText,focusWindow,spanText,startsZoomed,valueAt,visiblePoints,type Span,type TimelineLane,type TimelineModel,type TimelineOperation} from "../asset-timeline";
  /** One observation first; more signals and model curves are an explicit comparison. */
  let {axis,record,episode,ongoing,episodes=[],lanes,operation=null,models=[],periodSeconds=null,selected=null,onSelect,onFocus,actions}:{
    axis:"time"|"acquisition";record:Span;episode:Span;ongoing:boolean;
    episodes?:{label:string;selected:boolean;onPick:()=>void}[];lanes:TimelineLane[];operation?:TimelineOperation|null;models?:TimelineModel[];
    actions?:Snippet;periodSeconds?:number|null;selected?:number|null;onSelect?:(at:number)=>void;onFocus?:(key:string)=>void}=$props();
  const W=1000;
  let zoomed=$state(false),comparing=$state(false);
  const focused=$derived(lanes.find(lane=>lane.focus)??lanes[0]);
  $effect(()=>{zoomed=startsZoomed(record,episode);});
  const range=$derived(zoomed?focusWindow(record,episode):record);
  const lo=$derived(range.from),hi=$derived(Math.max(range.to,range.from+1));
  const x=(at:number)=>(at-lo)/(hi-lo)*W,clamp=(at:number)=>Math.max(0,Math.min(W,x(at)));
  const place=(at:number)=>axis==="time"?clockText(at):at+"번째 측정";
  const span=(r:Span)=>axis==="time"?spanText(r.from,r.to):r.from+"–"+r.to+"번째 측정";
  const scale=$derived(axis==="time"?{kind:"clock" as const}:measurementScale(periodSeconds));
  const displayed=$derived(comparing?[focused,...lanes.filter(l=>l!==focused)].filter((l):l is TimelineLane=>!!l):focused?[focused]:[]);
  const related=$derived(lanes.filter(lane=>lane!==focused));
  const primaryPoints=$derived(focused?visiblePoints(focused,record,zoomed):[]);
  const at=$derived(selected??primaryPoints.at(-1)?.x??null);
  const reading=$derived(at===null?null:valueAt(primaryPoints,at,0));
  function shape(lane:TimelineLane,height:number){
    const points=visiblePoints(lane,range,zoomed),values=points.map(p=>p.value);
    const low=Math.min(lane.usual.low,...values),high=Math.max(lane.usual.high,...values),pad=high>low?(high-low)*.12:Math.max(Math.abs(low)*.05,1);
    const y=(v:number)=>height-(v-low+pad)/(high-low+2*pad)*height;
    return {points,y,ticks:niceTicks(low-pad,high+pad,4).map(value=>({value,top:y(value)/height*100})).filter(p=>p.top>4&&p.top<96),
      path:points.map((p,i)=>(i&&p.join===true?"L":"M")+x(p.x).toFixed(1)+" "+y(p.value).toFixed(1)).join(" ")};
  }
</script>
{#if focused}
<section class="timeline" aria-label="선택한 변화">
  <header class="headline"><div><h2>{focused.label} · 초기보다 {focused.up?"높음":"낮음"}</h2>
    <p>{span(focused.interval)}{ongoing?" · 기록 끝까지 이어짐":""}{focused.condition?" · "+focused.condition+" 중":""}</p></div>
    <label class="signal-choice">조사할 신호<select value={focused.key} onchange={e=>onFocus?.(e.currentTarget.value)}>{#each lanes as lane(lane.key)}<option value={lane.key}>{lane.label}</option>{/each}</select></label>
  </header>
  {#if focused.values}<ChangeNumbers facts={{label:focused.label,unit:focused.unit,direction:focused.up?"up":"down",reference:focused.values.before,typical:focused.values.after}} fallback={focused.numbers} spanCaption={span(focused.interval)} latest={focused.values.latest?{caption:"마지막 · "+place(focused.values.latest.at),value:measure(focused.values.latest.value,focused.unit),note:versusStart(focused.values.latest.value,focused.values.before,focused.unit)}:null}/>{:else}<p class="numbers">{focused.numbers}</p>{/if}
  {#if actions}{@render actions()}{/if}
  <div class="toolbar"><div class="choices" role="group" aria-label="보는 범위"><button type="button" aria-pressed={!zoomed} onclick={()=>zoomed=false}>기록 전체</button><button type="button" aria-pressed={zoomed} onclick={()=>zoomed=true}>변화 구간 확대</button></div>
    {#if episodes.length>1}<div class="choices" role="group" aria-label="변화 시기">{#each episodes as item(item.label)}<button type="button" aria-pressed={item.selected} onclick={item.onPick}>{item.label}</button>{/each}</div>{/if}
    <button type="button" class="compare-toggle" aria-pressed={comparing} onclick={()=>comparing=!comparing}>{comparing?"선택 신호만 보기":"관련 신호·모델 함께 보기"}</button>
  </div>
  {#each displayed as lane(lane.key)}{@const height=lane.focus?230:130}{@const drawing=shape(lane,height)}
    {#if comparing}<div class="lane-heading"><strong>{lane.label}</strong><span>{lane.numbers}</span></div>{/if}
    <div class="chart"><div class="gutter" style:height={height+"px"}>{#each drawing.ticks as tick(tick.value)}<span style:top={tick.top+"%"}>{measure(tick.value,lane.unit)}</span>{/each}</div>
      <PlotCursor positions={drawing.points.map(p=>p.x)} value={at} {lo} {hi} label={lane.focus?"실제 측정 선택":lane.label+" 측정 선택"} {onSelect}><div class="plot">
        <svg viewBox={"0 0 "+W+" "+height} style:height={height+"px"} preserveAspectRatio="none" role="img" aria-label={lane.label+" · 초기 범위와 변화 구간 · 측정 공백은 연결하지 않음"}>
          {#each drawing.ticks as tick(tick.value)}<line x1="0" x2={W} y1={drawing.y(tick.value)} y2={drawing.y(tick.value)} class="grid"/>{/each}
          <rect width={W} y={drawing.y(lane.usual.high)} height={Math.max(1,drawing.y(lane.usual.low)-drawing.y(lane.usual.high))} class="usual"/><rect x={clamp(lane.interval.from)} width={Math.max(1,clamp(lane.interval.to)-clamp(lane.interval.from))} height={height} class="interval"/>
          <path d={drawing.path} class="trace"/>{#each drawing.points.length<180?drawing.points:[] as point(point.x)}<circle cx={x(point.x)} cy={drawing.y(point.value)} r="2"/>{/each}
          {#if at!==null&&at>=lo&&at<=hi}<line x1={x(at)} x2={x(at)} y1="0" y2={height} class="cursor"/>{/if}
        </svg><span class="onset" style:left={Math.min(80,clamp(lane.interval.from)/10)+"%"}>{place(lane.interval.from)}부터</span></div></PlotCursor>
      <div class="footer"><XAxis {lo} {hi} {scale}/></div>
    </div>
  {/each}
  <div class="chart-caption"><p class="key"><i class="usual-key"></i>초기 범위 · 기록 처음 30% <i class="interval-key"></i>변화 구간</p>{#if reading}<output>{place(reading.x)} · {measure(reading.value,focused.unit)}</output>{/if}</div>
  {#if comparing}
    {#if operation}<div class="lane-heading"><strong>운전 수준</strong><span>{operation.names.levels.map((_,i)=>bandName(operation.names,i+1)).join(" · ")}</span></div>
      <div class="chart"><div></div><svg viewBox={"0 0 "+W+" 32"} style:height="32px" preserveAspectRatio="none" role="img" aria-label="같은 시각의 운전 수준 비율">{#each operation.columns.filter(c=>c.to>=lo&&c.from<=hi) as col(col.from)}{@const width=Math.max(1,clamp(col.to)-clamp(col.from))}{#each col.shares as share,i(i)}<rect x={clamp(col.from)} width={width} y={col.shares.slice(0,i).reduce((a,b)=>a+b,0)*32} height={share*32} fill="var(--color-action)" opacity={i===0?.06:.25+.75*i/col.shares.length}/>{/each}{/each}</svg></div>{/if}
    {#if models.length}<div class="chart"><div></div><ModelScoreTracks {models} {lo} {hi} selected={at} {onSelect} range={focused.interval}/></div>{/if}
  {:else if related.length}<div class="related" aria-label="같은 시기에 달라진 신호"><h3>같은 시기의 다른 변화</h3>{#each related as lane(lane.key)}<button type="button" onclick={()=>onFocus?.(lane.key)}><strong>{lane.label}</strong><span>{span(lane.interval)}</span><small>{lane.numbers}</small></button>{/each}</div>{/if}
  {#if focused.decision}<p class="decision">남긴 판단 · {focused.decision}</p>{/if}
</section>
{/if}
<style>
  .timeline{display:grid;gap:var(--space-3);min-width:0}.headline{display:flex;align-items:start;justify-content:space-between;flex-wrap:wrap;gap:var(--space-3)}h2{margin:0;font-size:1.4rem;line-height:1.4}.headline p{margin:5px 0 0;font-size:var(--font-small);color:var(--color-ink-muted)}.signal-choice{display:grid;gap:4px;font-size:var(--font-label);min-width:220px}.signal-choice select{padding:8px}.numbers{margin:0;font-size:var(--font-section);font-weight:650}
  .toolbar{display:flex;align-items:center;flex-wrap:wrap;gap:var(--space-2);padding-block:var(--space-1)}.choices{display:inline-flex;border:1px solid var(--color-control-border);border-radius:var(--radius-control);overflow:hidden}button{cursor:pointer;font:inherit}.choices button{padding:6px 10px;font-size:var(--font-small);border:0;background:var(--color-surface);color:var(--color-ink)}.choices button+button{border-left:1px solid var(--color-border)}.choices button[aria-pressed="true"]{background:var(--color-surface-selected);color:var(--color-action);font-weight:650}.compare-toggle{margin-left:auto;border:0;background:none;color:var(--color-action);font-size:var(--font-small);text-decoration:underline;text-underline-offset:3px;padding:7px}
  .chart{display:grid;grid-template-columns:56px minmax(0,1fr);column-gap:8px;min-width:0}.gutter{position:relative;font-size:var(--font-label);color:var(--color-ink-muted)}.gutter span{position:absolute;right:0;transform:translateY(-50%);white-space:nowrap}.footer{grid-column:2}.plot{position:relative;border-bottom:1px solid var(--color-border)}svg{display:block;width:100%}svg path,svg line{vector-effect:non-scaling-stroke}.grid{stroke:var(--color-border);stroke-width:1}.usual{fill:var(--color-ink);opacity:.07}.interval{fill:var(--color-caution-ink);opacity:.12}.trace{fill:none;stroke:var(--color-action);stroke-width:2}circle{fill:var(--color-action)}.cursor{stroke:var(--color-ink);stroke-width:1;stroke-dasharray:3 3}.onset{position:absolute;top:5px;white-space:nowrap;background:var(--color-surface);padding:0 4px;border-radius:3px;font-size:var(--font-label);color:var(--color-caution-ink)}
  .chart-caption{display:flex;align-items:baseline;flex-wrap:wrap;justify-content:space-between;gap:var(--space-2);font-size:var(--font-label)}.key{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:0;color:var(--color-ink-muted)}.key i{display:inline-block;width:14px;height:9px}.usual-key{background:var(--color-ink);opacity:.12}.interval-key{background:var(--color-caution-ink);opacity:.25}output{font-weight:650;font-variant-numeric:tabular-nums}.lane-heading{display:flex;align-items:baseline;flex-wrap:wrap;justify-content:space-between;gap:6px;font-size:var(--font-small)}.lane-heading span{color:var(--color-ink-muted)}
  .related{display:flex;flex-wrap:wrap;gap:var(--space-2);border-top:1px solid var(--color-border);padding-top:var(--space-3)}.related h3{flex-basis:100%;font-size:var(--font-small);margin:0;color:var(--color-ink-muted)}.related button{display:grid;gap:3px;flex:1;min-width:200px;max-width:480px;text-align:left;border:1px solid var(--color-border);border-radius:var(--radius-control);background:var(--color-surface);padding:10px;color:var(--color-ink);font-size:var(--font-small)}.related button:hover{border-color:var(--color-action);background:var(--color-surface-selected)}.related span,.related small{color:var(--color-ink-muted);font-size:var(--font-label)}.decision{margin:0;font-size:var(--font-small);color:var(--color-action)}
</style>
