<script lang="ts">
  import type {Snippet} from "svelte";
  import {readAcquisitionTrend,type AcquisitionTrend} from "../acquisition-trend";
  import OverviewTrace from "./OverviewTrace.svelte";
  import {changeValue} from "../record-findings";
  import {plainLabel, latestNumber} from "../change-story";
  import ChangeNumbers from "./ChangeNumbers.svelte";
  import {vibrationShape, type VibrationChange, type VibrationFindings} from "../vibration-findings";
  import type {ModelRug} from "../model-context";

  /** 진동 측정 기록에서 고른 변화 하나: 결론, 숫자, 기록 전체를 측정 회차로 그린 그래프 하나. */
  let {assetId, record, change, rugs = [], selected=null, onSelect,actions}: {assetId?: string; record: VibrationFindings; change: VibrationChange; rugs?: ModelRug[];selected?:number|null;onSelect?:(at:number)=>void;actions?:Snippet} = $props();
  let full=$state<AcquisitionTrend|null>(null);
  $effect(()=>{
    const request=new AbortController();full=null;
    if(assetId&&record.first!==null&&record.last!==null&&change.trace.length<record.last-record.first+1){
      void readAcquisitionTrend(assetId,change.feature,request.signal).then(read=>{
        if(!request.signal.aborted&&!read.sampled&&read.sourceId===record.sourceId&&read.bindingId===record.bindingId)full=read;
      }).catch(()=>{});
    }
    return()=>request.abort();
  });
  const trace=$derived(full?full.points.map((p,i)=>({x:p.ordinal,value:p.value,join:i>0&&p.ordinal===full!.points[i-1].ordinal+1}))
    :change.trace.map(p=>({x:p.at,value:p.value,join:p.join})));
  // 변화가 기록 끝까지 이어졌으면 마지막 측정의 값이 '지금'이다.
  const shape = $derived(vibrationShape(change, record.last));
  const last = $derived(shape.atEnd ? change.trace.at(-1) : undefined);
  const latest = $derived(last ? latestNumber("마지막 · " + last.at + "회", last.value, change.reference, change.unit) : null);
</script>

<div class="change-lead"><div class="lead-copy"><h3 class="change-sentence">{plainLabel(change.label,change.feature)} · 초기보다 {change.direction==="up"?"높음":"낮음"}</h3>
  <p class="change-timing">{shape.span}{shape.jump?" · 마지막 측정에서 추가 급변":""}</p></div>
<ChangeNumbers facts={change} spanCaption={change.from + "–" + change.to + "회"} {latest}
  fallback={"가장 " + (change.direction === "up" ? "높을" : "낮을") + " 때 " + changeValue(change.value, change.unit)} />
</div>
{#if actions}{@render actions()}{/if}
<OverviewTrace main={{label:change.label,unit:change.unit,axis:"acquisition",periodSeconds:record.periodSeconds,latest:null,trace}} range={change} usual={change.usual} marks={shape.marks} {rugs} {selected} {onSelect} height={180}/>

<style>.change-timing{margin:0;font-size:var(--font-small);color:var(--color-ink-muted);line-height:1.5}</style>


