<script lang="ts">
  import {onMount} from "svelte";
  import {elapsedText} from "../time-axis";
  import {num} from "../format";
  import type {ModelBinding} from "../model-evidence";
  import {exceedanceText, exceedanceStory, readScoreTrend, type ScoreTrend, type TrendPoint} from "../model-trend";
  import StatusNotice from "./StatusNotice.svelte";
  /** Compare stored verdicts at the same measurement; score scales stay within each model. */
  type Props={bindings:ModelBinding[];names:Map<string,string>;selected:string;place:(position:number)=>string;
    selectedPosition?:number|null;onChoose:(bindingId:string)=>void;onPick:(position:number)=>void;period?:number|null};
  let {bindings,names,selected,place,onChoose,onPick,period=null,selectedPosition=null}:Props=$props();
  let trends:Map<string,ScoreTrend|null>=$state(new Map());
  let loadState:"loading"|"ready"|"failed"=$state("loading");
  let picked:number|null=$state(null);
  $effect(()=>{if(selectedPosition!==null)picked=selectedPosition;});
  const positions=$derived.by(()=>{
    const loaded=[...trends.values()].flatMap(read=>read?.points.map(point=>point.pointer.position)??[]);
    const processed=bindings.flatMap(binding=>binding.lastProcessed===null?[]:[binding.lastProcessed]);
    const selected=selectedPosition===null?[]:[selectedPosition];
    return [...new Set([...loaded,...processed,...selected])].sort((a,b)=>a-b);
  });
  const position=$derived(picked!==null&&positions.includes(picked)?picked:positions.at(-1)??null);
  const selectedModel=$derived(bindings.find(binding=>binding.bindingId===selected));
  const point=(binding:ModelBinding|undefined,at:number|null)=>trends.get(binding?.bindingId??"")?.points.find(point=>point.pointer.position===at)??null;
  function verdict(point:TrendPoint|null):string {
    return !point?"분석 기록 없음":point.pointer.state==="skipped"?"분석 제외":point.exceeds===null?"판단 정보 없음":point.exceeds?"기준 초과":"기준 이하";
  }
  const x=(at:number)=>800*(at-(positions[0]??0))/Math.max(1,(positions.at(-1)??1)-(positions[0]??0));
  onMount(()=>{
    const request=new AbortController();
    void Promise.all(bindings.map(binding=>readScoreTrend(binding,request.signal).catch(()=>null))).then(values=>{
      if(request.signal.aborted)return;
      trends=new Map(bindings.map((binding,i)=>[binding.bindingId,values[i]]));
      loadState=values.some(read=>read?.points.length)?"ready":"failed";
    });
    return()=>request.abort();
  });
</script>
<section class="comparison" aria-labelledby="model-comparison-title">
  <h3 id="model-comparison-title">모델별 판단 상태 비교</h3>
  <p class="context">동일한 측정에서 각 모델이 자신의 기준을 넘었는지 비교합니다. 점수와 기준값은 모델별 척도로 표시합니다.</p>
  {#if loadState==="loading"}<StatusNotice message="모델별 분석 기록을 불러오고 있습니다." />
  {:else if loadState==="failed"}<StatusNotice kind="uncertain" message="모델별 비교를 불러오지 못했습니다. 아래에서 모델을 개별적으로 확인하세요." />
  {:else}
    {#if [...trends.values()].some(read=>read?.truncated)}<p class="context" role="status">점수 기록을 일부만 조회했습니다. 마지막 처리 측정은 모델 상태에서 확인한 값이며, ‘조회 범위 밖’인 결과는 해당 모델의 개별 화면에서 확인하세요.</p>{/if}
    {#if positions.length}
      <label class="picker">비교할 측정 · {position===null?"없음":place(position)}
        <input type="range" min="0" max={positions.length-1} step="1" value={position===null?0:positions.indexOf(position)}
          aria-valuetext={position===null?"없음":place(position)} oninput={event=>picked=positions[Number(event.currentTarget.value)]} />
      </label>
      <button type="button" class="ui-button" disabled={position===null||(!point(selectedModel,position)&&selectedModel?.lastProcessed!==position&&selectedModel?.lastAnalyzed!==position)} onclick={()=>{if(position!==null)onPick(position);}}>이 측정의 상세 보기 →</button>
    {/if}
    <div class="scroll"><table>
      <caption aria-live="polite">{position===null?"비교할 측정 없음":place(position)+"의 모델별 결과"}</caption>
      <thead><tr><th scope="col">모델</th><th scope="col">선택 측정의 판단</th><th scope="col">점수 / 자체 기준</th><th scope="col">마지막 처리 측정</th></tr></thead>
      <tbody>{#each bindings as binding(binding.bindingId)}
        {@const current=point(binding,position)}
        {@const read=trends.get(binding.bindingId)}
        {@const latestRead=read?.points.at(-1)}
        <tr><th scope="row"><button class="model" type="button" aria-pressed={selected===binding.bindingId} onclick={()=>onChoose(binding.bindingId)}>{names.get(binding.bindingId)}</button></th>
          <td class:over={current?.exceeds===true}>{!read?"조회 실패":!current&&read.truncated?"조회 범위 밖":verdict(current)}</td>
          <td>{current?num(current.score)+" / "+num(current.threshold):"—"}</td>
          <td>{binding.lastProcessed===null?"처리 측정 미확인":place(binding.lastProcessed)}{#if read?.truncated&&latestRead}<small>조회한 기록은 {place(latestRead.pointer.position)}까지</small>{/if}</td></tr>
      {/each}</tbody>
    </table></div>
    <details><summary>조회한 기록의 모델별 판단 추이</summary>
      <p class="context">주황 · 기준 초과　파랑 · 기준 이하　회색 · 분석 제외 또는 판단 정보 없음. 빈 구간은 분석 기록이 없습니다.</p>
      {#if period}<p class="context">가로축 · 기록 시작 후 경과 시간 · 측정 간격 {elapsedText(period)}</p>{/if}
      {#each bindings as binding(binding.bindingId)}
        {@const read=trends.get(binding.bindingId)}
        {@const story=read&&!read.truncated?exceedanceText(exceedanceStory(read),place):null}
        <p><strong>{names.get(binding.bindingId)}</strong> · {read?.truncated?"일부 기록 · "+(read.points.length?place(read.points[0].pointer.position)+" ~ "+place(read.points.at(-1)!.pointer.position):"조회한 값 없음"):story?.headline??"기준 초과 흐름을 확인할 수 없습니다"}</p>
        <svg viewBox="0 0 800 32" preserveAspectRatio="none" role="img" aria-label={(names.get(binding.bindingId)??"모델")+"의 측정별 기준 초과 여부"}>
          {#each read?.points??[] as point(point.pointer.position)}
            <line x1={x(point.pointer.position)} x2={x(point.pointer.position)} y1="5" y2="27"
              class:over={point.exceeds===true} class:under={point.exceeds===false}>
              <title>{place(point.pointer.position)} · {verdict(point)}</title></line>
          {/each}
          {#if position!==null}<line x1={x(position)} x2={x(position)} y1="0" y2="32" class="picked" />{/if}
        </svg>
      {/each}
      {#if positions.length}<p class="context">{place(positions[0])} ~ {place(positions.at(-1)!)}</p>{/if}
    </details>
  {/if}
</section>
<style>
  .comparison{display:grid;gap:var(--space-3);min-width:0;margin-block:var(--space-4)}h3,p{margin:0}
  .context{font-size:var(--font-small);color:var(--color-ink-muted);overflow-wrap:anywhere}
  .picker{display:grid;gap:var(--space-2)}.picker input{width:100%;min-height:32px}.comparison>.ui-button{justify-self:start}
  td small{display:block;font-size:var(--font-small);color:var(--color-ink-muted);font-weight:400}
  .scroll{max-width:100%;overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:540px}caption{text-align:left;font-weight:650}
  td,th{text-align:left;padding:var(--space-3);border-bottom:1px solid var(--color-border)}.over{color:var(--color-caution-ink);font-weight:650}
  .model{font:inherit;background:var(--color-surface);color:var(--color-action);border:1px solid var(--color-border);border-radius:var(--radius-control);padding:var(--space-2);cursor:pointer}
  .model[aria-pressed="true"]{background:var(--color-surface-selected);font-weight:700}
  svg{display:block;width:100%;height:32px;margin-block:var(--space-2)}svg line{stroke:var(--color-border);stroke-width:3;vector-effect:non-scaling-stroke}
  svg .over{stroke:var(--color-caution-ink)}svg .under{stroke:var(--color-action)}svg .picked{stroke:var(--color-ink);stroke-width:2}
</style>
