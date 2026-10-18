<script lang="ts">
  import {onMount} from "svelte";
  import StatusNotice from "./StatusNotice.svelte";
  import {num} from "../format";
  import CautionNote from "./CautionNote.svelte";
  import {strength} from "../relation";
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
  const count=(n:number|null)=>n===null?"계산 안 됨":n.toFixed(3);

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
  <h2 id="acq-relation-title">진동 특징 관계</h2>
  <p class="context">같은 진동 측정에서 뽑은 두 특징값이 같이 움직이는지 봅니다. 같은 측정끼리만 짝짓습니다.</p>
  {#if sourceState==="loading"}
    <StatusNotice message="진동 특징 목록을 불러오고 있습니다."/>
  {:else if sourceState==="failed"}
    <StatusNotice kind="failure" title="진동 특징 목록을 불러오지 못했습니다" message={error}
      actionLabel="다시 불러오기" onAction={()=>void load()}/>
  {:else if sourceState==="empty"||sourceState==="unavailable"}
    <StatusNotice kind="uncertain" title="비교할 진동 특징이 부족합니다"
      message={error||"같은 적용 모델에서 나온 서로 다른 특징이 두 개 이상 필요합니다. 이상이 없다는 뜻은 아닙니다."}/>
  {:else if source && spans}
    <p class="context">데이터 출처 <strong>{source.sourceId}</strong>
      · 측정 #{source.first} ~ #{source.last}</p>
    <details class="tech"><summary>기술 상세</summary><p class="context">적용 모델 연결 {source.bindingId}</p></details>
    <div class="controls">
      <label>특징 X
        <select value={x} onchange={e=>feature("x",e.currentTarget.value)}>
          {#each source.features as item(item.id)}<option value={item.id}>{item.label} · {item.id}</option>{/each}
        </select>
      </label>
      <label>특징 Y
        <select value={y} onchange={e=>feature("y",e.currentTarget.value)}>
          {#each source.features as item(item.id)}<option value={item.id}>{item.label} · {item.id}</option>{/each}
        </select>
      </label>
    </div>
    <div class="controls">
      {#each ["a","b"] as name(name)}
        {@const period=name as "a"|"b"}
        <fieldset>
          <legend>기간 {period.toUpperCase()} · 측정 순서</legend>
          <label>처음 측정 # <input type="number" step="1" min={source.first} max={source.last}
            value={spans[period].from} onchange={e=>changeSpan(period,"from",e.currentTarget.value)}/></label>
          <label>마지막 측정 # <input type="number" step="1" min={source.first} max={source.last}
            value={spans[period].to} onchange={e=>changeSpan(period,"to",e.currentTarget.value)}/></label>
        </fieldset>
      {/each}
    </div>
    <button type="button" class="ui-button ui-button-primary" onclick={()=>void compare()}>
      관계 계산하기
    </button>
    {#if resultState==="loading"}
      <StatusNotice message="같은 측정의 특징 짝을 불러오고 있습니다."/>
    {:else if resultState==="failed"}
      <StatusNotice kind="failure" title="진동 특징 관계를 불러오지 못했습니다" message={error}
        actionLabel="같은 조건으로 다시 불러오기" onAction={()=>void compare()}/>
    {:else if resultState==="unavailable"}
      <StatusNotice kind="uncertain" title="고른 측정에 분석된 특징이 없습니다" message={error}/>
    {:else if relation}
      {#each relation.groups as group(group.period)}
        <section class="group">
          <h3>기간 {group.period.toUpperCase()} · 측정 #{spans[group.period].from}–#{spans[group.period].to}</h3>
          {#if group.pearson!==null}<p class="headline">{strength(group.pearson)}</p>{/if}
          <dl>
            <div><dt>분석한 측정</dt><dd>{group.analyzed}회</dd></div>
            <div><dt>쓸 수 있는 특징 짝</dt><dd>{group.pairs}개</dd></div>
            <div><dt>피어슨</dt><dd>{count(group.pearson)}</dd></div>
            <div><dt>스피어먼</dt><dd>{count(group.spearman)}</dd></div>
          </dl>
          {#if group.sampled||group.points.length<group.pairs}
            <StatusNotice kind="uncertain"
              message={"짝이 많아 계산이나 그래프에 일부만 사용했습니다. 분석한 측정은 전체 "+group.analyzed+"회, 쓸 수 있는 짝은 "+group.pairs+"개입니다."}/>
          {/if}
          {#if group.pairs<3||group.pearson===null||group.spearman===null}
            <StatusNotice kind="uncertain"
              message="짝이 부족하거나 값이 변하지 않아 관계를 계산할 수 없습니다. 관계가 없다는 뜻은 아닙니다."/>
          {/if}
          {#if group.points.length}
            <svg viewBox="0 0 320 180" role="img"
              aria-label={"기간 "+group.period.toUpperCase()+"의 같은 측정 특징 짝 "+group.points.length+"개 산점도. 가로축은 시간이 아닙니다."}>
              <path d="M24 16 V156 H304" fill="none" stroke="currentColor" stroke-width="1"/>
              {#each scatter(group) as point(point.ordinal)}
                <circle cx={point.x} cy={point.y} r="3.5" fill="var(--color-action)">
                  <title>측정 #{point.ordinal} · {x} / {y}</title>
                </circle>
              {/each}
            </svg>
          {/if}
          <details>
            <summary>같은 측정의 특징 짝 표 ({group.points.length}개 표시)</summary>
            <div class="table-scroll"><table>
              <caption>측정별 특징 짝 (일부만 표시될 수 있음)</caption>
              <thead><tr><th scope="col">측정 순서</th><th scope="col">{x}</th><th scope="col">{y}</th></tr></thead>
              <tbody>
                {#each group.points.slice(0,100) as point(point.ordinal)}
                  <tr><td>#{point.ordinal}</td><td>{num(point.x)}</td><td>{num(point.y)}</td></tr>
                {/each}
              </tbody>
            </table></div>
            {#if group.points.length>100}<p class="context">표에는 앞의 100개만 표시합니다.</p>{/if}
          </details>
        </section>
      {/each}
      <CautionNote message="두 특징이 함께 움직여도 원인 관계나 고장을 뜻하지 않습니다. 측정 순서는 실제 시각이 아닙니다."/>
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
  .headline{font-size:var(--font-section);font-weight:700}
</style>
