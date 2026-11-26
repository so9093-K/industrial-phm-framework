<script lang="ts">
  import {readSignalNames, signalName, type SignalNames} from "../history";
  import {scoreRaisers} from "../score-raisers";
  import {historyFeatureLabel} from "../history-model";
  import {assetTabUrl} from "../routes";
  import {num} from "../format";
  import type {ModelBinding,ModelRun} from "../model-evidence";
  import {readComparison,readRange,shapeText,type Comparison,type ModelRange,type Focus} from "../model-comparison";
  import ModelInput from "./ModelInput.svelte";
  import StatusNotice from "./StatusNotice.svelte";
  import AnalysisMessage from "./AnalysisMessage.svelte";
  import TaskDialog from "./TaskDialog.svelte";
  import {AGAINST_TEXT,LEARNED_TEXT,against,comparisonMessage} from "../analysis-messages";
  let {binding,run,compare,place,onFocus}: {binding:ModelBinding;run:ModelRun;compare:number|null;
    place:(at:number)=>string;onFocus:(focus:Focus)=>void}=$props();
  // A stored-history model's features are named by the asset's signal names (ADR-0032).
  let signalNames: SignalNames | null = $state(null);
  $effect(() => {
    if (binding.stepKind !== "history-window") return;
    void readSignalNames(binding.assetId).then((value) => { signalNames = value; }).catch(() => {});
  });
  const shown = (label: string) => historyFeatureLabel(label, signalNames);
  let comparison:Comparison|null=$state(null),range:ModelRange|null=$state(null);
  let exploreFeature=$state("");
  let failed=$state(false),rangeFailed=$state(false),loading=$state(false);
  let preview:{position:number;feature:string|null}|null=$state(null);
  // The model's own split of this score per signal, when it gives one; the summary leads with it.
  const everyRaiser=$derived(scoreRaisers(run.output.feature_contributions,Infinity));
  const raisers=$derived(everyRaiser.slice(0,3));
  // The bars show three signals; the rest of the rise is named once, so the bars do not read as all of it.
  const restShare=$derived(100-raisers.reduce((sum,item)=>sum+item.share,0));
  const raisedRows=$derived.by(()=>{
    const current: Comparison | null = comparison;
    return raisers.map(raiser=>({raiser,feature:current?.features.find(item=>item.feature===raiser.feature)??null}));
  });
  const signalShown=(signal:string)=>signalName(signalNames,signal);
  /** The statistic named after its signal: "평균" under "R상역률". */
  function statistic(label:string,signal:string):string{const full=shown(label),head=signalShown(signal);return full.startsWith(head+" ")?full.slice(head.length+1):full;}
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
  // Whether the score moved with values leaving where this asset usually sits, or on ordinary values.
  const told=$derived.by(()=>{
    const current: Comparison | null = comparison;
    if(!current||compare===null)return null;
    return comparisonMessage({previous:current.previousScore,current:typeof run.output.score==="number"?run.output.score:null,
      exceeds:typeof run.output.exceeds_threshold==="boolean"?run.output.exceeds_threshold:null},
      current.features.map(feature=>({...feature,label:shown(feature.label)})),current.usualUntil,place);
  });
  // The largest changes come first; the rest stay one press away instead of lengthening the page.
  const FIRST_ROWS=4;
  let showAll=$state(false);
  let view:"summary"|"values"|"flow"=$state("summary"), previewOpen=$state(false);
  const primary = $derived(binding.stepKind === "acquisition-snapshot" && ordered.some(row=>row.feature.endsWith(".rms"))
    ? ordered.filter(row=>row.feature.endsWith(".rms")).slice(0,2) : ordered.slice(0,2));
  const visible=$derived(showAll?ordered:ordered.slice(0,FIRST_ROWS));
  function exploration(feature:string):string|null {
    if(compare===null||binding.stepKind!=="acquisition-snapshot")return null;
    const split=Math.floor((compare+run.position)/2);
    const url=new URL(assetTabUrl(binding.assetId,"change","compare","vibration"),location.origin);
    for(const [key,value] of Object.entries({acquisition_feature:feature,acquisition_source:binding.sourceId,
      feature_a_from:String(compare),feature_a_to:String(split),feature_b_from:String(split+1),feature_b_to:String(run.position)}))url.searchParams.set(key,value);
    return url.pathname+url.search;
  }
  // Where this feature is heading: the condition outlook of the same feature.
  function outlook(feature:string):string|null {
    if(binding.stepKind!=="acquisition-snapshot")return null;
    const url=new URL(assetTabUrl(binding.assetId,"outlook",null,"vibration"),location.origin);
    url.searchParams.set("acq_forecast_feature",feature);
    return url.pathname+url.search;
  }
  function open(position:number,feature:string|null,question=false){
    preview={position,feature};
    previewOpen=true;
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
        // Start from the measurement that changed most, the one worth following further.
        const size=(value:number|null)=>value===null?-1:Math.abs(value);
        comparison=values;loading=false;
        exploreFeature=[...values.features].sort((x,y)=>size(y.relativePercent)-size(x.relativePercent))[0]?.feature??"";
        if(prior===null)return;
        try{const flow=await readRange(model,current,prior,values,request.signal);if(!request.signal.aborted)range=flow;}
        catch{if(!request.signal.aborted)rangeFailed=true;}
      }catch{if(!request.signal.aborted){failed=true;loading=false;}}
    })();
    return()=>request.abort();
  });
</script>
<section class="comparison" aria-label="측정값 비교">
  {#if loading}<StatusNotice message="두 측정의 저장값을 비교하고 있습니다."/>
  {:else if failed}<StatusNotice kind="uncertain" message="측정 비교를 읽지 못했습니다. 이전 비교로 대신하지 않습니다."/>
  {:else if comparison}
    {#if compare===null}<p class="context">비교할 이전 분석이 없어 한 시점의 측정값을 보여 줍니다.</p>{:else if !told}
    <p class="context">모델 점수 {num(comparison.previousScore,"기록 없음")} → {num(typeof run.output.score==="number"?run.output.score:null,"기록 없음")} · {place(compare)} → {place(run.position)}</p>{/if}
    <div class="views" role="group" aria-label="측정 변화 살펴보기">
      <button type="button" class="ui-button" aria-pressed={view==="summary"} onclick={()=>view="summary"}>{raisers.length?"점수를 올린 신호":"주요 측정값"}</button>
      <button type="button" class="ui-button" aria-pressed={view==="values"} onclick={()=>view="values"}>전체 특징 비교</button>
      <button type="button" class="ui-button" aria-pressed={view==="flow"} onclick={()=>view="flow"}>두 측정 사이의 흐름</button>
    </div>
    <div class="comparison-columns">{#if view==="summary" && raisers.length}
      <dl class="primary-features" aria-label="이 점수를 올린 신호">{#each raisedRows as {raiser,feature}(raiser.signal)}<div>
        <dt><span>{signalShown(raiser.signal)}</span><span class="share">{raiser.share}%</span></dt>
        <dd class="share-bar" aria-hidden="true"><span style:width={raiser.share+"%"}></span></dd>
        {#if feature}
          <dd><button type="button" class="text-button stat" onclick={()=>open(run.position,feature.feature)}>{statistic(feature.label,raiser.signal)}</button>
            {num(feature.previous,"—")} <span>→</span> {num(feature.current)}{feature.unit?" "+feature.unit:""}</dd>
          {#if feature.usual || feature.learned}<dd class="range-note">{#if feature.usual}{AGAINST_TEXT[against(feature.current,feature.usual)]} · 비교 범위 {num(feature.usual.low)}–{num(feature.usual.high)}{feature.unit?" "+feature.unit:""}{/if}{#if feature.learned&&against(feature.current,feature.learned)!=="inside"}{feature.usual?" · ":""}{LEARNED_TEXT[against(feature.current,feature.learned)]}{/if}</dd>{/if}
        {/if}
      </div>{/each}</dl>
      {#if everyRaiser.length>raisers.length && restShare>0}<p class="context">다른 신호 {everyRaiser.length-raisers.length}개 합계 {restShare}%</p>{/if}
    {:else if view==="summary"}
      <dl class="primary-features">{#each primary as feature(feature.feature)}<div>
        <dt><button type="button" class="text-button" onclick={()=>open(run.position,feature.feature)}>{shown(feature.label)}</button></dt>
        <dd>{num(feature.previous,"—")} <span>→</span> {num(feature.current)}{feature.unit?" "+feature.unit:""}</dd>
        {#if feature.usual}<dd class="range-note">{AGAINST_TEXT[against(feature.current,feature.usual)]} · 비교 범위 {num(feature.usual.low)}–{num(feature.usual.high)}{feature.unit?" "+feature.unit:""}</dd>{/if}
      </div>{/each}</dl>
      {#if primary[0] && exploration(primary[0].feature)}<a class="ui-button" href={exploration(primary[0].feature)!}>이 특징의 구간 비교하기 →</a>{/if}
    {:else if view==="values"}<div class="values-column"><div class="scroll"><table>
      <caption>측정 특징 비교 · 많이 변한 순서 · 이름을 누르면 원본을 봅니다</caption>
      <thead><tr><th>측정값</th><th>비교 측정</th><th>고른 측정</th><th>변화율</th><th>평소·학습값 범위와 비교</th></tr></thead>
      <tbody>{#each visible as feature(feature.feature)}
        <tr><th scope="row"><button class="text-button" aria-label={shown(feature.label) + " 원본 확인"} onclick={()=>open(run.position,feature.feature)}>{shown(feature.label)}</button></th>
          <td>{num(feature.previous,"—")}{feature.previous!==null&&feature.unit?" "+feature.unit:""}</td><td>{num(feature.current)}{feature.unit?" "+feature.unit:""}</td><td>{feature.relativePercent===null?"—":(feature.relativePercent>0?"+":"")+feature.relativePercent.toLocaleString("ko-KR",{maximumFractionDigits:1})+"%"}</td>
          <td>{#if feature.usual}<span title={"평소 범위 "+num(feature.usual.low)+"~"+num(feature.usual.high)+(feature.unit?" "+feature.unit:"")}>{AGAINST_TEXT[against(feature.current,feature.usual)]}</span>{:else}—{/if}
            {#if feature.learned&&against(feature.current,feature.learned)!=="inside"}<span class="learned" title={"학습값 5~95% 범위 "+num(feature.learned.low)+"~"+num(feature.learned.high)+(feature.unit?" "+feature.unit:"")}> · {LEARNED_TEXT[against(feature.current,feature.learned)]}</span>{/if}</td></tr>
      {/each}</tbody>
    </table></div>
    {#if ordered.length>FIRST_ROWS}<button type="button" class="text-button" aria-expanded={showAll} onclick={()=>showAll=!showAll}>{showAll?"많이 변한 "+FIRST_ROWS+"개만 보기":"나머지 "+(ordered.length-FIRST_ROWS)+"개 측정값도 보기"}</button>{/if}
    {#if exploration(exploreFeature)}<div class="explore"><label>더 살펴볼 특징<select bind:value={exploreFeature}>{#each comparison.features as feature(feature.feature)}<option value={feature.feature}>{shown(feature.label)}</option>{/each}</select></label><a href={exploration(exploreFeature)!}>이 구간을 A/B로 탐색 →</a>{#if outlook(exploreFeature)}<a href={outlook(exploreFeature)!}>이 특징의 기준 도달 전망 →</a>{/if}</div>{/if}
    {#if compare!==null}<button type="button" class="ui-button" onclick={()=>open(compare!,null)}>비교 측정 원본 확인</button>{/if}
    </div>{:else}<div class="flow-column">
    {#if rangeFailed}<StatusNotice kind="uncertain" message="구간 흐름을 읽지 못했습니다. 두 측정의 값은 위에서 볼 수 있습니다."/>
    {:else if range && compare !== null && rows.some(row=>row.shape.trend!=="insufficient")}
      <p class="context">구간 흐름 · {place(compare)} → {place(run.position)} · 분석 {range.steps}개{range.sampled?" · 흐름은 "+range.points+"개 표본, 최대 변화는 전체 기록":""}</p>
      <div class="flow" role="table" aria-label="구간 흐름">
        {#each marked as row(row.name)}
          <div class="flow-row" role="row"><div role="rowheader"><strong>{shown(row.label)}</strong></div>
            <span role="cell">{shapeText(row.shape)}</span>
            <div role="cell">
              {#if row.shape.shift}<button class="ui-button" onclick={()=>open(row.shape.shift!.at,row.name,true)}>수준 변화 {place(row.shape.shift.at)} · 원본 확인</button>{/if}
              {#if row.shape.largest}<button class="ui-button" onclick={()=>open(row.shape.largest!.to,row.name,true)}>가장 큰 변화 {place(row.shape.largest.from)} → {place(row.shape.largest.to)} · 원본 확인</button>{/if}
            </div>
          </div>
        {/each}
      </div>
      {#if quiet.length}<p class="context">변화 지점이 없거나 계산할 기록이 부족한 값 {quiet.length}개 · {quiet.map(row=>shown(row.label)).join(", ")}</p>{/if}
      <p class="context">변화 지점을 누르면 그 지점의 원본을 열고 다음 질문의 기준으로 지정합니다.</p>
    {/if}
    </div>{/if}</div>
    {#if told}<details><summary>측정값 비교 해석</summary><AnalysisMessage message={told} showHeadline={false}/></details>{/if}
  {/if}
  <TaskDialog bind:open={previewOpen} title="선택한 측정의 원본">{#if preview}
    {#key preview.position+":"+preview.feature}<ModelInput {binding} position={preview.position} feature={preview.feature} {place}/>{/key}
  {/if}</TaskDialog>
</section>
<style>
  .comparison{display:grid;gap:var(--space-3);min-width:0}
  p{margin:0}
  .context{color:var(--color-ink-muted);font-size:var(--font-small);overflow-wrap:anywhere}
  .scroll{max-width:100%;overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:520px}
  caption{text-align:left;font-weight:650}th,td{padding:var(--space-2);text-align:left;border-bottom:1px solid var(--color-border)}
  .explore{display:flex;flex-wrap:wrap;gap:var(--space-3);align-items:end}.explore label{display:grid;gap:var(--space-2)}.explore select{max-width:100%;padding:var(--space-2)}
  .text-button{border:0;background:none;color:var(--color-action);font:inherit;text-align:left;cursor:pointer;padding:var(--space-2)}
  .flow{display:grid}.flow-row{display:grid;grid-template-columns:minmax(120px,1fr) minmax(100px,1fr) 2fr;gap:var(--space-2);padding-block:var(--space-3);border-bottom:1px solid var(--color-border)}
  .flow-row>div{display:flex;gap:var(--space-2);flex-wrap:wrap}.values-column>.ui-button{justify-self:start}
  .values-column,.flow-column{min-width:0;display:grid;align-content:start;gap:var(--space-3)}
  .comparison-columns{display:grid;gap:var(--space-5)}
  .views{display:flex;gap:var(--space-2);flex-wrap:wrap}.views button[aria-pressed="true"]{background:var(--color-surface-selected);border-color:var(--color-action);font-weight:650}
  .primary-features{display:grid;gap:var(--space-3);margin:0}.primary-features>div{border-bottom:1px solid var(--color-border);padding-bottom:var(--space-3)}
  .primary-features dt .text-button{padding:0;font-weight:650}.primary-features dd{font-size:1.5rem;font-weight:700;margin:var(--space-1) 0 0;font-variant-numeric:tabular-nums}.primary-features dd span{color:var(--color-ink-muted);font-weight:400}.primary-features dd.range-note{font-size:var(--font-small);font-weight:400;color:var(--color-ink-muted)}
  .primary-features dt{display:flex;justify-content:space-between;gap:var(--space-2);font-weight:650}.share{font-variant-numeric:tabular-nums}
  .primary-features dd.share-bar{height:6px;margin:var(--space-2) 0;border-radius:3px;background:var(--color-surface-selected);overflow:hidden}
  .share-bar span{display:block;height:100%;border-radius:3px;background:var(--color-action)}
  .primary-features dd .stat{padding:0 var(--space-1) 0 0;font-size:var(--font-small);font-weight:650;vertical-align:middle}
  .flow-row{grid-template-columns:minmax(100px,1fr) 1fr}.flow-row>div:last-child{grid-column:1 / -1}.flow-row .ui-button{padding:var(--space-2);font-size:var(--font-small)}
  @media(max-width:600px){.flow-row{grid-template-columns:1fr}.flow-row>div{flex-direction:column;align-items:start}}
</style>
