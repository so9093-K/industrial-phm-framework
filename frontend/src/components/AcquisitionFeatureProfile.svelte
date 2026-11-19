<script lang="ts">
  import AnalysisControls from "./AnalysisControls.svelte";
  import {readableSourceId} from "../operations-status";
  import AcquisitionRange from "./AcquisitionRange.svelte";
  import AcquisitionPeriodTrend from "./AcquisitionPeriodTrend.svelte";
  import type {AcquisitionTiming} from "../asset-data";
  import {measurementLabel} from "../time-axis";
  import RangeCompare from "./RangeCompare.svelte";
  import {systemUrl} from "../routes";
  import {onMount} from "svelte";
  import StatusNotice from "./StatusNotice.svelte";
  import {num} from "../format";
  import {defaultSpans,validateSpans,type Spans} from "../spectrum";
  import {readVibrationSummary,vibrationDefault} from "../summary-defaults";
  import {plainLabel,versusStart} from "../change-story";
  import {rangeEvidence} from "../change-evidence";
  import {
    FeatureEvidenceUnavailable,loadFeatureSource,loadFeatureProfile,preferredFeature,
    type FeatureSource,type FeatureProfile,
  } from "../acquisition-profile";

  let {assetId,timing=null}:{assetId:string;timing?:AcquisitionTiming|null}=$props();
  type State="loading"|"ready"|"empty"|"unavailable"|"failed";
  let listState:State=$state("loading");
  let profileState:State=$state("empty");
  let source:FeatureSource|null=$state(null);
  let profile:FeatureProfile|null=$state(null);
  let spans:Spans|null=$state(null);
  const period = $derived.by(() => {
    const current: FeatureSource | null = source;
    return current && timing && timing.sourceId === current.sourceId ? timing.periodSeconds : null;
  });
  const place = (at:number) => measurementLabel(at, period);
  let message=$state("");
  const url=new URLSearchParams(location.search);
  // 두 기간이 모니터링 화면의 '초기'·'변화 구간'과 같은지. 기간을 고치면 꺼지고, 특징만 바꾸면 유지된다.
  let fromSummary=$state(url.get("compare_origin")==="summary");
  let selected=$state(url.get("acquisition_feature")??"");
  let listAbort:AbortController|null=null;
  let profileAbort:AbortController|null=null;

  function savedSpans(defaults:Spans,src:FeatureSource):Spans {
    const span=(key:"a"|"b")=>({
      from:Number(url.get("feature_"+key+"_from")),
      to:Number(url.get("feature_"+key+"_to")),
    });
    if(!["feature_a_from","feature_a_to","feature_b_from","feature_b_to"].every(k=>url.has(k)))
      return defaults;
    try{
      const candidate={a:span("a"),b:span("b")};
      validateSpans(candidate);
      for(const key of ["a","b"] as const)
        if(candidate[key].from<src.first||candidate[key].to>src.last)throw new Error("고른 측정 구간이 현재 데이터 범위를 벗어났습니다.");
      return candidate;
    }catch{throw new Error("고른 측정 구간을 확인하지 못했습니다.");}
  }
  function remember(){
    if(!spans)return;
    const u=new URL(location.href);
    u.searchParams.set("monitor_asset",assetId);
    u.searchParams.set("acquisition_feature",selected);
    if(fromSummary)u.searchParams.set("compare_origin","summary");else u.searchParams.delete("compare_origin");
    for(const key of ["a","b"] as const){
      u.searchParams.set("feature_"+key+"_from",String(spans[key].from));
      u.searchParams.set("feature_"+key+"_to",String(spans[key].to));
    }
    history.replaceState(history.state,"",u);
  }
  async function loadSource(){
    listAbort?.abort();profileAbort?.abort();
    const request=new AbortController();listAbort=request;
    listState="loading";profileState="empty";source=null;profile=null;spans=null;message="";
    try{
      const response=await loadFeatureSource(assetId,request.signal);
      if(request.signal.aborted)return;
      if(!response||!response.features.length){listState="empty";return;}
      if(url.has("acquisition_source")&&url.get("acquisition_source")!==response.sourceId)
        throw new Error("고른 측정 기록이 현재 비교할 수 있는 기록과 다릅니다.");
      if(url.has("acquisition_binding")&&url.get("acquisition_binding")!==response.bindingId)
        throw new Error("넘겨받은 모델과 탐색 데이터의 적용 모델이 달라 비교하지 않았습니다.");
      source=response;
      if(selected&&!response.features.some(x=>x.id===selected))throw new Error("고른 특징이 이 데이터 출처에 없습니다.");
      // 아무것도 고르지 않고 열었으면 상태 요약의 대표 변화와 같은 특징·기간으로 시작한다.
      const chosen=["feature_a_from","feature_a_to","feature_b_from","feature_b_to"].some(k=>url.has(k));
      const found=!selected&&!chosen?await readVibrationSummary(assetId,request.signal):null;
      if(request.signal.aborted)return;
      const summary=found?vibrationDefault(found,response.bindingId,response.features.map(x=>x.id)):null;
      if(summary){selected=summary.feature;fromSummary=true;}
      if(!selected)selected=preferredFeature(response.features)!.id;
      try{
        const bounds={source:response.sourceId,binding:response.bindingId,
          first:response.first,last:response.last,count:response.count};
        spans=summary?summary.spans:savedSpans(defaultSpans(bounds),response);
      }
      catch(cause:unknown){
        listState="unavailable";
        message=cause instanceof Error?cause.message:"비교할 측정 회차가 부족합니다.";
        return;
      }
      listState="ready";remember();await compare();
    }catch(cause:unknown){
      if(request.signal.aborted)return;
      listState=cause instanceof FeatureEvidenceUnavailable?"unavailable":"failed";
      message=cause instanceof Error?cause.message:"측정 특징 목록 조회 실패";
    }
  }
  function selectFeature(value:string){
    if(!source?.features.some(x=>x.id===value))return;
    selected=value;profileAbort?.abort();profile=null;profileState="empty";remember();
    void compare();
  }
  function editSpan(period:"a"|"b",edge:"from"|"to",value:string){
    if(!spans)return;
    spans={...spans,[period]:{...spans[period],[edge]:value===""?NaN:Number(value)}};
    fromSummary=false;profileAbort?.abort();profile=null;profileState="empty";
  }
  async function compare(){
    profileAbort?.abort();
    const request=new AbortController();profileAbort=request;
    profile=null;profileState="loading";message="";
    try{
      if(!source||!spans)throw new Error("측정 원본과 회차 범위를 확인하세요.");
      validateSpans(spans);
      for(const key of ["a","b"] as const)
        if(spans[key].from<source.first||spans[key].to>source.last)
          throw new Error("서버가 알려준 전체 측정 회차 안에서 범위를 선택하세요.");
      const expected:Spans={a:{...spans.a},b:{...spans.b}};
      const response=await loadFeatureProfile(assetId,source,selected,expected,request.signal);
      if(request.signal.aborted)return;
      profile=response;profileState="ready";remember();
    }catch(cause:unknown){
      if(request.signal.aborted)return;
      profileState=cause instanceof FeatureEvidenceUnavailable?"unavailable":"failed";
      message=cause instanceof Error?cause.message:"회차 특징 비교 결과 조회 오류";
    }
  }
  onMount(()=>{void loadSource();return()=>{listAbort?.abort();profileAbort?.abort();};});
  const label=(value:number|null)=>num(value);
  // 모니터링에서 같은 변화로 열었으면 중심 화면과 같은 이름을 쓴다. 기간을 직접 고치면 A·B로 돌아간다.
  const names=$derived(fromSummary?{a:"초기",b:"변화 구간"}:{a:"기간 A",b:"기간 B"});
  // 기간 A 값의 90% 범위(5~95%): 시간 추이에 띠로 그리고, 그 밖의 B 측정 수를 한 줄로 쓴다.
  const usual=$derived.by(()=>{
    const read:FeatureProfile|null=profile,q=read?.a.quantiles;
    return q&&q.length===5?{low:q[0],high:q[4]}:null;
  });
  const facts=$derived.by(()=>{
    const read:FeatureProfile|null=profile;
    if(!read)return null;
    const versus=read.a.median!==null&&read.b.median!==null?versusStart(read.b.median,read.a.median,read.unit??null,names.a):null;
    const outside=rangeEvidence({usable:read.b.usable,outside:read.outsideCount,low:usual?.low??null,high:usual?.high??null,
      unit:read.unit??null,condition:null},names);
    return {versus,outside};
  });
</script>

<section class="ui-panel acquisition" aria-labelledby="feature-title">
  <h2 class="visually-hidden" id="feature-title">진동 특징 두 기간 비교</h2>

  {#if listState==="loading"}
    <StatusNotice message="진동 특징과 저장된 측정을 불러오고 있습니다." />
  {:else if listState==="failed"}
    <StatusNotice kind="failure" title="진동 특징 목록을 불러오지 못했습니다" message={message}
      actionLabel="다시 불러오기" onAction={()=>void loadSource()} />
  {:else if listState==="empty" || listState==="unavailable"}
    <StatusNotice kind="uncertain" title="비교할 진동 특징이 없습니다"
      message={message||"이 설비에는 분석된 진동 측정이 없습니다."}
      actionLabel="데이터 연결 확인하기" actionHref={systemUrl("connections")} />
  {:else if source && spans}
    <div class="analysis-workspace analysis-full"><AnalysisControls title="특징·비교 기간" summary={profile?names.a+" · "+profile.spans.a.from+"–"+profile.spans.a.to+"번째 측정 / "+names.b+" · "+profile.spans.b.from+"–"+profile.spans.b.to+"번째 측정":null}>{#snippet children(close)}{#if source && spans}
    <p class="purpose">진동 측정에서 뽑은 특징값(예: RMS)을 두 기간 A·B로 나누어 비교합니다. 측정 간격이 있으면 경과 시간으로 표시합니다.</p>
    <p class="context">데이터 출처 <strong>{readableSourceId(source.sourceId)}</strong>
      · {place(source.first)} ~ {place(source.last)} · {source.count}회</p>
    <label for="acquisition-feature">진동 특징
      <select id="acquisition-feature" value={selected} onchange={e=>{close();selectFeature(e.currentTarget.value);}}>
        {#each source.features as item(item.id)}
          <option value={item.id}>{item.label}</option>
        {/each}
      </select>
    </label>
    <div class="ranges">
      {#each ["a","b"] as key(key)}
        {@const name=key as "a"|"b"}
        <AcquisitionRange name={name} span={spans[name]} first={source.first} last={source.last} {period}
          onChange={(edge, ordinal) => editSpan(name, edge, String(ordinal))} />
      {/each}
    </div>
    <button type="button" class="ui-button ui-button-primary" onclick={()=>{close();void compare();}}>
      비교하기
    </button>
    {/if}{/snippet}</AnalysisControls>
    <div class="analysis-body">
    {#if profileState==="loading"}
      <StatusNotice message="두 기간의 진동 특징을 불러오고 있습니다." />
    {:else if profileState==="failed"}
      <StatusNotice kind="failure" title="진동 특징 비교를 불러오지 못했습니다" message={message}
        actionLabel="같은 조건으로 다시 불러오기" onAction={()=>void compare()} />
    {:else if profileState==="unavailable"}
      <StatusNotice kind="uncertain" title="고른 측정에 분석된 특징이 없습니다" message={message} />
    {:else if profile}
      <section class="evidence">
        <h3>{plainLabel(profile.label,profile.featureId)}</h3>
        <p class="comparison-value">{label(profile.a.median)} <span>→</span> {label(profile.b.median)}{profile.unit?" "+profile.unit:""}<small>중앙값{facts?.versus?" · "+facts.versus:""}</small></p>
        {#if facts?.outside}<p class="comparison-fact">{facts.outside}</p>{/if}
        <div class="comparison-plots"><div>
        <AcquisitionPeriodTrend {source} feature={profile.featureId} spans={profile.spans} {names} {usual}/>
        </div><div>
        <h3>값 분포</h3>
        {#if profile.medianChange===null}
          <StatusNotice kind="uncertain" message="두 기간의 중앙값을 비교할 특징값이 부족합니다. 0으로 채우지 않습니다." />
        {/if}
        <RangeCompare a={profile.a.quantiles} b={profile.b.quantiles} histogram={profile.histogram??null} unit={profile.unit??null} label={profile.label} {names} />
        </div></div>
        <details><summary>기간별 측정 수와 통계</summary><div class="table-scroll"><table>
          <caption>선택한 두 구간의 집계 · 경과 시간은 실제 측정 시각이 아닙니다</caption>
          <thead><tr><th scope="col">항목</th><th scope="col">{names.a}</th><th scope="col">{names.b}</th></tr></thead>
          <tbody>
            <tr><th scope="row">받은 측정</th><td>{profile.a.delivered}</td><td>{profile.b.delivered}</td></tr>
            <tr><th scope="row">분석한 측정</th><td>{profile.a.analyzed}</td><td>{profile.b.analyzed}</td></tr>
            <tr><th scope="row">쓸 수 있는 특징값</th><td>{profile.a.usable}</td><td>{profile.b.usable}</td></tr>
            <tr><th scope="row">분석하지 않은 측정</th><td>{profile.a.unanalyzed}</td><td>{profile.b.unanalyzed}</td></tr>
            <tr><th scope="row">중간에 빠진 측정</th><td>{profile.a.missingAcquisitions}</td><td>{profile.b.missingAcquisitions}</td></tr>
            <tr><th scope="row">특징 중앙값</th><td>{label(profile.a.median)}</td><td>{label(profile.b.median)}</td></tr>
            <tr><th scope="row">특징 평균</th><td>{label(profile.a.mean)}</td><td>{label(profile.b.mean)}</td></tr>
            <tr><th scope="row">특징 집계</th>
              <td>{profile.a.sampled?"일부만 사용":"전체 사용"}</td>
              <td>{profile.b.sampled?"일부만 사용":"전체 사용"}</td>
            </tr>
          </tbody>
        </table></div></details>
        {#if profile.a.sampled||profile.b.sampled}
          <StatusNotice kind="uncertain" message="측정이 많아 특징 통계는 일부 측정만 골라 계산했습니다. 측정 건수는 전체 기준입니다." />
        {/if}
        <details>
          <summary>기술 상세</summary>
          <p class="context">데이터 출처 {profile.sourceId} · 적용 모델 연결 {profile.bindingId} · 특징 {profile.featureId}
            · ‘90% 범위’는 {names.a} 값의 5~95% 범위입니다. {names.a} 값도 약 10%는 이 범위 밖에 있고, {names.a}가 정상 운전이었다는 뜻은 아닙니다.</p>
        </details>
      </section>
    {:else}
      <p class="context">두 기간을 고르고 비교하기를 누르면 결과를 표시합니다.</p>
    {/if}
    </div></div>
  {/if}
</section>
<style>
  .comparison-plots{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--space-6);align-items:start;margin-block:var(--space-3)}
  .comparison-plots>div{min-width:0}
  .comparison-value{font-size:var(--font-result);font-weight:700;margin:var(--space-3) 0 var(--space-1);font-variant-numeric:tabular-nums}.comparison-value span{color:var(--color-ink-muted);font-weight:400}.comparison-value small{display:inline-block;margin-left:var(--space-3);font-size:var(--font-small);font-weight:400;color:var(--color-ink-muted)}
  .comparison-fact{margin:0;line-height:1.6}
  @media(max-width:1000px){.comparison-plots{grid-template-columns:minmax(0,1fr)}}
  .acquisition{min-width:0}.context{color:var(--color-ink-muted);overflow-wrap:anywhere}
  .ranges{display:grid;gap:var(--space-3);grid-template-columns:minmax(0,1fr);margin-block:var(--space-3)}
  label{display:grid;gap:var(--space-2);font-weight:650}
  select{min-width:0;width:100%;border:1px solid var(--color-border);border-radius:var(--radius-control);
    background:var(--color-surface);color:var(--color-ink);padding:var(--space-3)}
  .evidence{min-width:0}.evidence>h3:first-child{margin-top:0}
  h3{overflow-wrap:anywhere}.table-scroll{overflow-x:auto}table{width:100%;border-collapse:collapse}
  caption{text-align:left;color:var(--color-ink-muted);font-size:var(--font-small)}
  summary{cursor:pointer;font-weight:650;color:var(--color-action);padding-block:var(--space-2)}
  th,td{padding:var(--space-2);border-bottom:1px solid var(--color-border);text-align:left}
</style>
