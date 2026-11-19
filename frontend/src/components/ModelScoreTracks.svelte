<script lang="ts">
  import type {TimelineModel} from "../asset-timeline";
  import {drawTrend,type TrendPoint} from "../model-trend";
  import {measure} from "../chart-axis";
  import PlotCursor from "./PlotCursor.svelte";
  let {models,lo,hi,selected=null,onSelect,range=null}:{models:TimelineModel[];lo:number;hi:number;
    selected?:number|null;onSelect?:(at:number)=>void;range?:{from:number;to:number}|null}=$props();
  const x=(at:number)=>(at-lo)/Math.max(hi-lo,1e-9)*600;
  function plot(model:TimelineModel){
    const divisor=model.divisor??1;
    const all=model.trend.points.filter(p=>p.pointer.position/divisor>=lo&&p.pointer.position/divisor<=hi);
    const drawn=drawTrend(all,180);
    const segments=new Map<number,number>();let segment=0,prior:TrendPoint|null=null;
    for(const point of all){
      if(point.score===null||!prior||prior.score===null||(divisor===1&&point.pointer.position!==prior.pointer.position+1))segment++;
      segments.set(point.pointer.position,segment);prior=point;
    }
    const values=all.flatMap(p=>[p.score,p.threshold].filter((v):v is number=>v!==null));
    const low=Math.min(0,...values),high=Math.max(low+1e-9,...values);
    const y=(v:number)=>53-(v-low)/(high-low)*46;
    let path="",threshold="",over="",previous:TrendPoint|null=null;
    for(const point of drawn){
      const at=x(point.pointer.position/divisor);
      if(point.score===null){previous=null;continue;}
      const joined=previous!==null&&segments.get(point.pointer.position)===segments.get(previous.pointer.position);
      path+=(joined?"L":"M")+at+" "+y(point.score)+" ";
      if(point.threshold!==null)threshold+=(joined?"L":"M")+at+" "+y(point.threshold)+" ";
      if(joined&&(point.exceeds||previous!.exceeds))over+="M"+x(previous!.pointer.position/divisor)+" "+y(previous!.score!)+"L"+at+" "+y(point.score)+" ";
      previous=point;
    }
    const chosen=selected===null?null:all.find(p=>p.pointer.position/divisor===selected)??null;
    return {path,threshold,over,chosen,y,positions:all.map(p=>p.pointer.position/divisor)};
  }
</script>
{#if models.length}
<div class="models" aria-label="실측과 같은 시간축의 모델 점수">
  {#each models as model(model.key)}
    {@const curve=plot(model)}
    <section class="model" aria-label={model.count}>
      <header><strong>{model.name}</strong>
        {#if selected!==null}<span>{curve.chosen?.score!=null?"점수 "+measure(curve.chosen.score,null)+" · 기준 "+(curve.chosen.threshold===null?"없음":measure(curve.chosen.threshold,null)):"이 측정의 점수 없음"}</span>{/if}
      </header>
      <PlotCursor positions={curve.positions} value={selected} {lo} {hi} {onSelect} label={(model.name)+" 측정 선택"}>
        <svg class="curve" viewBox="0 0 600 60" preserveAspectRatio="none" role="img" aria-label={model.count+" · 모델 고유 점수와 기준"}>
          {#if range}<rect x={x(Math.max(lo,range.from))} width={Math.max(0,x(Math.min(hi,range.to))-x(Math.max(lo,range.from)))} height="60" class="interval"/>{/if}
          <path d={curve.threshold} class="threshold"/>
          <path d={curve.path} class="score"/><path d={curve.over} class="over"/>
          {#if selected!==null && selected>=lo && selected<=hi}<line x1={x(selected)} x2={x(selected)} y1="0" y2="60" class="selected"/>{/if}
          {#if curve.chosen?.score!=null}<circle cx={x(selected!)} cy={curve.y(curve.chosen.score)} r="3"/>{/if}
        </svg>
      </PlotCursor>
      <p class="count">{model.count}{model.unfamiliar?" · "+model.unfamiliar:""}</p>
    </section>
  {/each}
  <p class="key"><span><i class="score"></i>모델 점수</span><span><i class="over"></i>기준 초과</span><span><i class="threshold"></i>각 모델의 기준</span></p>
</div>
{/if}
<style>
  .models{display:grid;gap:var(--space-2);margin-top:var(--space-2)}
  .model{min-width:0;border-top:1px solid var(--color-border);padding-top:var(--space-2)}
  header{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:4px;font-size:var(--font-small)}
  header strong{font-weight:650}header span,.count{font-size:var(--font-label);color:var(--color-ink-muted);font-variant-numeric:tabular-nums}
  .count{margin:2px 0 0}.curve{height:64px}svg{display:block;width:100%;overflow:visible}
  path{fill:none;stroke-width:1.8;vector-effect:non-scaling-stroke}.score{stroke:var(--color-action)}.over{stroke:var(--color-failure-ink)}
  .threshold{stroke:var(--color-caution-ink);stroke-dasharray:4 4;stroke-width:1.2}.selected{stroke:var(--color-ink);stroke-width:1;stroke-dasharray:3 3;vector-effect:non-scaling-stroke}
  .interval{fill:var(--color-caution-ink);opacity:.1}circle{fill:var(--color-ink);stroke:var(--color-surface);stroke-width:1}
  .key{margin:0;display:flex;flex-wrap:wrap;gap:var(--space-3);font-size:var(--font-label);color:var(--color-ink-muted)}
  .key i{display:inline-block;width:16px;border-top:2px solid;vertical-align:middle;margin-right:4px}.key .score{border-color:var(--color-action)}.key .over{border-color:var(--color-failure-ink)}.key .threshold{border-color:var(--color-caution-ink);border-top-style:dashed}
</style>
