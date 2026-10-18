<script lang="ts">
  import {onMount} from "svelte";
  import StatusNotice from "./StatusNotice.svelte";
  import CautionNote from "./CautionNote.svelte";
  import ModelConnect from "./ModelConnect.svelte";
  import ModelExplanation from "./ModelExplanation.svelte";
  import ModelInput from "./ModelInput.svelte";
  import ScoreTrend from "./ScoreTrend.svelte";
  import ModelReviewRequest from "./ModelReviewRequest.svelte";
  import {num} from "../format";
  import {readPermission} from "../outlook-briefings";
  import {assetTabUrl} from "../routes";
  import {
    loadModelBindings,loadModelTrace,loadModelRun,loadModelPosition,modelName,NoModelEvidence,scoreSummary,
    type ModelBinding,type ModelRun,type ModelTrace,type StepPointer,
  } from "../model-evidence";

  let {assetId}:{assetId:string}=$props();
  type State="loading"|"ready"|"empty"|"unavailable"|"failed";
  let listState:State=$state("loading");
  let traceState:State=$state("empty");
  let detailState:State=$state("empty");
  let bindings:ModelBinding[]=$state([]);
  let binding:ModelBinding|null=$state(null);
  let trace:ModelTrace|null=$state(null);
  let trendSteps:StepPointer[]=$state([]);
  let selectedStep:StepPointer|null=$state(null);
  let result:ModelRun|null=$state(null);
  let error=$state("");
  let writable=$state(false);
  let explanationId:string|null=$state(null);
  const params=new URLSearchParams(location.search);
  let selectedBinding=$state(params.get("model_binding")??"");
  let selectedPosition=$state(params.get("model_position")??"");
  let followLatest=$state(!params.has("model_position"));
  let polling=false;
  let pollRequest:AbortController|null=null;
  let listRequest:AbortController|null=null;
  let traceRequest:AbortController|null=null;
  let resultRequest:AbortController|null=null;
  const clock=(raw:string|null)=>raw?new Date(raw).toLocaleString("ko-KR",{timeZone:"Asia/Seoul"}):"원본 기록 시각 없음";
  const stringify=(v:unknown)=>JSON.stringify(v,null,2);
  const place=(position:number)=>binding?.stepKind==="observation-window"
    ?"시간 구간 #"+position:"측정 순서 #"+position;
  // The recent list, plus a step chosen from the trend that is older than it.
  const choices=$derived.by(():StepPointer[]=>{
    const steps=trace?.steps??[];
    const chosen=selectedStep;
    return chosen&&!steps.some(step=>step.position===chosen.position)?[chosen,...steps]:steps;
  });
  // Earlier analyzed results of the same model, newest first, to compare against.
  const earlier=$derived.by(():number[]=>{
    const current=result;
    if(!trace||!current)return [];
    const all=(trendSteps.length?trendSteps:trace.steps).filter(step=>step.state==="analyzed"&&step.position<current.position)
      .map(step=>step.position).sort((a,b)=>b-a);
    return all.length>128?[...all.slice(0,128),all[all.length-1]]:all;
  });

  function remember(){
    if(!binding)return;
    const url=new URL(location.href);
    url.searchParams.set("monitor_asset",assetId);
    url.searchParams.set("model_binding",binding.bindingId);
    if(selectedStep)url.searchParams.set("model_position",String(selectedStep.position));
    else url.searchParams.delete("model_position");
    history.replaceState(history.state,"",url);
  }
  async function loadBindings(){
    listRequest?.abort();traceRequest?.abort();resultRequest?.abort();
    const request=new AbortController();listRequest=request;
    bindings=[];binding=null;trace=null;selectedStep=null;result=null;
    listState="loading";traceState="empty";detailState="empty";error="";
    try{
      const available=await loadModelBindings(assetId,request.signal);
      if(request.signal.aborted)return;
      bindings=available;
      if(!available.length){listState="empty";return;}
      listState="ready";
      const desired=selectedBinding?available.find(b=>b.bindingId===selectedBinding):available[0];
      if(!desired){listState="unavailable";error="북마크의 적용 모델은 이 설비에 없습니다. 다른 모델 결과로 대신하지 않습니다.";return;}
      await chooseBinding(desired.bindingId);
    }catch(cause:unknown){
      if(request.signal.aborted)return;
      error=cause instanceof Error?cause.message:"저장된 모델 바인딩 목록 조회 실패";
      listState="failed";
    }
  }
  async function chooseBinding(bindingId:string){
    traceRequest?.abort();resultRequest?.abort();
    const matched=bindings.find(item=>item.bindingId===bindingId);
    if(!matched)return;
    if(binding && binding.bindingId!==matched.bindingId){selectedPosition="";followLatest=true;}
    binding=matched;selectedBinding=bindingId;trace=null;trendSteps=[];selectedStep=null;result=null;
    traceState="loading";detailState="empty";error="";
    const request=new AbortController();traceRequest=request;
    try{
      const data=await loadModelTrace(matched,request.signal);
      if(request.signal.aborted)return;
      trace=data;
      if(!data.steps.length){traceState="empty";remember();return;}
      traceState="ready";
      const wanted=Number(selectedPosition);
      if(selectedPosition&&!data.steps.some(item=>item.position===wanted)){
        const record=await loadModelPosition(matched,wanted,request.signal);
        if(request.signal.aborted)return;
        selectedStep={position:record.position,runId:record.runId,state:record.state,stepKey:record.stepKey,changeSeq:record.changeSeq,reason:record.reason};
        result=record;detailState="ready";remember();return;
      }
      const step=data.steps.find(item=>item.position===wanted)
        ??data.steps.find(item=>item.position===matched.lastAnalyzed)
        ??data.steps.find(item=>item.state==="analyzed")??data.steps[0];
      await chooseStep(step);
    }catch(cause:unknown){
      if(request.signal.aborted)return;
      traceState=cause instanceof NoModelEvidence?"unavailable":"failed";
      error=cause instanceof Error?cause.message:"모델 저장 단계 목록 조회 실패";
    }
  }
  async function chooseStep(step:StepPointer){
    // A step may come from the recent list or from the whole score trend; the read checks it.
    if(!binding)return;
    resultRequest?.abort();
    const request=new AbortController();resultRequest=request;
    selectedStep=step;selectedPosition=String(step.position);
    result=null;detailState="loading";error="";remember();
    const frozen=binding;
    try{
      const record=await loadModelRun(frozen,step,request.signal);
      if(request.signal.aborted)return;
      result=record;detailState="ready";
    }catch(cause:unknown){
      if(request.signal.aborted)return;
      detailState=cause instanceof NoModelEvidence?"unavailable":"failed";
      error=cause instanceof Error?cause.message:"모델 실행 근거 조회 실패";
    }
  }
  async function poll(){
    if(!followLatest||polling||document.visibilityState!=="visible"||!binding||listState!=="ready")return;
    polling=true;
    const current=binding,request=new AbortController();pollRequest=request;
    try{
      const models=await loadModelBindings(assetId,request.signal);
      const owner=models.find(item=>item.bindingId===current.bindingId);
      if(!owner)throw new Error("적용 모델을 다시 읽지 못했습니다.");
      const data=await loadModelTrace(owner,request.signal);
      if(request.signal.aborted||!followLatest||binding?.bindingId!==current.bindingId)return;
      const changed=owner.lastProcessed!==binding.lastProcessed;
      binding=owner;trace=data;
      if(changed)trendSteps=[];
      traceState=data.steps.length?"ready":"empty";
      const next=data.steps.find(item=>item.position===owner.lastAnalyzed)
        ??[...data.steps].reverse().find(item=>item.state==="analyzed")??data.steps.at(-1);
      if(next&&(!result||next.runId!==result.runId))await chooseStep(next);
    }catch(cause:unknown){
      if(!request.signal.aborted&&followLatest){result=null;detailState="failed";error="최신 모델 결과를 다시 읽지 못했습니다. 이전 결과로 대신하지 않습니다.";}
    }finally{polling=false;}
  }
  let connectedNotice=$state("");
  function connected(bindingId:string){
    selectedBinding=bindingId;selectedPosition="";followLatest=true;
    connectedNotice="모델을 연결했습니다. 분석 실행기가 입력을 분석하면 점수가 나타납니다.";
    void loadBindings();
  }
  onMount(()=>{
    const permission=new AbortController();
    void readPermission(permission.signal).then(allowed=>{
      if(!permission.signal.aborted)writable=allowed;
    }).catch(()=>{});
    void loadBindings();
    const timer=setInterval(()=>void poll(),3000);
    return()=>{
      clearInterval(timer);pollRequest?.abort();
      permission.abort();listRequest?.abort();traceRequest?.abort();resultRequest?.abort();
    };
  });
</script>

<section class="ui-panel" aria-labelledby="model-evidence-title">
  <h2 id="model-evidence-title">모델 이상 점수</h2>
  <p class="context">이 설비에 적용한 이상 탐지 모델이 측정마다 계산한 점수와 기준을 봅니다.</p>
  {#if connectedNotice}<StatusNotice message={connectedNotice}/>{/if}
  {#if listState==="loading"}
    <StatusNotice message="이 설비에 적용한 모델을 확인하고 있습니다."/>
  {:else if listState==="failed"}
    <StatusNotice kind="failure" title="적용 모델을 불러오지 못했습니다" message={error}
      actionLabel="다시 불러오기" onAction={()=>void loadBindings()}/>
  {:else if listState==="empty"}
    <StatusNotice kind="uncertain" title="적용한 이상 탐지 모델이 없습니다"
      message="모델 점수가 없다고 이상이 없다는 뜻은 아닙니다. 기준 구간 이탈로 변화를 확인할 수 있습니다."
      actionLabel="기준 구간 이탈 보기" actionHref={assetTabUrl(assetId,"anomaly","baseline")}/>
    <ModelConnect {assetId} {writable} hasModel={false} onConnected={connected}/>
  {:else if listState==="unavailable"}
    <StatusNotice kind="uncertain" title="북마크의 모델을 찾을 수 없습니다" message={error}/>
  {:else}
    {#if bindings.length>1}
      <label class="selector">적용 모델
        <select value={selectedBinding} onchange={e=>void chooseBinding(e.currentTarget.value)}>
          {#each bindings as item(item.bindingId)}
            <option value={item.bindingId}>{modelName(item)} · 데이터 출처 {item.sourceId}</option>
          {/each}
        </select>
      </label>
    {/if}
    {#if binding}
      <p class="context">적용 모델 <strong>{modelName(binding)}</strong> · 데이터 출처 {binding.sourceId}{binding.pointId?" · 측정 위치 "+binding.pointId:""}
        · {binding.stepKind==="acquisition-snapshot"?"진동 측정마다 계산":"시간 구간마다 계산"}{binding.recordedReplay?" · 기록 재생 데이터":""}</p>
      <p class="context">{followLatest?"최신 결과를 3초마다 확인합니다. 측정을 고르거나 질문을 시작하면 그 결과에 고정합니다.":"고른 결과에 고정했습니다."}
        <button type="button" class="ui-button" onclick={()=>{followLatest=!followLatest;if(followLatest)void poll();}}>{followLatest?"최신 결과 따라보기 멈추기":"최신 결과 따라보기"}</button></p>
      {#if !binding.packageAvailable}
        <StatusNotice kind="uncertain" message="모델 정보 파일을 읽지 못했습니다. 저장된 점수는 볼 수 있지만 모델이 맞는 범위는 확인할 수 없습니다."/>
      {/if}
      {#if binding.lastProcessed!==null&&binding.lastProcessed!==binding.lastAnalyzed}
        <StatusNotice kind="uncertain" message={"가장 최근 "+place(binding.lastProcessed)+"은 모델이 분석하지 않았습니다. 이전 점수를 최신 점수처럼 보여 주지 않습니다."}/>
      {/if}
      {#if traceState==="loading"}
        <StatusNotice message="최근 측정의 모델 결과 목록을 불러오고 있습니다."/>
      {:else if traceState==="failed"}
        <StatusNotice kind="failure" title="모델 결과 목록을 불러오지 못했습니다" message={error}
          actionLabel="다시 불러오기" onAction={()=>void chooseBinding(binding!.bindingId)}/>
      {:else if traceState==="unavailable"}
        <StatusNotice kind="uncertain" title="모델 결과 기록을 찾을 수 없습니다" message={error}/>
      {:else if traceState==="empty"}
        <StatusNotice kind="uncertain" message="아직 모델이 분석한 측정이 없습니다. 기록을 읽지 못한 경우와는 다릅니다."/>
      {:else if trace}
        {#key binding.bindingId+":"+binding.lastProcessed}
          <ScoreTrend {binding} selected={selectedStep?.position??null} {place} onSelect={step=>{followLatest=false;void chooseStep(step);}} onLoaded={steps=>trendSteps=steps}/>
        {/key}
        <label class="selector">측정 선택 (최근 {trace.limit}회)
          <select value={selectedStep?String(selectedStep.position):""}
            onchange={e=>{
              const item=choices.find(s=>String(s.position)===e.currentTarget.value);
              if(item){followLatest=false;void chooseStep(item);}
            }}>
            {#each choices as item(item.runId)}
              <option value={String(item.position)} selected={selectedStep?.position===item.position}>{place(item.position)} · {item.state==="analyzed"?"분석함":"분석에서 제외"}</option>
            {/each}
          </select>
        </label>
        {#if trace.steps.length===trace.limit}
          <p class="context">최근 {trace.limit}회만 고를 수 있습니다. 이전 기록이 없다는 뜻은 아닙니다.</p>
        {/if}
        {#if detailState==="loading"}
          <StatusNotice message="선택한 측정의 모델 결과와 입력 파일을 맞춰 보고 있습니다."/>
        {:else if detailState==="failed"}
          <StatusNotice kind="failure" title="모델 결과를 확인하지 못했습니다" message={error}
            actionLabel="다시 확인" onAction={()=>{if(selectedStep)void chooseStep(selectedStep);}}/>
        {:else if detailState==="unavailable"}
          <StatusNotice kind="uncertain" title="선택한 모델 결과를 찾을 수 없습니다" message={error}/>
        {:else if result}
          {#if result.state==="skipped"}
            <StatusNotice kind="uncertain" title="이 측정은 모델 분석에서 제외됐습니다"
              message={result.reason??"제외 사유가 기록되지 않았습니다."}/>
          {:else}
            {@const summary=scoreSummary(result.output)}
            <div class="score" role="group" aria-label={place(result.position)+" 모델 결과"} data-model-position={result.position} data-model-event-start={result.eventStart ?? ""}>
              <div><span>모델 점수</span><strong>{num(summary.score,"기록 없음")}</strong></div>
              <div><span>모델 기준</span><strong>{num(summary.threshold,"기록 없음")}</strong></div>
              <div><span>기준 대비</span><strong>{summary.exceeds===null?"판단 정보 없음":summary.exceeds?"기준 초과":"기준 이하"}</strong></div>
            </div>
          {/if}
          <p class="context">{place(result.position)} · 측정 시각 {result.eventStart?clock(result.eventStart):"기록 없음"}{result.eventEnd&&result.eventEnd!==result.eventStart?" ~ "+clock(result.eventEnd):""}
            · 모델 처리 {clock(result.processedAt)}{result.replay?" · 기록 재생":""}</p>
          {#key result.runId}<ModelInput {binding} position={result.position} {place}/>{/key}
          {#if result.state!=="skipped"}
            {#key result.runId}
              <ModelExplanation {binding} run={result} {earlier} {writable} {place}
                onInteract={()=>followLatest=false} onExplained={id=>explanationId=id}/>
              <ModelReviewRequest {binding} run={result} {explanationId} {writable}/>
            {/key}
            <CautionNote message="모델 점수는 학습한 평소 상태와의 차이입니다. 고장 확률이나 고장 원인이 아닙니다. AI 해설은 저장된 측정값 비교를 설명할 뿐 원인을 진단하지 않습니다."/>
          {/if}
          <details>
            <summary>기술 상세</summary>
            <dl>
              <div><dt>적용 모델(binding)</dt><dd>{binding.bindingId}</dd></div>
              <div><dt>모델 패키지</dt><dd>{binding.packageId}</dd></div>
              <div><dt>모델 작업</dt><dd>{binding.task??"확인 불가"}</dd></div>
              <div><dt>모델 상태</dt><dd>{binding.health}</dd></div>
              <div><dt>모델 실행 기록</dt><dd>{result.runId}</dd></div>
              <div><dt>저장 단계 키</dt><dd>{result.stepKey}</dd></div>
              <div><dt>입력 파일 확인값</dt><dd>{String(result.inputReference.sha256??result.inputReference.input_digest??"없음")}</dd></div>
              <div><dt>시간 구간 ID</dt><dd>{String(result.inputReference.window_id??"해당 없음")}</dd></div>
            </dl>
            {#if result.state!=="skipped"}
              <h4>모델 출력 원본</h4>
              <pre>{stringify(result.output)}</pre>
              <h4>입력 특징값</h4>
              {#if result.features===null}
                <p class="context">이 실행에는 입력 특징값이 저장되지 않았습니다.</p>
              {:else}
                <pre>{stringify(result.features)}</pre>
              {/if}
            {/if}
          </details>
        {/if}
      {/if}
    {/if}
    <ModelConnect {assetId} {writable} hasModel={true} onConnected={connected}/>
  {/if}
</section>
<style>
  .context{color:var(--color-ink-muted);overflow-wrap:anywhere}
  .selector{display:grid;gap:var(--space-2);margin-block:var(--space-4);font-weight:650}
  select{width:100%;min-width:0;border:1px solid var(--color-border);
    border-radius:var(--radius-control);padding:var(--space-3);
    background:var(--color-surface);color:var(--color-ink)}
  .score{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:var(--space-3);margin-block:var(--space-4)}
  .score div{border:1px solid var(--color-border);border-radius:var(--radius-control);padding:var(--space-4);display:grid;gap:var(--space-1)}
  .score span{font-size:var(--font-small);color:var(--color-ink-muted)}
  .score strong{font-size:var(--font-section)}
  summary{cursor:pointer;font-weight:700;padding-block:var(--space-3)}
  dl{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:var(--space-3)}
  dt{font-size:var(--font-small);color:var(--color-ink-muted)}
  dd{margin:0;font-weight:650;overflow-wrap:anywhere}
  pre{max-width:100%;overflow:auto;padding:var(--space-3);
    background:var(--color-surface-secondary,var(--color-surface));border:1px solid var(--color-border);
    border-radius:var(--radius-panel);white-space:pre-wrap;overflow-wrap:anywhere}
</style>
