<script lang="ts">
  import {onMount} from "svelte";
  import StatusNotice from "./StatusNotice.svelte";
  import {defaultSpans,validateSpans,type Spans} from "../spectrum";
  import {
    FeatureEvidenceUnavailable,loadFeatureSource,loadFeatureProfile,
    type FeatureSource,type FeatureProfile,
  } from "../acquisition-profile";

  let {assetId}:{assetId:string}=$props();
  type State="loading"|"ready"|"empty"|"unavailable"|"failed";
  let listState:State=$state("loading");
  let profileState:State=$state("empty");
  let source:FeatureSource|null=$state(null);
  let profile:FeatureProfile|null=$state(null);
  let spans:Spans|null=$state(null);
  let message=$state("");
  const url=new URLSearchParams(location.search);
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
        if(candidate[key].from<src.first||candidate[key].to>src.last)return defaults;
      return candidate;
    }catch{return defaults;}
  }
  function remember(){
    if(!spans)return;
    const u=new URL(location.href);
    u.searchParams.set("monitor_asset",assetId);
    u.searchParams.set("acquisition_feature",selected);
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
      source=response;
      if(!response.features.some(x=>x.id===selected))selected=response.features[0].id;
      try{spans=savedSpans(defaultSpans(response),response);}
      catch(cause:unknown){
        listState="unavailable";
        message=cause instanceof Error?cause.message:"비교할 획득 회차가 부족합니다.";
        return;
      }
      listState="ready";remember();await compare();
    }catch(cause:unknown){
      if(request.signal.aborted)return;
      listState=cause instanceof FeatureEvidenceUnavailable?"unavailable":"failed";
      message=cause instanceof Error?cause.message:"획득 특징 목록 조회 실패";
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
    profileAbort?.abort();profile=null;profileState="empty";
  }
  async function compare(){
    profileAbort?.abort();
    const request=new AbortController();profileAbort=request;
    profile=null;profileState="loading";message="";
    try{
      if(!source||!spans)throw new Error("획득 원본과 회차 범위를 확인하세요.");
      validateSpans(spans);
      for(const key of ["a","b"] as const)
        if(spans[key].from<source.first||spans[key].to>source.last)
          throw new Error("서버가 알려준 전체 획득 회차 안에서 범위를 선택하세요.");
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
  const label=(value:number|null)=>value===null?"미산출":String(value);
</script>

<section class="ui-panel acquisition" aria-labelledby="feature-title">
  <h2 id="feature-title">획득 회차의 특징값 A/B 비교</h2>
  <p class="context">선택 설비 <strong>{assetId}</strong> · 서버가 저장한 획득 특징을 비교합니다.
    회차(ordinal)는 일정한 시간 간격이 아니며, 특징값 변화는 결함이나 잔여수명 판단이 아닙니다.</p>

  {#if listState==="loading"}
    <StatusNotice message="획득 특징과 저장 회차를 확인하고 있습니다." />
  {:else if listState==="failed"}
    <StatusNotice kind="failure" title="특징 목록 조회 실패" message={message}
      actionLabel="다시 조회" onAction={()=>void loadSource()} />
  {:else if listState==="empty" || listState==="unavailable"}
    <StatusNotice kind="uncertain" title="비교할 획득 특징이 없습니다"
      message={message||"현재 서버 응답에 저장된 특징 또는 비교 가능한 획득 회차가 없습니다. 정상이라는 뜻이 아닙니다."}
      actionLabel="기존 운영 데이터 연결 확인" actionHref="/web/#connect" />
  {:else if source && spans}
    <p class="context">원본 출처 <strong>{source.sourceId}</strong> · binding {source.bindingId}
      · 저장 분석 회차 {source.first} ~ {source.last} · 기록 {source.count}건</p>
    <label for="acquisition-feature">비교할 획득 특징
      <select id="acquisition-feature" value={selected} onchange={e=>selectFeature(e.currentTarget.value)}>
        {#each source.features as item(item.id)}
          <option value={item.id}>{item.label} · {item.id}</option>
        {/each}
      </select>
    </label>
    <div class="ranges">
      {#each ["a","b"] as key(key)}
        {@const name=key as "a"|"b"}
        <fieldset><legend>구간 {name.toUpperCase()} · 획득 회차</legend>
          <label>시작 회차
            <input type="number" step="1" min={source.first} max={source.last}
              value={spans[name].from} onchange={e=>editSpan(name,"from",e.currentTarget.value)}/>
          </label>
          <label>끝 회차
            <input type="number" step="1" min={source.first} max={source.last}
              value={spans[name].to} onchange={e=>editSpan(name,"to",e.currentTarget.value)}/>
          </label>
        </fieldset>
      {/each}
    </div>
    <button type="button" class="ui-button ui-button-primary" onclick={()=>void compare()}>
      특징값 분포와 분석 누락 비교
    </button>

    {#if profileState==="loading"}
      <StatusNotice message="서버에 저장된 획득 회차별 특징 통계를 조회합니다." />
    {:else if profileState==="failed"}
      <StatusNotice kind="failure" title="획득 특징 비교 실패" message={message}
        actionLabel="같은 조건 재조회" onAction={()=>void compare()} />
    {:else if profileState==="unavailable"}
      <StatusNotice kind="uncertain" title="선택 회차의 특징 근거 없음" message={message} />
    {:else if profile}
      <section class="evidence">
        <h3>{profile.label} · {profile.featureId}</h3>
        <p class="context">출처 {profile.sourceId} / binding {profile.bindingId} · 기간 A:
          {profile.spans.a.from}~{profile.spans.a.to}회 · 기간 B:
          {profile.spans.b.from}~{profile.spans.b.to}회</p>
        <p class="context">전 구간 수신·분석/미분석·결측 획득 회차 수는 서버 집계입니다.
          특징 평균·분위수는 조회된 유효 분석 회차에 한해 계산합니다.</p>
        <div class="table-scroll"><table>
          <caption>같은 저장 특징값에 대한 서버 통계 (서로 다른 회차 구간, 날짜 단위 아님)</caption>
          <thead><tr><th scope="col">판단 근거</th><th scope="col">구간 A</th><th scope="col">구간 B</th></tr></thead>
          <tbody>
            <tr><th scope="row">수신 회차</th><td>{profile.a.delivered}</td><td>{profile.b.delivered}</td></tr>
            <tr><th scope="row">분석 완료 회차</th><td>{profile.a.analyzed}</td><td>{profile.b.analyzed}</td></tr>
            <tr><th scope="row">유효 특징 수</th><td>{profile.a.usable}</td><td>{profile.b.usable}</td></tr>
            <tr><th scope="row">미분석 회차</th><td>{profile.a.unanalyzed}</td><td>{profile.b.unanalyzed}</td></tr>
            <tr><th scope="row">중간 누락 회차</th><td>{profile.a.missingAcquisitions}</td><td>{profile.b.missingAcquisitions}</td></tr>
            <tr><th scope="row">특징 중앙값</th><td>{label(profile.a.median)}</td><td>{label(profile.b.median)}</td></tr>
            <tr><th scope="row">특징 평균</th><td>{label(profile.a.mean)}</td><td>{label(profile.b.mean)}</td></tr>
            <tr><th scope="row">특징 집계 샘플링</th>
              <td>{profile.a.sampled?"샘플링됨":"전체 사용"}</td>
              <td>{profile.b.sampled?"샘플링됨":"전체 사용"}</td>
            </tr>
          </tbody>
        </table></div>
        {#if profile.a.sampled||profile.b.sampled}
          <StatusNotice kind="uncertain" message="전체 회차의 상태·건수와 달리 특징 통계는 분포를 대표하도록 제한된 표본으로 계산됐습니다. 전체 기록의 정확한 분포라고 단정하지 마세요." />
        {/if}
        {#if profile.medianChange===null}
          <StatusNotice kind="uncertain" message="양쪽 구간의 특징 중앙값을 비교할 근거가 부족합니다. 변화를 0으로 바꾸지 않습니다." />
        {:else}
          <p class="context">중앙값 변화 (B−A): <strong>{profile.medianChange}</strong>
            {#if profile.outsidePercent!==null}
              · B에서 A의 10~90% 분위수 밖 특징: {profile.outsidePercent.toFixed(1)}%
            {/if}
          </p>
        {/if}
      </section>
    {/if}
  {/if}
</section>
<style>
  .acquisition{min-width:0}.context{color:var(--color-ink-muted);overflow-wrap:anywhere}
  .ranges{display:grid;gap:var(--space-4);grid-template-columns:repeat(auto-fit,minmax(180px,1fr));margin-block:var(--space-4)}
  label{display:grid;gap:var(--space-2);font-weight:650}
  input,select{min-width:0;width:100%;border:1px solid var(--color-border);border-radius:var(--radius-control);
    background:var(--color-surface);color:var(--color-ink);padding:var(--space-3)}
  fieldset{min-width:0;display:grid;gap:var(--space-3);border:1px solid var(--color-border);border-radius:var(--radius-panel)}
  .evidence{margin-top:var(--space-6);border-top:1px solid var(--color-border);padding-top:var(--space-4)}
  h3{overflow-wrap:anywhere}.table-scroll{overflow-x:auto}table{width:100%;border-collapse:collapse}
  caption{text-align:left;color:var(--color-ink-muted);font-size:var(--font-small)}
  th,td{padding:var(--space-2);border-bottom:1px solid var(--color-border);text-align:left}
</style>
