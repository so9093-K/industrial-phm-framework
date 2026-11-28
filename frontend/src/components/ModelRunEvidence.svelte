<script lang="ts">
  import {clockText, spanText} from "../date-format";
  import {exposeAnalysis, type AnalysisReadout} from "../analysis-readout.svelte";
  import AnalysisControls from "./AnalysisControls.svelte";
  import TaskDialog from "./TaskDialog.svelte";
  import {readableSourceId} from "../operations-status";
  import {onMount,tick,untrack} from "svelte";
  import StatusNotice from "./StatusNotice.svelte";
  import ModelConnect from "./ModelConnect.svelte";
  import ModelBuild from "./ModelBuild.svelte";
  import ModelExplanation from "./ModelExplanation.svelte";
  import ModelInput from "./ModelInput.svelte";
  import ScoreTrend from "./ScoreTrend.svelte";
  import ModelScoreOverlay from "./ModelScoreOverlay.svelte";
  import ModelReviewRequest from "./ModelReviewRequest.svelte";
  import ScoreReason from "./ScoreReason.svelte";
  import {selectedScoreMessage} from "../analysis-messages";
  import {num} from "../format";
  import {readWriteSession} from "../session";
  import {assetTabUrl} from "../routes";
  import {
    loadModelBindings,loadModelTrace,loadModelRun,loadLatestScores,latestModel,loadModelPosition,modelNames,NoModelEvidence,scoreSummary,isTimeWindow,windowLabel,builtModelNote,skipReasonText,isUnjudged,
    type ModelBinding,type ModelRun,type ModelTrace,type StepPointer,
  } from "../model-evidence";
  import {beforeInterval,type Interval,type TrendPoint} from "../model-trend";
  import {changeRef} from "../analysis-chat";
  import {scoreRaisers} from "../score-raisers";
  import {readScoreReason,type ScoreReason as Reason} from "../score-reason";
  import type {AcquisitionTiming} from "../asset-data";
  import {measurementLabel} from "../time-axis";
  import {measurementLinks} from "../measurement-links";
  import {loadFeatureSource,type FeatureSource} from "../acquisition-profile";

  let {assetId,timing=null,measurements=null,selectedPosition:overviewPosition=null,onPosition}:{assetId:string;timing?:AcquisitionTiming|null;
    selectedPosition?:number|null;onPosition?:(at:number)=>void;
    /** First and last stored vibration measurement, to continue from a chosen one. */
    measurements?:{first:number;last:number}|null}=$props();
  type State="loading"|"ready"|"empty"|"unavailable"|"failed";
  let listState:State=$state("loading");
  let traceState:State=$state("empty");
  let detailState:State=$state("empty");
  let bindings:ModelBinding[]=$state([]);
  let featureSource:FeatureSource|null=$state(null);
  let binding:ModelBinding|null=$state(null);
  const period = $derived.by(() => {
    const current: ModelBinding | null = binding;
    return current && timing && current.stepKind === "acquisition-snapshot"
      && current.pointId === null && current.sourceId === timing.sourceId ? timing.periodSeconds : null;
  });
  let trace:ModelTrace|null=$state(null);
  let trendSteps:StepPointer[]=$state([]);
  let intervals:Interval[]=$state([]);
  let selectedStep:StepPointer|null=$state(null);
  let result:ModelRun|null=$state(null);
  $effect(()=>{
    const at=overviewPosition,ready=traceState==="ready";
    if(at===null||!ready)return;
    untrack(()=>{if(selectedStep?.position!==at)void pick(at);});
  });
  let error=$state("");
  let writable=$state(false);
  let explanationId:string|null=$state(null);
  // Why the selected result went over its threshold, read only for a result that did.
  let reason:Reason|null=$state(null);
  $effect(()=>{
    const model=binding,run=result;
    reason=null;
    if(!model||!run||run.state!=="analyzed"||run.output.exceeds_threshold!==true)return;
    const request=new AbortController();
    void readScoreReason(model,run,request.signal).then(value=>{if(!request.signal.aborted)reason=value;}).catch(()=>{});
    return()=>request.abort();
  });
  let reviewRun:string|null=$state(null), explanationRun:string|null=$state(null);
  let reviewPanel: HTMLDetailsElement | null = $state(null);
  // The hash target appears after asynchronous model reads, beyond native anchor navigation,
  // and the explanation above it keeps growing as its own reads finish. Keep the panel in view
  // until the reader takes over; after that, choosing another measurement keeps their place.
  let reviewTarget = location.hash === "#model-review";
  $effect(() => {
    const panel = reviewPanel;
    if (!panel || !reviewTarget) return;
    const TAKEOVER = ["wheel", "touchstart", "pointerdown", "keydown"] as const;
    let frame = 0;
    const reach = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const summary = panel.querySelector("summary");
        if (summary && document.activeElement !== summary) summary.focus({preventScroll: true});
        panel.scrollIntoView({block: "start"});
      });
    };
    const layout = new ResizeObserver(reach);
    const stop = () => {
      cancelAnimationFrame(frame); layout.disconnect();
      for (const name of TAKEOVER) removeEventListener(name, release, true);
    };
    function release() { reviewTarget = false; stop(); }
    for (const name of TAKEOVER) addEventListener(name, release, {capture: true, passive: true});
    layout.observe(document.body);
    return stop;
  });
  const params=new URLSearchParams(location.search);
  const investigation=changeRef(location.search);
  const modelChange=$derived.by(()=>{
    const current:ModelBinding|null=binding;
    return current && investigation && (investigation.kind==="history")===isTimeWindow(current.stepKind) ? investigation : null;
  });
  let changeResponse=$state<string|null>(null);
  let selectedBinding=$state(params.get("model_binding")??"");
  let selectedPosition=$state(params.get("model_position")??"");
  let inspectedByUser=$state(params.has("model_position"));
  let followLatest=$state(!params.has("model_position"));
  let polling=false;
  let pollRequest:AbortController|null=null;
  let listRequest:AbortController|null=null;
  let traceRequest:AbortController|null=null;
  let resultRequest:AbortController|null=null;
  const clock = (at: string | null) => at ? clockText(at, "second") : "원본 기록 시각 없음";
  const stringify=(v:unknown)=>JSON.stringify(v,null,2);
  let inputOpen=$state(false),comparisonOpen=$state(false);
  async function showSelectedInput() {
    followLatest = false;
    inputOpen=true;
    await tick();
    await tick();
    const input = document.getElementById("selected-model-input") as HTMLDetailsElement | null;
    if (input) input.open = true;
    input?.focus({preventScroll: true});
    input?.scrollIntoView({block: "start"});
  }
  const place=(position:number)=>binding&&isTimeWindow(binding.stepKind)
    ?windowLabel(position):measurementLabel(position);
  const timelinePlace=(position:number)=>binding&&isTimeWindow(binding.stepKind) ? place(position) : measurementLabel(position,period);
  // The review sits below the explanation; it names the result it would leave for review.
  const reviewSubject=(current:ModelBinding,run:ModelRun)=>{
    const exceeds=scoreSummary(run.output).exceeds;
    return [names.get(current.bindingId)??"모델",place(run.position),exceeds===null?"판단 정보 없음":exceeds?"기준 초과":"기준 이하"].join(" · ");
  };
  // The recent list, plus a step chosen from the trend that is older than it.
  function adjacent(direction:number):StepPointer|undefined {
    const at=selectedStep?.position;
    if(at===undefined)return undefined;
    // A recent-only list cannot establish the next step of an older bookmarked result.
    const steps=trendSteps;
    if(!steps.some(step=>step.position===at))return undefined;
    return [...steps].filter(step=>direction<0?step.position<at:step.position>at)
      .sort((a,b)=>direction<0?b.position-a.position:a.position-b.position)[0];
  }
  const choices=$derived.by(():StepPointer[]=>{
    const steps=trace?.steps??[];
    const chosen=selectedStep;
    return chosen&&!steps.some(step=>step.position===chosen.position)?[chosen,...steps]:steps;
  });
  const names=$derived(modelNames(bindings));
  // Models on the same measurement stream share positions, so they can be drawn together.
  const comparable=$derived.by(():ModelBinding[]=>{
    const current=binding;
    // 실행할 수 없는 모델은 비교 후보가 아니다(지금 보고 있는 모델이면 그대로 둔다).
    return current?bindings.filter(item=>item.sourceId===current.sourceId&&item.stepKind===current.stepKind&&item.pointId===current.pointId
      &&item.lastAnalyzed!==null&&item.lastAnalyzed===current.lastAnalyzed&&(item===current||item.health!=="unavailable")):[];
  });
  // A measurement inside an over-threshold run is compared with the last one before the run.
  const suggested=$derived.by(():number|null=>{
    const current=result;
    if(!current)return null;
    return beforeInterval(intervals,trendSteps.filter(step=>step.state==="analyzed").map(step=>step.position),current.position);
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
    if(selectedStep&&(!modelChange||inspectedByUser||overviewPosition!==null)){
      url.searchParams.set("model_position",String(selectedStep.position));
      if(binding.stepKind==="acquisition-snapshot"){
        url.searchParams.set("vibration_at",String(selectedStep.position));
        if(featureSource?.sourceId===binding.sourceId)url.searchParams.set("acquisition_binding",featureSource.bindingId);
      }
    }
    else url.searchParams.delete("model_position");
    history.replaceState(history.state,"",url);
  }
  $effect(()=>{if(result&&location.hash==="#selected-model-input")void tick().then(showSelectedInput);});
  async function loadBindings(){
    listRequest?.abort();traceRequest?.abort();resultRequest?.abort();
    const request=new AbortController();listRequest=request;
    bindings=[];binding=null;trace=null;selectedStep=null;result=null;
    listState="loading";traceState="empty";detailState="empty";error="";
    try{
      const [models,features]=await Promise.all([loadModelBindings(assetId,request.signal),
        measurements?loadFeatureSource(assetId,request.signal).catch(()=>null):Promise.resolve(null)]);
      const available=features?models.filter(model=>model.sourceId===features.sourceId&&model.pointId===null):models;
      if(request.signal.aborted)return;
      featureSource=features;
      bindings=available;
      if(!available.length){listState="empty";return;}
      listState="ready";
      // Without a bookmark, open the latest measurement; a failed read keeps the first.
      // 패키지를 불러올 수 없는 모델(폐기된 종류 등)은 저장된 결과만 남는다: 실행할 수 있는 모델을 먼저 연다.
      const runnable=available.filter(b=>b.health!=="unavailable");
      const candidates=runnable.length?runnable:available;
      const latest=selectedBinding||candidates.length<2?null
        :await loadLatestScores(assetId,request.signal,candidates).then(latestModel).catch(()=>null);
      if(request.signal.aborted)return;
      const desired=selectedBinding?available.find(b=>b.bindingId===selectedBinding)
        :candidates.find(b=>b.bindingId===latest?.bindingId)??candidates[0];
      if(!desired){listState="unavailable";error="북마크의 적용 모델은 이 설비에 없습니다.";return;}
      await chooseBinding(desired.bindingId);
    }catch(cause:unknown){
      if(request.signal.aborted)return;
      error=cause instanceof Error?cause.message:"저장된 모델 바인딩 목록 조회 실패";
      listState="failed";
    }
  }
  // Switching between models of one stream keeps the measurement in view, so it can be read by both.
  async function chooseBinding(bindingId:string,keepPosition=false){
    traceRequest?.abort();resultRequest?.abort();
    const matched=bindings.find(item=>item.bindingId===bindingId);
    if(!matched)return;
    if(binding && binding.bindingId!==matched.bindingId&&!(keepPosition&&selectedStep)){selectedPosition="";followLatest=true;inspectedByUser=false;}
    binding=matched;selectedBinding=bindingId;trace=null;trendSteps=[];intervals=[];selectedStep=null;result=null;changeResponse=null;
    traceState="loading";detailState="empty";error="";
    const request=new AbortController();traceRequest=request;
    try{
      const data=await loadModelTrace(matched,request.signal);
      if(request.signal.aborted)return;
      trace=data;
      if(!data.steps.length){traceState="empty";remember();return;}
      traceState="ready";
      const preferred=overviewPosition===null?selectedPosition:String(overviewPosition);
      const wanted=Number(preferred);
      if(preferred&&!data.steps.some(item=>item.position===wanted)){
        const record=await loadModelPosition(matched,wanted,request.signal);
        if(request.signal.aborted)return;
        selectedStep={position:record.position,runId:record.runId,state:record.state,stepKey:record.stepKey,changeSeq:record.changeSeq,reason:record.reason};
        result=record;detailState="ready";onPosition?.(record.position);remember();return;
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
    onPosition?.(step.position);
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
  function inspectStep(step:StepPointer) {
    inspectedByUser=true;
    followLatest=false;
    void chooseStep(step);
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
      bindings=models;binding=owner;trace=data;
      if(changed)trendSteps=[];
      traceState=data.steps.length?"ready":"empty";
      const next=data.steps.find(item=>item.position===owner.lastAnalyzed)
        ??[...data.steps].reverse().find(item=>item.state==="analyzed")??data.steps.at(-1);
      if(next&&(!result||next.runId!==result.runId))await chooseStep(next);
    }catch(cause:unknown){
      if(!request.signal.aborted&&followLatest){result=null;detailState="failed";error="최신 모델 결과를 다시 읽지 못했습니다.";}
    }finally{polling=false;}
  }
  async function pick(position:number){
    inspectedByUser=true;
    const step=trendSteps.find(item=>item.position===position)??trace?.steps.find(item=>item.position===position);
    if(step){followLatest=false;await chooseStep(step);return;}
    if(!binding)return;
    resultRequest?.abort();const request=new AbortController();resultRequest=request;
    const owner=binding;followLatest=false;result=null;detailState="loading";
    try{
      const read=await loadModelPosition(owner,position,request.signal);
      if(request.signal.aborted||binding.bindingId!==owner.bindingId)return;
      selectedStep={position:read.position,runId:read.runId,state:read.state,stepKey:read.stepKey,changeSeq:read.changeSeq,reason:read.reason};
      result=read;selectedPosition=String(read.position);detailState="ready";onPosition?.(read.position);remember();
    }catch(cause){if(!request.signal.aborted){detailState="failed";error=cause instanceof Error?cause.message:"선택한 측정을 읽지 못했습니다.";}}
  }
  let connectedNotice=$state("");
  // The notice outlives the panel that asked, since the model list is read again right after.
  function connected(bindingId:string,notice="모델을 연결했습니다. 분석 서비스가 입력을 분석하면 점수가 나타납니다."){
    selectedBinding=bindingId;selectedPosition="";followLatest=true;inspectedByUser=false;
    connectedNotice=notice;
    void loadBindings();
  }
  onMount(()=>{
    const permission=new AbortController();
    void readWriteSession(permission.signal).then(session=>{
      if(!permission.signal.aborted) writable=session.writable;
    }).catch(()=>{});
    void loadBindings();
    const timer=setInterval(()=>void poll(),3000);
    return()=>{
      clearInterval(timer);pollRequest?.abort();
      permission.abort();listRequest?.abort();traceRequest?.abort();resultRequest?.abort();
    };
  });

  exposeAnalysis((): AnalysisReadout | null => {
    if (!binding) return null;
    if (modelChange && changeResponse === null) return null;
    const model = names.get(binding.bindingId) ?? binding.bindingId;
    const measurement = result ? place(result.position) : null;
    const scope = modelChange
      ? modelChange.kind==="history" ? spanText(Date.parse(modelChange.start),Date.parse(modelChange.end)) : modelChange.from+"–"+modelChange.to+"번째 측정"
      : measurement;
    if (!scope) return null;
    const facts = {"조회 범위": scope, ...(changeResponse!==null ? {"변화 구간의 모델 반응":changeResponse}:{}), "선택한 모델": model};
    if (modelChange && !inspectedByUser && overviewPosition===null) return facts;
    const context = {...facts, ...(measurement!==null ? {"선택한 측정": measurement}:{})};
    if (detailState !== "ready" || !result) return changeResponse===null ? null : context;
    if (result.state === "skipped") return {...context,
      "모델 결과": skipReasonText(result.reason)};
    const {score, threshold, exceeds} = scoreSummary(result.output);
    const raised = scoreRaisers(result.output.feature_contributions).map(row=>row.signal).join(" · ");
    return {...context,
      "모델 점수": num(score, "기록 없음"), "모델 기준": num(threshold, "기록 없음"),
      "기준 대비": exceeds === null ? "판단 정보 없음" : exceeds ? "기준 초과" : "기준 이하",
      ...(raised ? {"점수를 올린 신호": raised} : {})};
  });

  function receiveTrend(steps:StepPointer[], found:Interval[], points:TrendPoint[]|null, truncated:boolean) {
    trendSteps=steps;
    intervals=found;
    if (!points) {changeResponse=null;return;}
    const judged=points.filter(point=>point.score!==null&&point.exceeds!==null);
    const crossed=judged.filter(point=>point.exceeds);
    changeResponse=(truncated?"읽은 점수만 · ":"")+(judged.length
      ? judged.length+"개 중 "+crossed.length+"개 모델 기준 초과"
      : "선택한 변화에 해당하는 모델 점수 없음");
    if (points.length>judged.length) changeResponse+=" · 판정하지 않은 입력 "+(points.length-judged.length)+"개";
    if (followLatest && overviewPosition===null) {
      followLatest=false;
      const initial=crossed[0]??judged.at(-1)??points[0];
      if (initial) void chooseStep(initial.pointer);
      else {selectedStep=null;result=null;resultRequest?.abort();detailState="empty";}
    }
  }
</script>

<section class="ui-panel" aria-labelledby="model-evidence-title">
  <h2 class="visually-hidden" id="model-evidence-title">모델 이상 점수</h2>
  {#if connectedNotice}<StatusNotice message={connectedNotice}/>{/if}
  {#if listState==="loading"}
    <StatusNotice message="이 설비에 적용한 모델을 확인하고 있습니다."/>
  {:else if listState==="failed"}
    <StatusNotice kind="failure" title="적용 모델을 불러오지 못했습니다" message={error}
      actionLabel="다시 불러오기" onAction={()=>void loadBindings()}/>
  {:else if listState==="empty"}
    <StatusNotice kind="uncertain" title="적용한 이상 탐지 모델이 없습니다"
      message="저장된 신호의 변화를 기록 변화 찾기에서 확인할 수 있습니다."
      actionLabel="기록 변화 찾기" actionHref={assetTabUrl(assetId,"anomaly","baseline")}/>
    <details><summary>이상 탐지 모델 설정</summary>
      <ModelConnect {assetId} {writable} hasModel={false} onConnected={connected}/>
      <ModelBuild {assetId} {writable} hasModel={false} onBuilt={connected}/>
    </details>
  {:else if listState==="unavailable"}
    <StatusNotice kind="uncertain" title="북마크의 모델을 찾을 수 없습니다" message={error}/>
  {:else}
    {#if binding}
      <div class="analysis-workspace model-workspace"><div class="model-toolbar">
      <label class="model-choice">이상 탐지 모델
        <select value={selectedBinding} onchange={e=>void chooseBinding(e.currentTarget.value,true)}>
          {#each bindings as model(model.bindingId)}<option value={model.bindingId}>{names.get(model.bindingId)}{model.health==="unavailable"?" · 실행할 수 없음":""}</option>{/each}
        </select>
      </label>
      <AnalysisControls title="모델 설정">{#snippet children()}{#if binding}
      <p class="context">적용 모델 <strong>{names.get(binding.bindingId)}</strong> · 데이터 출처 {readableSourceId(binding.sourceId,bindings.map(each=>each.sourceId))}{binding.pointId?" · 측정 위치 "+binding.pointId:""}
        · {binding.stepKind==="acquisition-snapshot"?"진동 측정마다 계산":"시간 구간마다 계산"}{binding.recordedReplay?" · 저장 기록 데이터":""}</p>
      {#if builtModelNote(binding)}<p class="context">{builtModelNote(binding)}</p>{/if}
      {#if trace}
      <p class="context">{followLatest?"최신 결과를 3초마다 확인합니다. 측정을 고르거나 질문을 시작하면 그 결과에 고정합니다.":"고른 결과에 고정했습니다."}
        <button type="button" class="ui-button" onclick={()=>{followLatest=!followLatest;if(followLatest)void poll();}}>{followLatest?"최신 결과 따라보기 멈추기":"최신 결과 따라보기"}</button></p>
      {/if}
      {/if}{/snippet}</AnalysisControls>
      {#if comparable.length>1}<button type="button" class="ui-button" onclick={()=>comparisonOpen=true}>다른 모델과 비교</button>{/if}
      <TaskDialog bind:open={comparisonOpen} title="같은 측정의 다른 모델 결과">
        {#if comparisonOpen&&comparable.length>1}
          {#key comparable.map(item=>item.bindingId+":"+item.lastProcessed).join(",")}
            <ModelScoreOverlay bindings={comparable} {names} selected={selectedBinding} selectedPosition={selectedStep?.position??null} place={timelinePlace} {period}
              onChoose={id=>{if(id!==binding?.bindingId)void chooseBinding(id,true);}} onPick={pick}/>
          {/key}
        {/if}
      </TaskDialog></div>
    <div class="analysis-body">
      {#if !binding.packageAvailable}
        <StatusNotice kind="uncertain" message="모델 정보 파일을 읽지 못했습니다. 저장된 점수는 볼 수 있지만 모델이 맞는 범위는 확인할 수 없습니다."/>
      {:else if binding.health==="unavailable"}
        <StatusNotice kind="uncertain" message="이 모델은 실행할 수 없어 새 측정을 분석하지 않습니다. 저장된 결과만 보입니다."/>
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
        <!-- 이상 탐지의 중심 그림: 점수 추이와 임계선(모델 기준), 넘은 구간. 시간축 옆에 열려도 보인다. -->
        {#key binding.bindingId+":"+binding.lastProcessed}
          <ScoreTrend {binding} {period} change={modelChange} selected={selectedStep?.position??null} pinned={!followLatest} place={timelinePlace}
            signal={reason?.rows[0]??null} onSelect={inspectStep} onLoaded={receiveTrend}/>
        {/key}
      {/if}
      </div>
      {#if trace}
      <div class="model-comparison-area">
        <div class="measurement-picker"><label class="selector">측정 선택
          <select value={selectedStep?String(selectedStep.position):""}
            onchange={e=>{
              const item=choices.find(s=>String(s.position)===e.currentTarget.value);
              if(item)inspectStep(item);
            }}>
            {#each choices as item(item.runId)}
              <option value={String(item.position)} selected={selectedStep?.position===item.position}>{place(item.position)} · {item.state==="analyzed"?"분석함":isUnjudged(item.reason??null)?"판정 안 함":"분석에서 제외"}</option>
            {/each}
          </select>
        </label>
        <div class="step-actions"><button type="button" class="ui-button" disabled={!adjacent(-1)} onclick={()=>{const step=adjacent(-1);if(step)inspectStep(step);}}>이전 측정</button><button type="button" class="ui-button" disabled={!adjacent(1)} onclick={()=>{const step=adjacent(1);if(step)inspectStep(step);}}>다음 측정</button><button type="button" class="ui-button" disabled={!result} onclick={showSelectedInput}>{measurements?"원본 파형·입력값":"입력 측정값"}</button></div></div>
        {#if detailState==="loading"}
          <StatusNotice message="선택한 측정의 모델 결과와 입력 파일을 맞춰 보고 있습니다."/>
        {:else if detailState==="failed"}
          <StatusNotice kind="failure" title="모델 결과를 확인하지 못했습니다" message={error}
            actionLabel="다시 확인" onAction={()=>{if(selectedStep)void chooseStep(selectedStep);}}/>
        {:else if detailState==="unavailable"}
          <StatusNotice kind="uncertain" title="선택한 모델 결과를 찾을 수 없습니다" message={error}/>
        {:else if result}
          {#if result.state==="skipped"}
            <StatusNotice kind="uncertain" title={isUnjudged(result.reason)?"이 구간은 판정하지 않았습니다":"이 측정은 모델 분석에서 제외됐습니다"}
              message={skipReasonText(result.reason)}/>
          {:else}
            {@const summary=scoreSummary(result.output)}
            <div class="selected-result"><h3>{place(result.position)}{summary.exceeds===null?"":summary.exceeds?" · 기준 초과":" · 기준 이하"}</h3>
              <span class="context">점수 {num(summary.score,"기록 없음")} · 모델 기준 {num(summary.threshold,"기록 없음")}</span>
            </div>
            {#if reason}<ScoreReason {reason}/>{/if}
          {/if}
          {#if result.state==="skipped"}<button type="button" class="ui-button input-details" onclick={()=>inputOpen=true}>원본·모델 상세</button>{/if}
          <TaskDialog bind:open={inputOpen} title="선택한 측정의 원본·모델 상세"><div class="selected-more">
          <div class="selected-meta"><p class="context">측정 시각 {result.eventStart?clock(result.eventStart):"기록 없음"}{result.eventEnd&&result.eventEnd!==result.eventStart?" ~ "+clock(result.eventEnd):""}
            · 모델 처리 {clock(result.processedAt)}{result.replay?" · 저장 기록":""}</p>
          {#if measurements&&binding.stepKind==="acquisition-snapshot"}
            {@const links=measurementLinks(assetId,result.position,{...measurements,bindingId:binding.bindingId},"model")}
            {#if links.length}<p class="continue">같은 측정으로 이어서 보기
              {#each links.filter(item=>item.key!=="features") as item(item.key)}<a href={item.href}>{item.label} →</a>{/each}</p>{/if}
          {/if}</div>

          {#if result.state!=="skipped"}{@const summary=scoreSummary(result.output)}
            <details><summary>점수·판정 상세</summary>
          <p class="context">{selectedScoreMessage(summary).meaning}</p>
          <div class="score" role="group" aria-label={place(result.position)+" 모델 결과"} data-model-position={result.position} data-model-event-start={result.eventStart ?? ""}>
            <div><span>모델 점수</span><strong>{num(summary.score,"기록 없음")}</strong></div>
            <div><span>모델 기준</span><strong>{num(summary.threshold,"기록 없음")}</strong></div>
            <div><span>기준 대비</span><strong>{summary.exceeds===null?"판단 정보 없음":summary.exceeds?"기준 초과":"기준 이하"}</strong></div>
          </div>
          </details>
          {/if}
          <details id="selected-model-input" tabindex="-1" open={location.hash==="#selected-model-input"}><summary>선택 측정의 원본 데이터</summary>
            {#key result.runId}<ModelInput {binding} position={result.position} {place}/>{/key}
          </details>
          <details>
            <summary>기술 상세</summary>
            <dl>
              <div><dt>적용 모델(binding)</dt><dd>{binding.bindingId}</dd></div>
              <div><dt>모델 레시피</dt><dd>{binding.recipeId??"확인 불가"}</dd></div>
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
          </div></TaskDialog>
        {/if}
        {#if result}
          {#if result.state!=="skipped"}
            {#key result.runId}
              <details class="optional-review" ontoggle={event=>explanationRun=event.currentTarget.open ? result?.runId ?? null : null}>
                <summary>이 구간의 측정 비교·AI 해설</summary>
                {#if explanationRun === result.runId}<ModelExplanation {binding} run={result} {earlier} {suggested} {writable} {place}
                  onInteract={()=>followLatest=false} onExplained={id=>explanationId=id}/>{/if}
              </details>
              <details id="model-review" bind:this={reviewPanel} class="optional-review" open={location.hash==="#model-review"} ontoggle={(event)=>reviewRun=event.currentTarget.open && result ? result.runId : null}><summary>검토 기록에 남기기 (선택)</summary>
                {#if reviewRun === result.runId}<ModelReviewRequest {binding} run={result} {explanationId} {writable}
                  subject={reviewSubject(binding, result)}/>{/if}
              </details>
            {/key}
          {/if}
        {/if}
      </div>
      {/if}</div>
    {/if}
    <ModelConnect {assetId} {writable} hasModel={true} onConnected={connected}/>
      <ModelBuild {assetId} {writable} hasModel={true} onBuilt={connected}/>
  {/if}
</section>
<style>
  .model-toolbar{grid-column:1/-1;grid-row:1;display:flex;flex-wrap:wrap;align-items:center;gap:var(--space-3)}
  .model-toolbar :global(.analysis-controls){flex:none;margin:0;margin-left:auto}
  .model-choice{display:flex;align-items:center;flex-wrap:wrap;gap:var(--space-2);font-size:var(--font-small)}.model-choice select{width:auto;min-width:160px}
  .model-workspace{grid-template-columns:minmax(0,1fr);gap:var(--space-3)}
  .model-comparison-area{min-width:0;border-top:1px solid var(--color-border);padding-top:var(--space-3);display:grid;gap:var(--space-2)}
  .measurement-picker{display:flex;align-items:end;flex-wrap:wrap;gap:var(--space-2)}
  .step-actions{display:flex;flex-wrap:wrap;gap:var(--space-1)}
  .input-details{justify-self:start}
  .selected-result{display:flex;align-items:baseline;flex-wrap:wrap;gap:var(--space-2) var(--space-4)}
  .selected-result h3{margin:0;font-size:1.2rem}
  .selected-meta{display:flex;flex-wrap:wrap;align-items:baseline;gap:var(--space-1) var(--space-5)}
  .selected-meta p{margin:0}
  .selected-more{display:flex;flex-wrap:wrap;align-items:start;gap:0 var(--space-5)}
  .selected-more>details[open]{flex-basis:100%}
  .context{color:var(--color-ink-muted);overflow-wrap:anywhere}
  .selector{display:flex;align-items:center;gap:var(--space-2);flex-wrap:wrap;font-size:var(--font-small);font-weight:650}
  .selector select{width:auto;max-width:100%}
  select{width:100%;min-width:0;border:1px solid var(--color-border);
    border-radius:var(--radius-control);padding:var(--space-3);
    background:var(--color-surface);color:var(--color-ink)}
  .score{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:var(--space-3);margin-block:var(--space-4)}
  .score div{border:1px solid var(--color-border);border-radius:var(--radius-control);padding:var(--space-4);display:grid;gap:var(--space-1)}
  .score span{font-size:var(--font-small);color:var(--color-ink-muted)}
  .score strong{font-size:var(--font-section)}
  summary{cursor:pointer;font-weight:650;padding-block:var(--space-2);color:var(--color-action)}
  dl{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:var(--space-3)}
  dt{font-size:var(--font-small);color:var(--color-ink-muted)}
  dd{margin:0;font-weight:650;overflow-wrap:anywhere}
  pre{max-width:100%;overflow:auto;padding:var(--space-3);
    background:var(--color-surface-secondary,var(--color-surface));border:1px solid var(--color-border);
    border-radius:var(--radius-panel);white-space:pre-wrap;overflow-wrap:anywhere}
  .continue{display:flex;flex-wrap:wrap;gap:var(--space-2) var(--space-4);align-items:baseline;color:var(--color-ink-muted);font-size:var(--font-small)}
</style>
