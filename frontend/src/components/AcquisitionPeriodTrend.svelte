<script lang="ts">
  import {onMount} from "svelte";
  import {readAcquisitionTrend,type AcquisitionTrend} from "../acquisition-trend";
  import type {FeatureSource} from "../acquisition-profile";
  import type {Spans} from "../spectrum";
  import {measurementLabel,measurementScale,elapsedText} from "../time-axis";
  import {measure,yTicks} from "../chart-axis";
  import {periodOnset} from "../analysis-messages";
  import StatusNotice from "./StatusNotice.svelte";
  import ValueAxis from "./ValueAxis.svelte";
  import XAxis from "./XAxis.svelte";

  /** 두 기간의 측정별 값. 기간마다 음영과 이름표, 기간 A 값의 90% 범위(5~95%)를 가로 띠로 그리고,
   * B에서 처음 그 범위를 벗어난 측정을 표시한다. '범위 밖 n회'라는 숫자가 그래프에서 그대로 보이게 한다. */
  let {source,feature,spans,names={a:"기간 A",b:"기간 B"},usual=null}:{source:FeatureSource;feature:string;spans:Spans;
    names?:{a:string;b:string};usual?:{low:number;high:number}|null}=$props();
  let trend:AcquisitionTrend|null=$state(null);
  let loadState:"loading"|"ready"|"failed"=$state("loading");
  let error=$state("");
  let request:AbortController|null=null;
  const chart=$derived.by(()=>{
    const read:AcquisitionTrend|null=trend;
    if(!read)return null;
    const first=Math.min(spans.a.from,spans.b.from),last=Math.max(spans.a.to,spans.b.to);
    const points=read.points.filter(p=>first<=p.ordinal&&p.ordinal<=last);
    if(!points.length)return null;
    const low=Math.min(...points.map(p=>p.value),usual?.low??Infinity),high=Math.max(...points.map(p=>p.value),usual?.high??-Infinity);
    const pad=low===high?Math.max(Math.abs(low)*0.05,1):(high-low)*0.06;
    const x=(at:number)=>800*(at-first)/Math.max(1,last-first);
    const y=(value:number)=>220-220*(value-low+pad)/(high-low+2*pad);
    const marks=points.map(p=>({...p,x:x(p.ordinal),y:y(p.value)}));
    // 일부만 고른 기록에서는 '처음 벗어난 측정'이 빠졌을 수 있어 표시하지 않는다.
    const onset=usual&&!read.sampled?periodOnset(read.points,spans.b,usual.low,usual.high):null;
    return {first,last,x,y,marks,onset,ticks:yTicks(low-pad,high+pad,0,220),
      path:marks.map((p,i)=>(i&&p.ordinal===marks[i-1].ordinal+1?"L":"M")+p.x+" "+p.y).join(" ")};
  });
  async function load(){
    request?.abort();const pending=new AbortController();request=pending;
    loadState="loading";trend=null;error="";
    try{
      const read=await readAcquisitionTrend(source.assetId,feature,pending.signal);
      if(pending.signal.aborted)return;
      if(read.sourceId!==source.sourceId||read.bindingId!==source.bindingId)
        throw new Error("구간 비교와 다른 출처·모델의 시간 추이는 표시하지 않습니다.");
      trend=read;loadState="ready";
    }catch(cause:unknown){
      if(pending.signal.aborted)return;
      loadState="failed";error=cause instanceof Error?cause.message:"시간 추이를 읽지 못했습니다.";
    }
  }
  onMount(()=>{void load();return()=>request?.abort();});
</script>

<section aria-labelledby="period-trend-title">
  <h3 id="period-trend-title">측정별 값</h3>
  {#if loadState==="loading"}<StatusNotice message="같은 진동 특징의 측정별 추이를 불러오고 있습니다."/>
  {:else if loadState==="failed"}
    <StatusNotice kind="failure" title="시간 추이를 불러오지 못했습니다" message={error}
      actionLabel="시간 추이 다시 불러오기" onAction={()=>void load()}/>
  {:else if !chart||!trend}<StatusNotice message="선택한 구간에 그릴 측정값이 없습니다. 아래 집계도 함께 확인하세요."/>
  {:else}
    {@const read=trend}
    {@const plot=chart}
    {@const at=(ordinal:number)=>Math.min(100,Math.max(0,plot.x(ordinal)/8))}
    <figure>
      <ValueAxis ticks={plot.ticks} height={220} unit={read.unit}>
        <div class="plot">
        <svg viewBox="0 0 800 220" preserveAspectRatio="none" role="img"
          aria-label={read.label+" 측정별 값. "+names.a+"와 "+names.b+"를 음영으로 표시합니다."}>
          {#each ["a","b"] as key(key)}
            {@const span=spans[key as "a"|"b"]}
            <rect x={plot.x(span.from)} y="0" width={Math.max(2,plot.x(span.to)-plot.x(span.from))} height="220" class={"band "+key}>
              <title>{key==="a"?names.a:names.b} · {measurementLabel(span.from,read.periodSeconds)} ~ {measurementLabel(span.to,read.periodSeconds)}</title>
            </rect>
          {/each}
          {#if usual}<rect x="0" width="800" y={plot.y(usual.high)} height={Math.max(1,plot.y(usual.low)-plot.y(usual.high))} class="usual"/>{/if}
          {#each plot.ticks as tick(tick.value)}<line x1="0" x2="800" y1={tick.y} y2={tick.y} class="grid"/>{/each}
          {#if plot.onset}<line x1={plot.x(plot.onset.first)} x2={plot.x(plot.onset.first)} y1="0" y2="220" class="onset"/>{/if}
          <path d={plot.path} class="line"/>
          {#each plot.marks as point(point.ordinal)}<circle cx={point.x} cy={point.y} r="3">
            <title>{measurementLabel(point.ordinal,read.periodSeconds)} · {measure(point.value,read.unit)}</title>
          </circle>{/each}
        </svg>
        {#each ["a","b"] as key(key)}
          <span class={"tag "+key} style:left={at(spans[key as "a"|"b"].from)+"%"}>{key==="a"?names.a:names.b}</span>
        {/each}
        {#if usual}<span class="tag usual-tag" style:top={plot.y(usual.high)/220*100+"%"}>{names.a} 값의 90% 범위</span>{/if}
        {#if plot.onset}<span class="note" class:leftward={at(plot.onset.first)>60} style:left={at(plot.onset.first)+"%"}>{plot.onset.first}번째 측정{plot.onset.stayed?"부터 범위 밖":" 초기 범위 밖"}</span>{/if}
        </div>
        {#snippet footer()}<XAxis lo={plot.first} hi={plot.last} scale={measurementScale(read.periodSeconds)}
          note={read.periodSeconds?"경과 시간 · 측정 간격 "+elapsedText(read.periodSeconds):"측정 회차"}/>{/snippet}
      </ValueAxis>
    </figure>
    {#if read.sampled}<p class="sampled">기록이 많아 고르게 선택한 일부 측정만 표시합니다. 표시한 점의 수와 아래 전체 구간 집계는 다를 수 있습니다.</p>{/if}
  {/if}
</section>

<style>
  section{min-width:0}figure{margin:var(--space-3) 0}svg{display:block;width:100%;height:220px}
  svg line,svg path,svg circle{vector-effect:non-scaling-stroke}
  .band.a{fill:var(--color-ink-muted);fill-opacity:0.12}.band.b{fill:var(--color-action);fill-opacity:0.12}
  .usual{fill:var(--color-ink);fill-opacity:.08}
  .onset{stroke:var(--color-caution-ink);stroke-width:1.5;stroke-dasharray:4 4}
  .plot{position:relative}
  .tag,.note{position:absolute;font-size:var(--font-label);white-space:nowrap;pointer-events:none}
  .tag{top:4px;transform:translateX(6px);font-weight:650}.tag.a{color:var(--color-ink-muted)}.tag.b{color:var(--color-action)}
  .usual-tag{left:4px;transform:translateY(-110%);color:var(--color-ink-muted);font-weight:400}
  .note{top:24px;transform:translateX(6px);font-weight:650;color:var(--color-ink);background:var(--color-surface);padding:1px 4px;border-radius:3px}
  .note.leftward{transform:translateX(calc(-100% - 6px))}
  .grid{stroke:var(--color-border);stroke-width:1}.line{stroke:var(--color-action);stroke-width:2;fill:none}circle{fill:var(--color-action)}
  .sampled{color:var(--color-ink-muted);font-size:var(--font-small);overflow-wrap:anywhere}
</style>
