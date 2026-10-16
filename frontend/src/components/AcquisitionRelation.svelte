<script lang="ts">
  import {onMount} from "svelte";
  import StatusNotice from "./StatusNotice.svelte";
  import {loadFeatureSource,type FeatureSource} from "../acquisition-profile";
  import {defaultSpans,validateSpans,type Spans} from "../spectrum";
  import {
    readAcquisitionRelation,AcquisitionRelationUnavailable,
    type AcquisitionRelation,type AcquisitionPairGroup,
  } from "../acquisition-relation";

  let {assetId}:{assetId:string}=$props();
  type State="loading"|"ready"|"empty"|"unavailable"|"failed";
  let sourceState:State=$state("loading");
  let resultState:State=$state("empty");
  let source:FeatureSource|null=$state(null);
  let relation:AcquisitionRelation|null=$state(null);
  let spans:Spans|null=$state(null);
  let error=$state("");
  const params=new URLSearchParams(location.search);
  let x=$state(params.get("acq_relation_x")??"");
  let y=$state(params.get("acq_relation_y")??"");
  let sourceAbort:AbortController|null=null;
  let relationAbort:AbortController|null=null;
  const count=(n:number|null)=>n===null?"미산출":n.toFixed(3);

  function savedSpans(fallback:Spans,src:FeatureSource):Spans {
    const keys=["acq_a_from","acq_a_to","acq_b_from","acq_b_to"];
    if(!keys.every(k=>params.has(k)))return fallback;
    const data:Spans={
      a:{from:Number(params.get("acq_a_from")),to:Number(params.get("acq_a_to"))},
      b:{from:Number(params.get("acq_b_from")),to:Number(params.get("acq_b_to"))},
    };
    try{
      validateSpans(data);
      for(const period of ["a","b"] as const)
        if(data[period].from<src.first||data[period].to>src.last)return fallback;
      return data;
    }catch{return fallback;}
  }
  function remember(){
    if(!spans)return;
    const url=new URL(location.href);
    url.searchParams.set("monitor_asset",assetId);
    url.searchParams.set("acq_relation_x",x);
    url.searchParams.set("acq_relation_y",y);
    for(const p of ["a","b"] as const){
      url.searchParams.set("acq_"+p+"_from",String(spans[p].from));
      url.searchParams.set("acq_"+p+"_to",String(spans[p].to));
    }
    history.replaceState(history.state,"",url);
  }
  async function load(){
    sourceAbort?.abort();relationAbort?.abort();
    const pending=new AbortController();sourceAbort=pending;
    sourceState="loading";resultState="empty";source=null;relation=null;spans=null;error="";
    try{
      const result=await loadFeatureSource(assetId,pending.signal);
      if(pending.signal.aborted)return;
      if(!result||result.features.length<2){sourceState="empty";return;}
      source=result;
      if(!result.features.some(f=>f.id===x))x=result.features[0].id;
      if(!result.features.some(f=>f.id===y)||y===x)
        y=result.features.find(f=>f.id!==x)!.id;
      try{
        spans=savedSpans(defaultSpans({
          source:result.sourceId,binding:result.bindingId,
          first:result.first,last:result.last,count:result.count,
        }),result);
      }catch(cause:unknown){
        sourceState="unavailable";error=cause instanceof Error?cause.message:"획득 범위가 부족합니다.";return;
      }
      sourceState="ready";remember();await compare();
    }catch(cause:unknown){
      if(pending.signal.aborted)return;
      sourceState="failed";error=cause instanceof Error?cause.message:"특징 목록 조회 실패";
    }
  }
  function feature(which:"x"|"y",value:string){
    if(!source?.features.some(f=>f.id===value))return;
    if(which==="x")x=value;else y=value;
    relationAbort?.abort();relation=null;resultState="empty";remember();
  }
  function changeSpan(period:"a"|"b",edge:"from"|"to",value:string){
    if(!spans)return;
    spans={...spans,[period]:{...spans[period],[edge]:value===""?NaN:Number(value)}};
    relationAbort?.abort();relation=null;resultState="empty";
  }
  async function compare(){
    relationAbort?.abort();
    const pending=new AbortController();relationAbort=pending;
    relation=null;resultState="loading";error="";
    try{
      if(!source||!spans)throw new Error("저장 출처와 획득 회차를 확인하세요.");
      validateSpans(spans);
      const frozen:Spans={a:{...spans.a},b:{...spans.b}};
      const response=await readAcquisitionRelation(assetId,source,x,y,frozen,pending.signal);
      if(pending.signal.aborted)return;
      relation=response;resultState="ready";remember();
    }catch(cause:unknown){
      if(pending.signal.aborted)return;
      error=cause instanceof Error?cause.message:"획득 특징 짝 관계를 확인하지 못했습니다.";
      resultState=cause instanceof AcquisitionRelationUnavailable?"unavailable":"failed";
    }
  }
  function scatter(group:AcquisitionPairGroup):{ordinal:number;x:number;y:number}[]{
    if(!group.points.length)return [];
    const xx=group.points.map(p=>p.x),yy=group.points.map(p=>p.y);
    const xmin=Math.min(...xx),xrange=Math.max(...xx)-xmin;
    const ymin=Math.min(...yy),yrange=Math.max(...yy)-ymin;
    return group.points.map(p=>({
      ordinal:p.ordinal,x:xrange===0?160:24+(p.x-xmin)/xrange*272,
      y:yrange===0?90:156-(p.y-ymin)/yrange*132,
    }));
  }
  onMount(()=>{void load();return()=>{sourceAbort?.abort();relationAbort?.abort();};});
</script>

<section class="ui-panel" aria-labelledby="acq-relation-title">
  <h2 id="acq-relation-title">획득 회차 두 특징 관계 비교</h2>
  <p class="context">같은 설비·출처·모델 입력 binding의 동일 획득 회차에 저장된 두 특징값만 비교합니다.
    획득 번호는 측정 시각이 아니며, 상관관계는 인과관계나 설비 고장 판정이 아닙니다.</p>
  {#if sourceState==="loading"}
    <StatusNotice message="획득 특징과 원본 범위를 조회하고 있습니다."/>
  {:else if sourceState==="failed"}
    <StatusNotice kind="failure" title="획득 관계 자료 조회 실패" message={error}
      actionLabel="목록 다시 조회" onAction={()=>void load()}/>
  {:else if sourceState==="empty"||sourceState==="unavailable"}
    <StatusNotice kind="uncertain" title="관계 분석에 필요한 획득 특징이 부족합니다"
      message={error||"같은 바인딩에 서로 다른 두 특징과 회차 자료가 필요합니다. 정상 설비라는 의미가 아닙니다."}/>
  {:else if source && spans}
    <p class="context">설비 <strong>{assetId}</strong> · 원본 출처 <strong>{source.sourceId}</strong>
      · binding <strong>{source.bindingId}</strong> · 획득 #{source.first} ~ #{source.last}</p>
    <div class="controls">
      <label>X 특징
        <select value={x} onchange={e=>feature("x",e.currentTarget.value)}>
          {#each source.features as item(item.id)}<option value={item.id}>{item.label} · {item.id}</option>{/each}
        </select>
      </label>
      <label>Y 특징
        <select value={y} onchange={e=>feature("y",e.currentTarget.value)}>
          {#each source.features as item(item.id)}<option value={item.id}>{item.label} · {item.id}</option>{/each}
        </select>
      </label>
    </div>
    <div class="controls">
      {#each ["a","b"] as name(name)}
        {@const period=name as "a"|"b"}
        <fieldset>
          <legend>구간 {period.toUpperCase()} · 획득 회차</legend>
          <label>시작 회차 <input type="number" step="1" min={source.first} max={source.last}
            value={spans[period].from} onchange={e=>changeSpan(period,"from",e.currentTarget.value)}/></label>
          <label>끝 회차 <input type="number" step="1" min={source.first} max={source.last}
            value={spans[period].to} onchange={e=>changeSpan(period,"to",e.currentTarget.value)}/></label>
        </fieldset>
      {/each}
    </div>
    <button type="button" class="ui-button ui-button-primary" onclick={()=>void compare()}>
      동일 획득의 특징 짝 비교
    </button>
    {#if resultState==="loading"}
      <StatusNotice message="서버가 계산한 획득 관계 근거를 확인하고 있습니다."/>
    {:else if resultState==="failed"}
      <StatusNotice kind="failure" title="획득 특징 관계 확인 실패" message={error}
        actionLabel="같은 조건 다시 조회" onAction={()=>void compare()}/>
    {:else if resultState==="unavailable"}
      <StatusNotice kind="uncertain" title="저장된 획득 근거 없음" message={error}/>
    {:else if relation}
      {#each relation.groups as group(group.period)}
        <section class="group">
          <h3>구간 {group.period.toUpperCase()} · 획득 회차 {spans[group.period].from}–{spans[group.period].to}</h3>
          <dl>
            <div><dt>분석한 회차</dt><dd>{group.analyzed}건</dd></div>
            <div><dt>유효 특징 짝</dt><dd>{group.pairs}건</dd></div>
            <div><dt>피어슨</dt><dd>{count(group.pearson)}</dd></div>
            <div><dt>스피어먼</dt><dd>{count(group.spearman)}</dd></div>
          </dl>
          {#if group.sampled||group.points.length<group.pairs}
            <StatusNotice kind="uncertain"
              message={"관계 계산 입력 또는 그래프 표시가 일부만 추출됐습니다. 전체 분석 "+group.analyzed+"회차와 유효 짝 "+group.pairs+"개를 혼동하지 마세요."}/>
          {/if}
          {#if group.pairs<3||group.pearson===null||group.spearman===null}
            <StatusNotice kind="uncertain"
              message="자료가 부족하거나 상수 특징으로 관계 계수를 계산할 수 없습니다. 관계 없음(0)으로 표시하지 않습니다."/>
          {/if}
          {#if group.points.length}
            <svg viewBox="0 0 320 180" role="img"
              aria-label={"구간 "+group.period.toUpperCase()+"의 동일 획득 특징 짝 "+group.points.length+"개 산점도. 인과관계나 시간축이 아닙니다."}>
              <path d="M24 16 V156 H304" fill="none" stroke="currentColor" stroke-width="1"/>
              {#each scatter(group) as point(point.ordinal)}
                <circle cx={point.x} cy={point.y} r="3.5" fill="var(--color-action)">
                  <title>획득 #{point.ordinal} · {x} / {y}</title>
                </circle>
              {/each}
            </svg>
          {/if}
          <details>
            <summary>동일 획득 특징 짝 표 ({group.points.length}개 표시)</summary>
            <div class="table-scroll"><table>
              <caption>서버가 반환한 회차별 유효 특징 짝, 선택 표본</caption>
              <thead><tr><th scope="col">획득 회차</th><th scope="col">{x}</th><th scope="col">{y}</th></tr></thead>
              <tbody>
                {#each group.points.slice(0,100) as point(point.ordinal)}
                  <tr><td>#{point.ordinal}</td><td>{point.x}</td><td>{point.y}</td></tr>
                {/each}
              </tbody>
            </table></div>
            {#if group.points.length>100}<p class="context">표에는 앞의 100개만 표시합니다.</p>{/if}
          </details>
        </section>
      {/each}
    {/if}
  {/if}
</section>
<style>
  .context{color:var(--color-ink-muted);overflow-wrap:anywhere}
  .controls{display:grid;gap:var(--space-3);grid-template-columns:repeat(auto-fit,minmax(170px,1fr));margin-block:var(--space-4)}
  label{display:grid;gap:var(--space-2);font-weight:650}
  select,input{min-width:0;width:100%;padding:var(--space-3);border:1px solid var(--color-border);
    color:var(--color-ink);background:var(--color-surface);border-radius:var(--radius-control)}
  fieldset{display:grid;gap:var(--space-2);min-width:0;border:1px solid var(--color-border);border-radius:var(--radius-panel)}
  dl{display:flex;flex-wrap:wrap;gap:var(--space-4)}dt{color:var(--color-ink-muted);font-size:var(--font-small)}
  dd{margin:0;font-weight:650}.group{border-top:1px solid var(--color-border);padding-block:var(--space-4)}
  svg{max-width:100%;height:auto} .table-scroll{overflow-x:auto}
  table{width:100%;border-collapse:collapse}th,td{padding:var(--space-2);text-align:left;border-bottom:1px solid var(--color-border)}
  caption{text-align:left;color:var(--color-ink-muted)}
</style>
