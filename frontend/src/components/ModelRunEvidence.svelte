<script lang="ts">
  import {onMount} from "svelte";
  import StatusNotice from "./StatusNotice.svelte";
  import CautionNote from "./CautionNote.svelte";
  import {num} from "../format";
  import {assetTabUrl} from "../routes";
  import {
    loadModelBindings,loadModelTrace,loadModelRun,NoModelEvidence,scoreSummary,
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
  let selectedStep:StepPointer|null=$state(null);
  let result:ModelRun|null=$state(null);
  let error=$state("");
  const params=new URLSearchParams(location.search);
  let selectedBinding=$state(params.get("model_binding")??"");
  let selectedPosition=$state(params.get("model_position")??"");
  let listRequest:AbortController|null=null;
  let traceRequest:AbortController|null=null;
  let resultRequest:AbortController|null=null;
  const clock=(raw:string|null)=>raw?new Date(raw).toLocaleString("ko-KR",{timeZone:"Asia/Seoul"}):"원본 기록 시각 없음";
  const stringify=(v:unknown)=>JSON.stringify(v,null,2);
  const place=(position:number)=>binding?.stepKind==="observation-window"
    ?"시간 구간 #"+position:"측정 순서 #"+position;

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
      const desired=available.find(b=>b.bindingId===selectedBinding)??available[0];
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
    if(binding && binding.bindingId!==matched.bindingId)selectedPosition="";
    binding=matched;selectedBinding=bindingId;trace=null;selectedStep=null;result=null;
    traceState="loading";detailState="empty";error="";
    const request=new AbortController();traceRequest=request;
    try{
      const data=await loadModelTrace(matched,request.signal);
      if(request.signal.aborted)return;
      trace=data;
      if(!data.steps.length){traceState="empty";remember();return;}
      traceState="ready";
      const wanted=Number(selectedPosition);
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
    if(!trace?.steps.some(s=>s.position===step.position&&s.runId===step.runId)||!binding)return;
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
  onMount(()=>{void loadBindings();return()=>{
    listRequest?.abort();traceRequest?.abort();resultRequest?.abort();
  };});
</script>

<section class="ui-panel" aria-labelledby="model-evidence-title">
  <h2 id="model-evidence-title">모델 이상 점수</h2>
  <p class="context">이 설비에 적용한 이상 탐지 모델이 측정마다 계산한 점수와 기준을 봅니다.</p>
  {#if listState==="loading"}
    <StatusNotice message="이 설비에 적용한 모델을 확인하고 있습니다."/>
  {:else if listState==="failed"}
    <StatusNotice kind="failure" title="적용 모델을 불러오지 못했습니다" message={error}
      actionLabel="다시 불러오기" onAction={()=>void loadBindings()}/>
  {:else if listState==="empty"}
    <StatusNotice kind="uncertain" title="적용한 이상 탐지 모델이 없습니다"
      message="모델 점수가 없다고 이상이 없다는 뜻은 아닙니다. 기준 구간 이탈로 변화를 확인할 수 있습니다."
      actionLabel="기준 구간 이탈 보기" actionHref={assetTabUrl(assetId,"anomaly","baseline")}/>
  {:else}
    {#if bindings.length>1}
      <label class="selector">적용 모델
        <select value={selectedBinding} onchange={e=>void chooseBinding(e.currentTarget.value)}>
          {#each bindings as item(item.bindingId)}
            <option value={item.bindingId}>{item.packageId} · 데이터 출처 {item.sourceId}</option>
          {/each}
        </select>
      </label>
    {/if}
    {#if binding}
      <p class="context">적용 모델 <strong>{binding.packageId}</strong> · 데이터 출처 {binding.sourceId}{binding.pointId?" · 측정 위치 "+binding.pointId:""}
        · {binding.stepKind==="acquisition-snapshot"?"진동 측정마다 계산":"시간 구간마다 계산"}{binding.recordedReplay?" · 기록 재생 데이터":""}</p>
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
        <label class="selector">측정 선택 (최근 {trace.limit}회)
          <select value={selectedStep?String(selectedStep.position):""}
            onchange={e=>{
              const item=trace!.steps.find(s=>String(s.position)===e.currentTarget.value);
              if(item)void chooseStep(item);
            }}>
            {#each trace.steps as item(item.runId)}
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
            <div class="score" role="group" aria-label={place(result.position)+" 모델 결과"}>
              <div><span>모델 점수</span><strong>{num(summary.score,"기록 없음")}</strong></div>
              <div><span>모델 기준</span><strong>{num(summary.threshold,"기록 없음")}</strong></div>
              <div><span>기준 대비</span><strong>{summary.exceeds===null?"판단 정보 없음":summary.exceeds?"기준 초과":"기준 이하"}</strong></div>
            </div>
          {/if}
          <p class="context">{place(result.position)} · 측정 시각 {result.eventStart?clock(result.eventStart):"기록 없음"}{result.eventEnd&&result.eventEnd!==result.eventStart?" ~ "+clock(result.eventEnd):""}
            · 모델 처리 {clock(result.processedAt)}{result.replay?" · 기록 재생":""}</p>
          {#if result.state!=="skipped"}
            <CautionNote message="모델 점수는 학습한 평소 상태와의 차이입니다. 고장 확률이나 고장 원인이 아닙니다."/>
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
