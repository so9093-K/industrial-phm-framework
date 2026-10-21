<script lang="ts">
  import {onMount} from "svelte";
  import {readAcquisitionTrend,type AcquisitionTrend} from "../acquisition-trend";
  import type {FeatureSource} from "../acquisition-profile";
  import type {Spans} from "../spectrum";
  import {measurementLabel,measurementScale,elapsedText} from "../time-axis";
  import {measure,yTicks} from "../chart-axis";
  import StatusNotice from "./StatusNotice.svelte";
  import ValueAxis from "./ValueAxis.svelte";
  import XAxis from "./XAxis.svelte";

  let {source,feature,spans}:{source:FeatureSource;feature:string;spans:Spans}=$props();
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
    const low=Math.min(...points.map(p=>p.value)),high=Math.max(...points.map(p=>p.value));
    const pad=low===high?Math.max(Math.abs(low)*0.05,1):(high-low)*0.06;
    const x=(at:number)=>800*(at-first)/Math.max(1,last-first);
    const y=(value:number)=>220-220*(value-low+pad)/(high-low+2*pad);
    const marks=points.map(p=>({...p,x:x(p.ordinal),y:y(p.value)}));
    return {first,last,x,marks,ticks:yTicks(low-pad,high+pad,0,220),
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
  <h3 id="period-trend-title">시간에 따른 변화</h3>
  {#if loadState==="loading"}<StatusNotice message="같은 진동 특징의 측정별 추이를 불러오고 있습니다."/>
  {:else if loadState==="failed"}
    <StatusNotice kind="failure" title="시간 추이를 불러오지 못했습니다" message={error}
      actionLabel="시간 추이 다시 불러오기" onAction={()=>void load()}/>
  {:else if !chart||!trend}<StatusNotice message="선택한 구간에 그릴 측정값이 없습니다. 아래 집계도 함께 확인하세요."/>
  {:else}
    {@const read=trend}
    {@const plot=chart}
    <p class="note">세로축 · {read.label} · {read.unit??"단위 미확인"}</p>
    <figure>
      <ValueAxis ticks={plot.ticks} height={220} unit={null}>
        <svg viewBox="0 0 800 220" preserveAspectRatio="none" role="img"
          aria-label={"시간에 따른 "+read.label+" 변화. 기간 A와 B를 음영으로 표시합니다."}>
          {#each ["a","b"] as key(key)}
            {@const span=spans[key as "a"|"b"]}
            <rect x={plot.x(span.from)} y="0" width={Math.max(2,plot.x(span.to)-plot.x(span.from))} height="220" class={"band "+key}>
              <title>기간 {key.toUpperCase()} · {measurementLabel(span.from,read.periodSeconds)} ~ {measurementLabel(span.to,read.periodSeconds)}</title>
            </rect>
          {/each}
          {#each plot.ticks as tick(tick.value)}<line x1="0" x2="800" y1={tick.y} y2={tick.y} class="grid"/>{/each}
          <path d={plot.path} class="line"/>
          {#each plot.marks as point(point.ordinal)}<circle cx={point.x} cy={point.y} r="3">
            <title>{measurementLabel(point.ordinal,read.periodSeconds)} · {measure(point.value,read.unit)}</title>
          </circle>{/each}
        </svg>
        {#snippet footer()}<XAxis lo={plot.first} hi={plot.last} scale={measurementScale(read.periodSeconds)}
          note={read.periodSeconds?"가로축 · 기록 시작 후 경과 시간 · 기록된 측정 간격 "+elapsedText(read.periodSeconds):"가로축 · 측정 회차 · 측정 간격 기록 없음"}/>{/snippet}
      </ValueAxis>
      <figcaption><span><i class="key a"></i>기간 A</span><span><i class="key b"></i>기간 B</span> · 점은 저장된 측정값입니다.</figcaption>
    </figure>
    {#if read.sampled}<p class="note">기록이 많아 고르게 선택한 일부 측정만 표시합니다. 표시한 점의 수와 아래 전체 구간 집계는 다를 수 있습니다.</p>{/if}
  {/if}
</section>

<style>
  section{min-width:0}figure{margin:var(--space-3) 0}svg{display:block;width:100%;height:220px}
  svg line,svg path,svg circle{vector-effect:non-scaling-stroke}
  .band.a{fill:var(--color-ink-muted);fill-opacity:0.12}.band.b{fill:var(--color-action);fill-opacity:0.12}
  .grid{stroke:var(--color-border);stroke-width:1}.line{stroke:var(--color-action);stroke-width:2;fill:none}circle{fill:var(--color-action)}
  .note,figcaption{color:var(--color-ink-muted);font-size:var(--font-small);overflow-wrap:anywhere}
  figcaption{display:flex;flex-wrap:wrap;gap:var(--space-2)}.key{display:inline-block;width:14px;height:10px;margin-right:var(--space-1)}
  .key.a{background:var(--color-ink-muted);opacity:0.5}.key.b{background:var(--color-action);opacity:0.5}
</style>
