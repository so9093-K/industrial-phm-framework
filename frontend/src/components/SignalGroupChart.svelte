<script lang="ts">
  import {signalChart,valueRange,type HistoryGroup} from "../history";
  import type {Span} from "../signal-selection";
  import PlotCursor from "./PlotCursor.svelte";
  import ValueAxis from "./ValueAxis.svelte";
  import XAxis from "./XAxis.svelte";
  let {series,from,to,bucketSeconds,picked,onPick}:{series:{id:string;label:string;unit:string|null;group:HistoryGroup}[];
    from:string;to:string;bucketSeconds:number|null;picked:Span|null;onPick:(at:number)=>void}=$props();
  const panels=$derived.by(()=>{
    const groups=new Map<string,typeof series>();
    for(const row of series){const key=row.unit?"unit:"+row.unit:"signal:"+row.id;groups.set(key,[...(groups.get(key)??[]),row]);}
    return [...groups].map(([key,rows])=>{
      const ranges=rows.map(row=>valueRange(row.group)).filter(row=>row!==null);
      const range=ranges.length?{low:Math.min(...ranges.map(row=>row.low)),high:Math.max(...ranges.map(row=>row.high))}:undefined;
      const height=groups.size===1?260:rows.some(row=>row.id===series[0]?.id)?210:130;
      return {key,unit:rows[0].unit,rows:rows.map(row=>({...row,chart:signalChart(row.group,from,to,bucketSeconds,{height,range})})),height};
    });
  });
  const lo=$derived(Date.parse(from)),hi=$derived(Date.parse(to));
  const positions=$derived([...new Set(series.flatMap(row=>row.group.buckets.filter(b=>b.mean!==null).map(b=>Date.parse(b.bucketStart))))].sort((a,b)=>a-b));
  const colors=["var(--color-action)","#bd6017","#557a47","#8c5793","#455e73"];
</script>
<div class="linked" aria-label="같은 시간축의 관련 실측 신호">
  {#each panels as panel(panel.key)}
    {@const primary=panel.rows.find(row=>row.chart)?.chart}
    {#if primary}<div class="panel"><div class="legend">{#each panel.rows as row,i(row.id)}<span><i style:border-color={colors[i%colors.length]} style:border-top-style={i%2?"dashed":"solid"}></i>{row.label}</span>{/each}</div>
      <ValueAxis ticks={primary.ticks} height={panel.height} unit={panel.unit}>
        <PlotCursor {positions} value={picked?.from??null} {lo} {hi} label="관련 신호를 확인할 측정 시점" onSelect={onPick}>
          <svg viewBox={"0 0 "+primary.width+" "+panel.height} style:height={panel.height+"px"} preserveAspectRatio="none" role="img" aria-label={panel.rows.map(row=>row.label).join(" · ")+" · 공통 시간축과 같은 단위의 눈금"}>
            {#each primary.ticks as tick(tick.value)}<line x1="0" x2={primary.width} y1={tick.y} y2={tick.y} class="grid"/>{/each}
            {#if picked}<rect x={Math.max(0,(picked.from-lo)/(hi-lo)*primary.width)} width={Math.max(2,(Math.min(picked.to,hi)-Math.max(picked.from,lo))/(hi-lo)*primary.width)} height={panel.height} class="picked"/>{/if}
            {#each panel.rows as row,i(row.id)}{#if row.chart}<path d={row.chart.path} stroke={colors[i%colors.length]} stroke-dasharray={i%2?"6 3":undefined}/>{/if}{/each}
          </svg>
        </PlotCursor>
      </ValueAxis>
    </div>{/if}
  {/each}
  <div class="time"><XAxis {lo} {hi} scale={{kind:"clock"}}/></div>
</div>
<style>
  .linked{display:grid;gap:12px;min-width:0}.legend{display:flex;gap:8px 18px;flex-wrap:wrap;margin-bottom:6px;font-size:var(--font-small)}.legend span{display:flex;align-items:center;gap:6px}.legend i{display:inline-block;width:22px;border-top:2px solid}.grid{stroke:var(--color-border);stroke-width:1}svg{display:block;width:100%}path{fill:none;stroke-width:2;vector-effect:non-scaling-stroke}.picked{fill:var(--color-action);opacity:.12}.time{padding-left:60px}
</style>
