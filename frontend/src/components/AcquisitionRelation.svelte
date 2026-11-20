<script lang="ts">
  import {investigationOriginUrl} from "../routes";
  import {measure} from "../chart-axis";
  import {plainLabel} from "../change-story";
  import AnalysisControls from "./AnalysisControls.svelte";
  import {readableSourceId} from "../operations-status";
  import FeatureScatter from "./FeatureScatter.svelte";
  import AcquisitionRange from "./AcquisitionRange.svelte";
  import type {AcquisitionTiming} from "../asset-data";
  import {measurementLabel} from "../time-axis";
  import {onMount} from "svelte";
  import StatusNotice from "./StatusNotice.svelte";
  import {num} from "../format";
  import CautionNote from "./CautionNote.svelte";
  import {strength} from "../relation";
  import AnalysisMessage from "./AnalysisMessage.svelte";
  import {formulaLink,middle,relationMessage} from "../analysis-messages";
  import {featureCompareHref,measurementLinks} from "../measurement-links";
  import {loadFeatureSource,preferredFeature,type FeatureSource} from "../acquisition-profile";
  import {defaultSpans,validateSpans,type Spans} from "../spectrum";
  import {readVibrationSummary,vibrationDefault,VIBRATION_SUMMARY_NOTE} from "../summary-defaults";
  import {
    readAcquisitionRelation,AcquisitionRelationUnavailable,
    type AcquisitionRelation,
  } from "../acquisition-relation";

  let {assetId,timing=null,selectedPosition=null,onPosition}:{assetId:string;timing?:AcquisitionTiming|null;selectedPosition?:number|null;onPosition?:(at:number)=>void}=$props();
  type State="loading"|"ready"|"empty"|"unavailable"|"failed";
  let sourceState:State=$state("loading");
  let resultState:State=$state("empty");
  let source:FeatureSource|null=$state(null);
  let relation:AcquisitionRelation|null=$state(null);
  let spans:Spans|null=$state(null);
  const period = $derived.by(() => {
    const current: FeatureSource | null = source;
    return current && timing && timing.sourceId === current.sourceId ? timing.periodSeconds : null;
  });
  const place = (at:number) => measurementLabel(at, period);
  let error=$state("");
  const params=new URLSearchParams(location.search);
  let pickedOrdinal=$state<number|null>(Number(params.get("vibration_at"))||null);
  let pickedPeriod=$state<"a"|"b">("b");
  const chosen=$derived.by(()=>{
    const read:AcquisitionRelation|null=relation;if(!read)return null;
    const ordinal=selectedPosition??pickedOrdinal;
    const preferred=read.groups.find(group=>group.period===pickedPeriod);
    const group=(ordinal===null?null:read.groups.find(group=>group===preferred&&group.points.some(point=>point.ordinal===ordinal))
      ??read.groups.find(group=>group.points.some(point=>point.ordinal===ordinal)))??read.groups.find(group=>group.period==="b")??read.groups[0];
    const point=group?.points.find(point=>point.ordinal===ordinal)??group?.points[0];
    return group&&point?{period:group.period,point}:null;
  });
  function pickMeasurement(period:"a"|"b",ordinal:number){
    pickedPeriod=period;pickedOrdinal=ordinal;onPosition?.(ordinal);
    const url=new URL(location.href);url.searchParams.set("vibration_at",String(ordinal));history.replaceState(history.state,"",url);
  }
  let x=$state(params.get("acq_relation_x")??"");
  let y=$state(params.get("acq_relation_y")??"");
  const linked=$derived.by(()=>{const current:FeatureSource|null=source;return current&&chosen?measurementLinks(assetId,chosen.point.ordinal,{first:current.first,last:current.last,feature:x}):[];});
  let fromSummary=$state(false);
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
      // 아무것도 고르지 않고 열었으면 상태 요약의 대표 변화를, 같은 측정에서 함께 달라진 특징과 견준다.
      const chosen=["acq_relation_x","acq_a_from","acq_a_to","acq_b_from","acq_b_to"].some(k=>params.has(k));
      const found=!chosen?await readVibrationSummary(assetId,pending.signal):null;
      if(pending.signal.aborted)return;
      const summary=found?vibrationDefault(found,result.bindingId,result.features.map(f=>f.id)):null;
      if(summary?.related){x=summary.feature;y=summary.related;fromSummary=true;}
      if(!result.features.some(f=>f.id===x))x=preferredFeature(result.features)!.id;
      if(!result.features.some(f=>f.id===y)||y===x)
        y=result.features.find(f=>f.id!==x)!.id;
      try{
        spans=fromSummary&&summary?summary.spans:savedSpans(defaultSpans({
          source:result.sourceId,binding:result.bindingId,
          first:result.first,last:result.last,count:result.count,
        }),result);
      }catch(cause:unknown){
        sourceState="unavailable";error=cause instanceof Error?cause.message:"측정 범위가 부족합니다.";return;
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
    fromSummary=false;
    relationAbort?.abort();relation=null;resultState="empty";remember();
  }
  function changeSpan(period:"a"|"b",edge:"from"|"to",value:string){
    if(!spans)return;
    spans={...spans,[period]:{...spans[period],[edge]:value===""?NaN:Number(value)}};
    fromSummary=false;relationAbort?.abort();relation=null;resultState="empty";
  }
  async function compare(){
    relationAbort?.abort();
    const pending=new AbortController();relationAbort=pending;
    relation=null;resultState="loading";error="";
    try{
      if(!source||!spans)throw new Error("저장 출처와 측정 회차를 확인하세요.");
      validateSpans(spans);
      const frozen:Spans={a:{...spans.a},b:{...spans.b}};
      const response=await readAcquisitionRelation(assetId,source,x,y,frozen,pending.signal);
      if(pending.signal.aborted)return;
      relation=response;resultState="ready";remember();
    }catch(cause:unknown){
      if(pending.signal.aborted)return;
      error=cause instanceof Error?cause.message:"두 진동 특징의 관계를 확인하지 못했습니다.";
      resultState=cause instanceof AcquisitionRelationUnavailable?"unavailable":"failed";
    }
  }
  // The same feature pair in both periods needs the same scales for a fair visual comparison.
  const axes = $derived.by(() => {
    const current:AcquisitionRelation|null = relation;
    const points = current?.groups.flatMap(group=>group.points) ?? [];
    return points.length ? {xmin:Math.min(...points.map(p=>p.x)), xmax:Math.max(...points.map(p=>p.x)),
      ymin:Math.min(...points.map(p=>p.y)), ymax:Math.max(...points.map(p=>p.y))} : null;
  });
  const featureLabel = (id:string) => plainLabel(source?.features.find(item=>item.id===id)?.label ?? id,id);
  const message = $derived.by(() => {
    const read:AcquisitionRelation|null = relation;
    const ga = read?.groups.find(group=>group.period==="a"), gb = read?.groups.find(group=>group.period==="b");
    if(!read||!ga||!gb)return null;
    const side = (group:typeof ga) => ({pearson:group.pearson,spearman:group.spearman,pairs:group.pairs});
    // The crest factor's own median per period, only when every pair is in hand.
    const link = formulaLink(read.x,read.y);
    const axis = link==="crest"||link==="crest-rms" ? (read.x.endsWith(".crest_factor") ? "x" : "y") : null;
    const whole = (group:typeof ga) => group.points.length===group.pairs;
    const crest = axis&&whole(ga)&&whole(gb)
      ? {a:middle(ga.points.map(p=>p[axis])),b:middle(gb.points.map(p=>p[axis]))} : null;
    return relationMessage(read.x,read.y,side(ga),side(gb),crest,[read.x,read.y].map(id=>({
      label:featureLabel(id)+" 두 기간 비교",href:featureCompareHref(assetId,id,read.spans)})));
  });
  onMount(()=>{void load();return()=>{sourceAbort?.abort();relationAbort?.abort();};});
</script>

<section class="ui-panel" aria-labelledby="acq-relation-title">
  <h2 class="visually-hidden" id="acq-relation-title">진동 특징 관계</h2>
  {#if sourceState==="loading"}
    <StatusNotice message="진동 특징 목록을 불러오고 있습니다."/>
  {:else if sourceState==="failed"}
    <StatusNotice kind="failure" title="진동 특징 목록을 불러오지 못했습니다" message={error}
      actionLabel="다시 불러오기" onAction={()=>void load()}/>
  {:else if sourceState==="empty"||sourceState==="unavailable"}
    <StatusNotice kind="uncertain" title="비교할 진동 특징이 부족합니다"
      message={error||"같은 적용 모델에서 나온 서로 다른 특징이 두 개 이상 필요합니다."}/>
  {:else if source && spans}
    <div class="analysis-workspace"><header class="analysis-result-head"><div><h3>{featureLabel(x)} × {featureLabel(y)}</h3><p>A · {spans.a.from}–{spans.a.to}회 / B · {spans.b.from}–{spans.b.to}회</p></div><AnalysisControls title="비교 대상·기간">{#snippet children(close)}{#if source && spans}
    <p class="purpose">두 진동 특징이 함께 움직이는 방식이 달라졌는지 같은 측정의 특징값끼리 비교합니다. 계산식으로 연결된 특징의 높은 상관은 새로운 현상을 뜻하지 않을 수 있습니다.</p>
    <p class="context">데이터 출처 <strong>{readableSourceId(source.sourceId)}</strong>
      · {place(source.first)} ~ {place(source.last)}</p>
    <p class="period-summary">기간 A · 비교 기준 {place(spans.a.from)} ~ {place(spans.a.to)}<br/>기간 B · 살펴볼 구간 {place(spans.b.from)} ~ {place(spans.b.to)}</p>
    <section class="conditions">
    <div class="controls">
      <label>가로축 특징
        <select value={x} onchange={e=>feature("x",e.currentTarget.value)}>
          {#each source.features as item(item.id)}<option value={item.id}>{item.label}</option>{/each}
        </select>
      </label>
      <label>세로축 특징
        <select value={y} onchange={e=>feature("y",e.currentTarget.value)}>
          {#each source.features as item(item.id)}<option value={item.id}>{item.label}</option>{/each}
        </select>
      </label>
    </div>
    <div class="controls">
      {#each ["a","b"] as name(name)}
        {@const key=name as "a"|"b"}
        <AcquisitionRange name={key} span={spans[key]} first={source.first} last={source.last} {period}
          onChange={(edge, ordinal) => changeSpan(key, edge, String(ordinal))} />
      {/each}
    </div>
    <button type="button" class="ui-button ui-button-primary" onclick={()=>{close();void compare();}}>
      관계 계산하기
    </button>
    </section>
    {/if}{/snippet}</AnalysisControls></header>
    <div class="analysis-body">
    {#if resultState==="loading"}
      <StatusNotice message="같은 측정의 특징 짝을 불러오고 있습니다."/>
    {:else if resultState==="failed"}
      <StatusNotice kind="failure" title="진동 특징 관계를 불러오지 못했습니다" message={error}
        actionLabel="같은 조건으로 다시 불러오기" onAction={()=>void compare()}/>
    {:else if resultState==="unavailable"}
      <StatusNotice kind="uncertain" title="고른 측정에 분석된 특징이 없습니다" message={error}/>
    {:else if relation}
      {#if message}<p class="result-statement">{message.headline}</p>{/if}
      {#if fromSummary}<p class="context">{VIBRATION_SUMMARY_NOTE}</p>{/if}
      <div class="relation-workspace"><div class="pair">
      {#each relation.groups as group(group.period)}
        <section class="group">
          <h3>기간 {group.period.toUpperCase()}</h3>
          <p class="context span">{place(spans[group.period].from)} ~ {place(spans[group.period].to)}</p>
          {#if group.sampled||group.points.length<group.pairs}
            <StatusNotice kind="uncertain"
              message={"짝이 많아 계산이나 그래프에 일부만 사용했습니다. 분석한 측정은 전체 "+group.analyzed+"회, 쓸 수 있는 짝은 "+group.pairs+"개입니다."}/>
          {/if}
          {#if group.pairs<3||group.pearson===null||group.spearman===null}
            <StatusNotice kind="uncertain"
              message="짝이 부족하거나 값이 변하지 않아 관계를 계산할 수 없습니다."/>
          {/if}
          {#if group.points.length}
            {#if axes}<FeatureScatter bounds={axes}
              points={group.points.map(p=>({x:p.x,y:p.y,label:place(p.ordinal)}))}
              xLabel={featureLabel(x)+(relation.xUnit?" ("+relation.xUnit+")":"")}
              yLabel={featureLabel(y)+(relation.yUnit?" ("+relation.yUnit+")":"")}
              caption={null} picked={chosen?.period===group.period?group.points.findIndex(point=>point.ordinal===chosen.point.ordinal):null}
              onPick={index=>pickMeasurement(group.period,group.points[index].ordinal)}
              description={"기간 "+group.period.toUpperCase()+" · 같은 측정 특징 짝 "+group.points.length+"개 산점도."}/>{/if}
          {/if}
          <details><summary>상관계수와 측정 수</summary>
          {#if group.pearson!==null}<p class="headline">{strength(group.pearson)}</p>{/if}
          <dl>
            <div><dt>분석한 측정</dt><dd>{group.analyzed}회</dd></div>
            <div><dt>쓸 수 있는 특징 짝</dt><dd>{group.pairs}개</dd></div>
            <div><dt>상관계수 (값 그대로)</dt><dd>{count(group.pearson)}</dd></div>
            <div><dt>상관계수 (순위로)</dt><dd>{count(group.spearman)}</dd></div>
          </dl>
          </details>
          <details>
            <summary>같은 측정의 특징 짝 표 ({group.points.length}개 표시)</summary>
            <div class="table-scroll"><table>
              <caption>측정별 특징 짝 (일부만 표시될 수 있음)</caption>
              <thead><tr><th scope="col">측정</th><th scope="col">{x}</th><th scope="col">{y}</th></tr></thead>
              <tbody>
                {#each group.points.slice(0,100) as point(point.ordinal)}
                  <tr><td>{place(point.ordinal)}</td><td>{num(point.x)}</td><td>{num(point.y)}</td></tr>
                {/each}
              </tbody>
            </table></div>
            {#if group.points.length>100}<p class="context">표에는 앞의 100개만 표시합니다.</p>{/if}
          </details>
        </section>
      {/each}
      </div>
      {#if chosen}<aside class="relation-inspector" aria-label="선택한 측정">
        <header><h3>{chosen.point.ordinal}번째 측정</h3><span>기간 {chosen.period.toUpperCase()}</span></header>
        <dl><div><dt>{featureLabel(x)}</dt><dd>{measure(chosen.point.x,relation.xUnit)}</dd></div>
          <div><dt>{featureLabel(y)}</dt><dd>{measure(chosen.point.y,relation.yUnit)}</dd></div></dl>
        <nav aria-label="이 측정에서 이어서 분석">{#each linked.filter(link=>link.key!=="features") as link(link.key)}<a href={link.href}
          onclick={event=>event.currentTarget.href=investigationOriginUrl(event.currentTarget.href,location.href)}>{link.label} →</a>{/each}</nav>
      </aside>{/if}
      </div>
      <p class="context plot-note">한 점은 같은 측정의 두 특징값이고, 두 기간은 같은 축 범위로 표시합니다. 점의 색은 측정 순서에 따라 옅은색에서 진한색으로 바뀝니다.</p>
      {#if message}<AnalysisMessage {message} showHeadline={false}/>{/if}
      <CautionNote message="두 특징이 함께 움직여도 원인 관계나 고장을 뜻하지 않습니다. 경과 시간은 측정 간격으로 환산한 값이며 실제 측정 시각이 아닙니다."/>
    {:else}
      <p class="context">두 특징과 기간을 고르고 관계 계산하기를 누르면 결과를 표시합니다.</p>
    {/if}
    <details class="tech"><summary>기술 상세</summary><p class="context">적용 모델 연결 {source.bindingId}</p></details>
    </div></div>
  {/if}
</section>
<style>
  .period-summary{overflow-wrap:anywhere}
  .conditions{padding:var(--space-3);border:1px solid var(--color-border);border-radius:var(--radius-control)}
  .context{color:var(--color-ink-muted);overflow-wrap:anywhere}
  .controls{display:grid;gap:var(--space-3);grid-template-columns:minmax(0,1fr);margin-block:var(--space-3)}
  .pair{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:var(--space-5);align-items:start}
  label{display:grid;gap:var(--space-2);font-weight:650}
  select{min-width:0;width:100%;padding:var(--space-3);border:1px solid var(--color-border);
    color:var(--color-ink);background:var(--color-surface);border-radius:var(--radius-control)}
  dl{display:flex;flex-wrap:wrap;gap:var(--space-4)}dt{color:var(--color-ink-muted);font-size:var(--font-small)}
  dd{margin:0;font-weight:650}.group{min-width:0;padding-block:var(--space-2)}.group h3{font-size:var(--font-body);margin:0;overflow-wrap:anywhere}
  .span,.plot-note{font-size:var(--font-small);margin:0 0 var(--space-2)}
  .table-scroll{overflow-x:auto}
  table{width:100%;border-collapse:collapse}th,td{padding:var(--space-2);text-align:left;border-bottom:1px solid var(--color-border)}
  caption{text-align:left;color:var(--color-ink-muted)}
  .headline{font-size:var(--font-section);font-weight:700}

  .relation-workspace{display:grid;grid-template-columns:minmax(0,1fr) 240px;gap:var(--space-5);align-items:start}
  .relation-inspector{display:grid;gap:var(--space-4);border-left:1px solid var(--color-border);padding-left:var(--space-4);min-width:0}
  .relation-inspector header{display:flex;align-items:baseline;justify-content:space-between;gap:var(--space-2)}.relation-inspector header span,.relation-inspector dt{font-size:var(--font-small);color:var(--color-ink-muted)}
  .relation-inspector dl{display:grid;grid-template-columns:minmax(0,1fr);gap:var(--space-4);margin:0}.relation-inspector dd{margin:4px 0 0;font-size:var(--font-result);font-weight:700}
  .relation-inspector nav{display:grid;gap:var(--space-3);font-size:var(--font-small)}
  @media(max-width:1100px){.relation-workspace{grid-template-columns:minmax(0,1fr)}.relation-inspector{border-left:0;border-top:1px solid var(--color-border);padding:var(--space-3) 0 0}.relation-inspector dl{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>
