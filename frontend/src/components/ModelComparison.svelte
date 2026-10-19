<script lang="ts">
  import {assetTabUrl} from "../routes";
  import {num} from "../format";
  import type {ModelBinding,ModelRun} from "../model-evidence";
  import {readComparison,readRange,shapeText,type Comparison,type ModelRange,type Focus} from "../model-comparison";
  import ModelInput from "./ModelInput.svelte";
  import StatusNotice from "./StatusNotice.svelte";
  let {binding,run,compare,place,onFocus}: {binding:ModelBinding;run:ModelRun;compare:number|null;
    place:(at:number)=>string;onFocus:(focus:Focus)=>void}=$props();
  let comparison:Comparison|null=$state(null),range:ModelRange|null=$state(null);
  let exploreFeature=$state("");
  let failed=$state(false),rangeFailed=$state(false),loading=$state(false);
  let preview:{position:number;feature:string|null}|null=$state(null);
  const contributions=$derived.by(() => {
    const raw=run.output.feature_contributions;
    if(!raw||typeof raw!=="object"||Array.isArray(raw))return [];
    return Object.entries(raw).filter((entry): entry is [string,number] => typeof entry[1]==="number"&&Number.isFinite(entry[1])).sort((a,b)=>b[1]-a[1]);
  });
  const rows=$derived.by(() => { const flow: ModelRange | null = range; return flow ? [{name:"primary",label:"모델 점수",shape:flow.primary},...flow.features] : []; });
  // Rows with a change point to open come first; the rest are named once instead of repeated.
  const marked=$derived(rows.filter(row=>row.shape.shift||row.shape.largest));
  const quiet=$derived(rows.filter(row=>!row.shape.shift&&!row.shape.largest));
  // The measurements that changed most lead the table.
  const ordered=$derived.by(()=>{
    const current: Comparison | null = comparison;
    const size=(value:number|null)=>value===null?-1:Math.abs(value);
    return current?[...current.features].sort((a,b)=>size(b.relativePercent)-size(a.relativePercent)):[];
  });
  function exploration(feature:string):string|null {
    if(compare===null||binding.stepKind!=="acquisition-snapshot")return null;
    const split=Math.floor((compare+run.position)/2);
    const url=new URL(assetTabUrl(binding.assetId,"change","compare","vibration"),location.origin);
    for(const [key,value] of Object.entries({acquisition_feature:feature,acquisition_binding:binding.bindingId,
      feature_a_from:String(compare),feature_a_to:String(split),feature_b_from:String(split+1),feature_b_to:String(run.position)}))url.searchParams.set(key,value);
    return url.pathname+url.search;
  }
  function open(position:number,feature:string|null,question=false){
    preview={position,feature};
    if(question)onFocus({position,series:feature});
  }
  $effect(()=>{
    const prior=compare,model=binding,current=run;
    comparison=null;range=null;preview=null;failed=false;rangeFailed=false;
    const request=new AbortController();loading=true;
    void (async()=>{
      try{
        const values=await readComparison(model,current,prior,request.signal);
        if(request.signal.aborted)return;
        comparison=values;exploreFeature=values.features[0]?.feature??"";loading=false;
        if(prior===null)return;
        try{const flow=await readRange(model,current,prior,values,request.signal);if(!request.signal.aborted)range=flow;}
        catch{if(!request.signal.aborted)rangeFailed=true;}
      }catch{if(!request.signal.aborted){failed=true;loading=false;}}
    })();
    return()=>request.abort();
  });
</script>
<section class="comparison" aria-label="측정값 비교">
  <h4>측정값 비교</h4>
  <p class="context">저장된 두 측정과 구간 흐름은 AI 없이도 확인할 수 있습니다.</p>
  {#if loading}<StatusNotice message="두 측정의 저장값을 비교하고 있습니다."/>
  {:else if failed}<StatusNotice kind="uncertain" message="측정 비교를 읽지 못했습니다. 이전 비교로 대신하지 않습니다."/>
  {:else if comparison}
    {#if compare===null}<p class="context">비교할 이전 분석이 없어 한 시점의 측정값을 보여 줍니다.</p>{:else}
    <p class="context">모델 점수 {num(comparison.previousScore,"기록 없음")} → {num(typeof run.output.score==="number"?run.output.score:null,"기록 없음")} · {place(compare)} → {place(run.position)}</p>{/if}
    <div class="scroll"><table>
      <caption>측정 특징 비교 · 많이 변한 순서 · 이름을 누르면 원본을 봅니다</caption>
      <thead><tr><th>측정값</th><th>비교 측정</th><th>고른 측정</th><th>변화율</th></tr></thead>
      <tbody>{#each ordered as feature(feature.feature)}
        <tr><th scope="row"><button class="text-button" aria-label={feature.label + " 원본 확인"} onclick={()=>open(run.position,feature.feature)}>{feature.label}</button></th>
          <td>{num(feature.previous,"—")}</td><td>{num(feature.current)}</td><td>{feature.relativePercent===null?"—":num(feature.relativePercent)+"%"}</td></tr>
      {/each}</tbody>
    </table></div>
    {#if exploration(exploreFeature)}<div class="explore"><label>두 기간으로 탐색할 특징<select bind:value={exploreFeature}>{#each comparison.features as feature(feature.feature)}<option value={feature.feature}>{feature.label}</option>{/each}</select></label><a href={exploration(exploreFeature)!}>이 구간을 A/B로 탐색 →</a></div>{/if}
    {#if compare!==null}<button type="button" class="ui-button" onclick={()=>open(compare!,null)}>비교 측정 원본 확인</button>{/if}
    {#if rangeFailed}<StatusNotice kind="uncertain" message="구간 흐름을 읽지 못했습니다. 두 측정의 값은 위에서 볼 수 있습니다."/>
    {:else if range && compare !== null && rows.some(row=>row.shape.trend!=="insufficient")}
      <p class="context">구간 흐름 · {place(compare)} → {place(run.position)} · 분석 {range.steps}개{range.sampled?" · 흐름은 "+range.points+"개 표본, 최대 변화는 전체 기록":""}</p>
      <div class="flow" role="table" aria-label="구간 흐름">
        {#each marked as row(row.name)}
          <div class="flow-row" role="row"><div role="rowheader"><strong>{row.label}</strong></div>
            <span role="cell">{shapeText(row.shape)}</span>
            <div role="cell">
              {#if row.shape.shift}<button class="ui-button" onclick={()=>open(row.shape.shift!.at,row.name,true)}>수준 변화 {place(row.shape.shift.at)} · 원본 확인</button>{/if}
              {#if row.shape.largest}<button class="ui-button" onclick={()=>open(row.shape.largest!.to,row.name,true)}>가장 큰 변화 {place(row.shape.largest.from)} → {place(row.shape.largest.to)} · 원본 확인</button>{/if}
            </div>
          </div>
        {/each}
      </div>
      {#if quiet.length}<p class="context">변화 지점이 없거나 계산할 기록이 부족한 값 {quiet.length}개 · {quiet.map(row=>row.label).join(", ")}</p>{/if}
      <p class="context">변화 지점을 누르면 그 지점의 원본을 열고 다음 질문의 기준으로 지정합니다.</p>
    {/if}
  {/if}
  {#if contributions.length}<details><summary>모델이 반영한 특징 ({contributions.length}개)</summary><p class="context">모델 출력의 특징별 기여도입니다. 설비 고장의 원인이나 확률이 아닙니다.</p><dl>{#each contributions as [name,value] (name)}<div><dt>{comparison?.features.find(item=>item.feature===name)?.label??name}</dt><dd>{num(value)}</dd></div>{/each}</dl></details>{/if}
  {#if preview}
    {#key preview.position+":"+preview.feature}<ModelInput {binding} position={preview.position} feature={preview.feature} {place}/>{/key}
  {/if}
</section>
<style>
  .comparison{display:grid;gap:var(--space-3);min-width:0}
  h4,p{margin:0}h4{font-size:var(--font-section)}
  .context{color:var(--color-ink-muted);font-size:var(--font-small);overflow-wrap:anywhere}
  .scroll{max-width:100%;overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:520px}
  caption{text-align:left;font-weight:650}th,td{padding:var(--space-2);text-align:left;border-bottom:1px solid var(--color-border)}
  .explore{display:flex;flex-wrap:wrap;gap:var(--space-3);align-items:end}.explore label{display:grid;gap:var(--space-2)}.explore select{max-width:100%;padding:var(--space-2)}
  .text-button{border:0;background:none;color:var(--color-action);font:inherit;text-align:left;cursor:pointer;padding:var(--space-2)}
  .flow{display:grid}.flow-row{display:grid;grid-template-columns:minmax(120px,1fr) minmax(100px,1fr) 2fr;gap:var(--space-2);padding-block:var(--space-3);border-bottom:1px solid var(--color-border)}
  .flow-row>div{display:flex;gap:var(--space-2);flex-wrap:wrap}.comparison>.ui-button{justify-self:start}
  @media(max-width:600px){.flow-row{grid-template-columns:1fr}.flow-row>div{flex-direction:column;align-items:start}}
</style>
