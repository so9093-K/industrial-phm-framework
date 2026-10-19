<script lang="ts">
  import RangeCompare from "./RangeCompare.svelte";
  import {systemUrl} from "../routes";
  import {onMount} from "svelte";
  import StatusNotice from "./StatusNotice.svelte";
  import {num} from "../format";
  import CautionNote from "./CautionNote.svelte";
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
        if(candidate[key].from<src.first||candidate[key].to>src.last)throw new Error("고른 측정 구간이 현재 데이터 범위를 벗어났습니다.");
      return candidate;
    }catch{throw new Error("고른 측정 구간을 확인할 수 없어 다른 구간으로 대신하지 않습니다.");}
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
      if(url.has("acquisition_binding")&&url.get("acquisition_binding")!==response.bindingId)
        throw new Error("넘겨받은 모델과 탐색 데이터의 적용 모델이 달라 비교하지 않았습니다.");
      source=response;
      if(selected&&!response.features.some(x=>x.id===selected))throw new Error("고른 특징이 이 데이터 출처에 없습니다.");
      if(!selected)selected=response.features[0].id;
      try{
        const bounds={source:response.sourceId,binding:response.bindingId,
          first:response.first,last:response.last,count:response.count};
        spans=savedSpans(defaultSpans(bounds),response);
      }
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
  const label=(value:number|null)=>num(value);
</script>

<section class="ui-panel acquisition" aria-labelledby="feature-title">
  <h2 id="feature-title">진동 특징 두 기간 비교</h2>
  <p class="context">진동 측정에서 뽑은 특징값(예: RMS)을 측정 순서로 나눈 두 기간 A·B에서 비교합니다.</p>

  {#if listState==="loading"}
    <StatusNotice message="진동 특징과 저장된 측정을 불러오고 있습니다." />
  {:else if listState==="failed"}
    <StatusNotice kind="failure" title="진동 특징 목록을 불러오지 못했습니다" message={message}
      actionLabel="다시 불러오기" onAction={()=>void loadSource()} />
  {:else if listState==="empty" || listState==="unavailable"}
    <StatusNotice kind="uncertain" title="비교할 진동 특징이 없습니다"
      message={message||"이 설비에는 분석된 진동 측정이 없습니다. 이상이 없다는 뜻은 아닙니다."}
      actionLabel="데이터 연결 확인하기" actionHref={systemUrl("connections")} />
  {:else if source && spans}
    <p class="context">데이터 출처 <strong>{source.sourceId}</strong>
      · 분석한 측정 #{source.first} ~ #{source.last} · {source.count}회</p>
    <label for="acquisition-feature">진동 특징
      <select id="acquisition-feature" value={selected} onchange={e=>selectFeature(e.currentTarget.value)}>
        {#each source.features as item(item.id)}
          <option value={item.id}>{item.label}</option>
        {/each}
      </select>
    </label>
    <div class="ranges">
      {#each ["a","b"] as key(key)}
        {@const name=key as "a"|"b"}
        <fieldset><legend>기간 {name.toUpperCase()} · 측정 순서</legend>
          <label>처음 측정 #
            <input type="number" step="1" min={source.first} max={source.last}
              value={spans[name].from} onchange={e=>editSpan(name,"from",e.currentTarget.value)}/>
          </label>
          <label>마지막 측정 #
            <input type="number" step="1" min={source.first} max={source.last}
              value={spans[name].to} onchange={e=>editSpan(name,"to",e.currentTarget.value)}/>
          </label>
        </fieldset>
      {/each}
    </div>
    <button type="button" class="ui-button ui-button-primary" onclick={()=>void compare()}>
      비교하기
    </button>

    {#if profileState==="loading"}
      <StatusNotice message="두 기간의 진동 특징을 불러오고 있습니다." />
    {:else if profileState==="failed"}
      <StatusNotice kind="failure" title="진동 특징 비교를 불러오지 못했습니다" message={message}
        actionLabel="같은 조건으로 다시 불러오기" onAction={()=>void compare()} />
    {:else if profileState==="unavailable"}
      <StatusNotice kind="uncertain" title="고른 측정에 분석된 특징이 없습니다" message={message} />
    {:else if profile}
      <section class="evidence">
        <h3>{profile.label}</h3>
        <p class="context">기간 A 측정 #{profile.spans.a.from}~#{profile.spans.a.to}
          · 기간 B 측정 #{profile.spans.b.from}~#{profile.spans.b.to}</p>
        {#if profile.medianChange===null}
          <StatusNotice kind="uncertain" message="두 기간의 중앙값을 비교할 특징값이 부족합니다. 0으로 채우지 않습니다." />
        {:else}
          <p class="headline">중앙값 변화(B − A) <strong>{num(profile.medianChange)}</strong>
            {#if profile.outsidePercent!==null}
              <span> · B의 값 중 A의 평소 범위 밖 {profile.outsidePercent.toFixed(1)}%</span>
            {/if}
          </p>
        {/if}
        <RangeCompare a={profile.a.quantiles} b={profile.b.quantiles} unit={null} label={profile.label} />
        <div class="table-scroll"><table>
          <caption>측정 순서로 나눈 두 기간의 집계 (날짜가 아닌 측정 순서)</caption>
          <thead><tr><th scope="col">항목</th><th scope="col">기간 A</th><th scope="col">기간 B</th></tr></thead>
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
        </table></div>
        {#if profile.a.sampled||profile.b.sampled}
          <StatusNotice kind="uncertain" message="측정이 많아 특징 통계는 일부 측정만 골라 계산했습니다. 측정 건수는 전체 기준입니다." />
        {/if}
        <CautionNote message="기간 A는 고른 비교 기준이며 정상 상태로 확인된 기간이 아닙니다." />
        <details>
          <summary>기술 상세</summary>
          <p class="context">데이터 출처 {profile.sourceId} · 적용 모델 연결 {profile.bindingId} · 특징 {profile.featureId}
            · ‘평소 범위 밖’은 기간 A의 5~95% 분위수 범위를 벗어난 B 값의 비율입니다.</p>
        </details>
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
  .headline{font-size:var(--font-section)}.headline span{font-size:var(--font-small);color:var(--color-ink-muted)}
  summary{cursor:pointer;font-weight:650;color:var(--color-action);padding-block:var(--space-2)}
  th,td{padding:var(--space-2);border-bottom:1px solid var(--color-border);text-align:left}
</style>
