<script lang="ts">
  import {onMount} from "svelte";
  import StatusNotice from "./StatusNotice.svelte";
  import {
    loadModelBindings,loadModelTrace,loadModelRun,NoModelEvidence,
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
  <h2 id="model-evidence-title">저장 모델 실행과 입력 근거</h2>
  <p class="context">저장된 모델 패키지·binding·AnalysisRun·입력 해시를 확인합니다. 모델 이상 점수는
    설비 고장 확률이 아니며, 분석 시각은 수집 시각과 다릅니다.
    이 PHM 모델 저장 형식에는 별도의 운영 Evidence ID가 없으므로 임의로 생성하지 않습니다.</p>
  {#if listState==="loading"}
    <StatusNotice message="설비에 명시적으로 연결된 모델 목록을 확인하고 있습니다."/>
  {:else if listState==="failed"}
    <StatusNotice kind="failure" title="모델 목록 조회 실패" message={error}
      actionLabel="목록 다시 조회" onAction={()=>void loadBindings()}/>
  {:else if listState==="empty"}
    <StatusNotice kind="uncertain" title="연결된 모델 실행이 없습니다"
      message="설비에 연결된 활성 모델 바인딩이 없습니다. 설비가 정상이라는 의미가 아닙니다."/>
  {:else}
    <label class="selector">저장 모델 바인딩
      <select value={selectedBinding} onchange={e=>void chooseBinding(e.currentTarget.value)}>
        {#each bindings as item(item.bindingId)}
          <option value={item.bindingId}>{item.bindingId} · {item.sourceId} · {item.packageId}</option>
        {/each}
      </select>
    </label>
    {#if binding}
      <dl>
        <div><dt>모델 binding</dt><dd>{binding.bindingId}</dd></div>
        <div><dt>설비</dt><dd>{binding.assetId}</dd></div>
        <div><dt>원본 출처</dt><dd>{binding.sourceId}</dd></div>
        <div><dt>측정 지점</dt><dd>{binding.pointId??"별도 지점 없음"}</dd></div>
        <div><dt>패키지</dt><dd>{binding.packageId}</dd></div>
        <div><dt>모델 작업</dt><dd>{binding.task??"확인 불가"}</dd></div>
        <div><dt>입력 축</dt><dd>{binding.stepKind==="acquisition-snapshot"?"획득 순번":"저장 관측 윈도우"}</dd></div>
        <div><dt>모델 실행 상태</dt><dd>{binding.health} · 설비 건전성 판정 아님</dd></div>
      </dl>
      {#if !binding.packageAvailable}
        <StatusNotice kind="uncertain" message="패키지 manifest를 조회하지 못했습니다. 저장 실행은 볼 수 있어도 모델 적합성이나 검증 범위는 주장할 수 없습니다."/>
      {/if}
      {#if binding.lastProcessed!==null&&binding.lastProcessed!==binding.lastAnalyzed}
        <StatusNotice kind="uncertain" message="가장 최근 처리 단계와 최근 분석 성공 단계가 다릅니다. 제외·대기 입력을 마지막 점수로 대체하지 않습니다."/>
      {/if}
      {#if traceState==="loading"}
        <StatusNotice message="최근 모델 실행 단계와 선택 가능한 AnalysisRun을 읽고 있습니다."/>
      {:else if traceState==="failed"}
        <StatusNotice kind="failure" title="모델 이력 조회 실패" message={error}
          actionLabel="이력 다시 조회" onAction={()=>void chooseBinding(binding!.bindingId)}/>
      {:else if traceState==="unavailable"}
        <StatusNotice kind="uncertain" title="모델 저장 이력을 찾을 수 없습니다" message={error}/>
      {:else if traceState==="empty"}
        <StatusNotice kind="uncertain" message="조회 가능한 최근 실행 이력이 없습니다. 저장소 오류와 혼동하지 마세요."/>
      {:else if trace}
        <label class="selector">모델 실행 회차 (최근 {trace.limit}개 범위)
          <select value={selectedStep?String(selectedStep.position):""}
            onchange={e=>{
              const item=trace!.steps.find(s=>String(s.position)===e.currentTarget.value);
              if(item)void chooseStep(item);
            }}>
            {#each trace.steps as item(item.runId)}
              <option value={item.position}>{item.position} · {item.state==="analyzed"?"분석":"제외"} · {item.runId}</option>
            {/each}
          </select>
        </label>
        {#if trace.steps.length===trace.limit}
          <StatusNotice kind="uncertain" message="이 화면은 최근 64개 저장 단계만 선택할 수 있습니다. 더 오래된 결과가 없다는 뜻이 아닙니다."/>
        {/if}
        {#if detailState==="loading"}
          <StatusNotice message="선택한 AnalysisRun과 입력 원본을 대조하고 있습니다."/>
        {:else if detailState==="failed"}
          <StatusNotice kind="failure" title="모델 근거 일치 검증 실패" message={error}
            actionLabel="해당 실행 재조회" onAction={()=>{if(selectedStep)void chooseStep(selectedStep);}}/>
        {:else if detailState==="unavailable"}
          <StatusNotice kind="uncertain" title="선택한 모델 실행을 조회할 수 없습니다" message={error}/>
        {:else if result}
          <h3>선택한 저장 실행 근거</h3>
          <dl>
            <div><dt>AnalysisRun</dt><dd>{result.runId}</dd></div>
            <div><dt>저장 단계 키</dt><dd>{result.stepKey}</dd></div>
            <div><dt>입력 위치</dt><dd>{result.position} · {result.evidenceKind==="acquisition-snapshot"?"획득 회차(시간 아님)":"관측 윈도우 정렬 키"}</dd></div>
            <div><dt>처리 상태</dt><dd>{result.state==="analyzed"?"모델 분석 성공":"입력 제외"}</dd></div>
            <div><dt>재생 입력</dt><dd>{result.replay?"기록 재생":"재생 아님"}</dd></div>
            <div><dt>측정 시작</dt><dd>{clock(result.eventStart)}</dd></div>
            <div><dt>측정 끝</dt><dd>{clock(result.eventEnd)}</dd></div>
            <div><dt>모델 처리 시각</dt><dd>{clock(result.processedAt)}</dd></div>
            <div><dt>원본 입력 해시</dt><dd>{String(result.inputReference.sha256??result.inputReference.input_digest??"없음")}</dd></div>
            <div><dt>윈도우 ID</dt><dd>{String(result.inputReference.window_id??"해당 없음")}</dd></div>
          </dl>
          {#if result.state==="skipped"}
            <StatusNotice kind="uncertain" title="이 단계는 모델 분석에서 제외됐습니다"
              message={result.reason??"제외 사유 없음"}/>
          {:else}
            <p class="context">아래는 서버가 저장한 모델 출력입니다. 프런트엔드에서 점수·임계값·변수 기여도를 새로 계산하지 않습니다.</p>
            <h4>원본 모델 출력</h4>
            <pre>{stringify(result.output)}</pre>
            <h4>저장 입력 특징</h4>
            {#if result.features===null}
              <StatusNotice kind="uncertain" message="이 모델 실행에 저장된 특징 근거가 없습니다."/>
            {:else}
              <pre>{stringify(result.features)}</pre>
            {/if}
          {/if}
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
  dl{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:var(--space-3)}
  dt{font-size:var(--font-small);color:var(--color-ink-muted)}
  dd{margin:0;font-weight:650;overflow-wrap:anywhere}
  pre{max-width:100%;overflow:auto;padding:var(--space-3);
    background:var(--color-surface-secondary,var(--color-surface));border:1px solid var(--color-border);
    border-radius:var(--radius-panel);white-space:pre-wrap;overflow-wrap:anywhere}
</style>
