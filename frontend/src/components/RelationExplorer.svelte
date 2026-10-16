<script lang="ts">
  import {onMount} from "svelte";
  import {defaultPeriods,readSources,validatePeriods,NoHistoryError,type Periods,type SourceHistory} from "../comparison";
  import {readRelation,RelationUnavailable,type Relation} from "../relation";
  import StatusNotice from "./StatusNotice.svelte";
  let {assetId}:{assetId:string}=$props();
  type State="loading"|"ready"|"empty"|"unavailable"|"failed";
  let listState:State=$state("loading");
  let resultState:State=$state("empty");
  let available:SourceHistory|null=$state(null);
  let relation:Relation|null=$state(null);
  let error=$state("");
  let x=$state(new URLSearchParams(location.search).get("relation_x")??"");
  let y=$state(new URLSearchParams(location.search).get("relation_y")??"");
  let periods:Periods|null=$state(null);
  let sourceAbort:AbortController|null=null;
  let relationAbort:AbortController|null=null;
  const asTime=(value:string)=>new Date(value).toLocaleString("ko-KR",{timeZone:"Asia/Seoul"});
  const periodText=(n:"a"|"b")=>periods?asTime(periods[n].from)+" ~ "+asTime(periods[n].to):"";
  const localTime=(value:string)=>new Date(Date.parse(value)+9*3600000).toISOString().slice(0,16);
  const selectedPeriod=(raw:string)=>raw+":00+09:00";
  function initialPeriods(fallback:Periods):Periods{
    const args=new URLSearchParams(location.search);
    const decode=(key:string)=>{
      const parts=args.get(key)?.split("~");
      return parts?.length===2?{from:parts[0],to:parts[1]}:null;
    };
    const a=decode("compare_a"),b=decode("compare_b");
    if(!a||!b)return fallback;
    try{validatePeriods({a,b});return {a,b};}catch{return fallback;}
  }
  function remember(){
    if(!periods)return;
    const url=new URL(location.href);
    url.searchParams.set("monitor_asset",assetId);
    url.searchParams.set("relation_x",x);
    url.searchParams.set("relation_y",y);
    url.searchParams.set("compare_a",periods.a.from+"~"+periods.a.to);
    url.searchParams.set("compare_b",periods.b.from+"~"+periods.b.to);
    history.replaceState(history.state,"",url);
  }
  async function sourceList(){
    sourceAbort?.abort();relationAbort?.abort();
    const req=new AbortController();sourceAbort=req;
    listState="loading";resultState="empty";relation=null;available=null;error="";
    try{
      const src=await readSources(assetId,req.signal);
      if(req.signal.aborted)return;
      available=src;
      if(src.channels.length<2){listState="empty";return;}
      if(!src.channels.includes(x))x=src.channels[0];
      if(!src.channels.includes(y)||x===y)y=src.channels.find(c=>c!==x)??"";
      periods=initialPeriods(defaultPeriods(src.from,src.to));
      listState="ready";
      remember();await compare();
    }catch(cause:unknown){
      if(req.signal.aborted)return;
      listState=cause instanceof NoHistoryError?"unavailable":"failed";
      error=cause instanceof Error?cause.message:"저장 측정 목록을 조회할 수 없습니다.";
    }
  }
  function switchChannel(which:"x"|"y",value:string){
    if(!available?.channels.includes(value))return;
    if(which==="x")x=value;else y=value;
    relationAbort?.abort();relation=null;resultState="empty";remember();
  }
  function editPeriod(n:"a"|"b",edge:"from"|"to",value:string){
    if(!periods)return;
    periods={...periods,[n]:{...periods[n],[edge]:selectedPeriod(value)}};
    relationAbort?.abort();relation=null;resultState="empty";
  }
  async function compare(){
    relationAbort?.abort();
    const req=new AbortController();relationAbort=req;
    relation=null;resultState="loading";error="";
    try{
      if(!periods)throw new Error("비교 기간을 선택하세요.");
      const frozen:Periods={a:{...periods.a},b:{...periods.b}};
      validatePeriods(frozen);
      const response=await readRelation(assetId,x,y,frozen,req.signal);
      if(req.signal.aborted)return;
      relation=response;resultState=response.groups.length?"ready":"empty";
      remember();
    }catch(cause:unknown){
      if(req.signal.aborted)return;
      error=cause instanceof Error?cause.message:"저장 측정 관계를 계산할 수 없습니다.";
      resultState=cause instanceof RelationUnavailable?"unavailable":"failed";
    }
  }
  onMount(()=>{void sourceList();return()=>{sourceAbort?.abort();relationAbort?.abort();};});
</script>
<section class="ui-panel relation" aria-labelledby="relation-title">
  <h2 id="relation-title">두 신호의 같은 시각 관측 짝</h2>
  <p class="context">설비 <strong>{assetId}</strong> · 저장된 관측 중 원본 출처·측정 지점·시각이 같은 짝만 분석합니다. 상관관계는 원인·고장 여부·확률을 뜻하지 않습니다.</p>
  {#if listState==="loading"}
    <StatusNotice message="두 신호의 저장 측정 목록을 읽고 있습니다."/>
  {:else if listState==="failed"}
    <StatusNotice kind="failure" title="신호 목록 조회 실패" message={error} actionLabel="재조회" onAction={()=>void sourceList()}/>
  {:else if listState==="empty"||listState==="unavailable"}
    <StatusNotice kind="uncertain" title="비교할 측정 신호가 부족합니다"
      message="서로 다른 두 신호에 같은 출처·시각의 관측이 있어야 합니다. 목록이 부족하다는 것은 정상 설비라는 의미가 아닙니다."
      actionLabel="신호와 품질 확인" actionHref={"/web-next/?view=signals&monitor_asset="+encodeURIComponent(assetId)}/>
  {:else if available&&periods}
    <div class="controls">
      <label for="relation-x">X 측정
        <select id="relation-x" value={x} onchange={e=>switchChannel("x",e.currentTarget.value)}>
          {#each available.channels as id(id)}<option value={id}>{id}</option>{/each}
        </select>
      </label>
      <label for="relation-y">Y 측정
        <select id="relation-y" value={y} onchange={e=>switchChannel("y",e.currentTarget.value)}>
          {#each available.channels as id(id)}<option value={id}>{id}</option>{/each}
        </select>
      </label>
    </div>
    <div class="periods">
      {#each ["a","b"] as name(name)}
        {@const n=name as "a"|"b"}
        <fieldset><legend>구간 {n.toUpperCase()} (KST)</legend>
          <label>시작 <input type="datetime-local" value={localTime(periods[n].from)}
            onchange={e=>editPeriod(n,"from",e.currentTarget.value)}/></label>
          <label>끝 <input type="datetime-local" value={localTime(periods[n].to)}
            onchange={e=>editPeriod(n,"to",e.currentTarget.value)}/></label>
        </fieldset>
      {/each}
    </div>
    <button type="button" class="ui-button ui-button-primary" onclick={()=>void compare()}>
      같은 시각의 신호 짝 비교
    </button>
    {#if resultState==="loading"}
      <StatusNotice message="동일 원본 출처·시각의 저장 측정 짝을 찾고 있습니다."/>
    {:else if resultState==="failed"}
      <StatusNotice kind="failure" title="관계 분석 조회 실패" message={error}
        actionLabel="같은 조건 재조회" onAction={()=>void compare()}/>
    {:else if resultState==="unavailable"}
      <StatusNotice kind="uncertain" title="저장 근거 없음" message={error}/>
    {:else if resultState==="empty"}
      <StatusNotice title="조건에 맞는 측정 짝이 없습니다"
        message="서로 다른 시각·출처의 측정값을 임의로 연결하지 않습니다."/>
    {:else if relation}
      <p class="context">구간 A: {periodText("a")} · 구간 B: {periodText("b")}</p>
      {#each relation.groups as group(group.id)}
        <section class="group">
          <h3>구간 {group.period.toUpperCase()} · {group.source} / {group.point??"측정점 미확인"}</h3>
          <p class="context">측정 의미 {group.meaning} · {x} ({group.xUnit??"단위 미확인"}) / {y} ({group.yUnit??"단위 미확인"})</p>
          <dl>
            <div><dt>같은 시각 관측 짝</dt><dd>{group.pairCount}개</dd></div>
            <div><dt>피어슨 상관</dt><dd>{group.pearson===null?"미산출":group.pearson.toFixed(3)}</dd></div>
            <div><dt>스피어먼 상관</dt><dd>{group.spearman===null?"미산출":group.spearman.toFixed(3)}</dd></div>
          </dl>
          {#if group.sampled}
            <StatusNotice kind="uncertain" message="서버에서 일부 짝만 샘플링했습니다. 관측의 전체 분포를 단정하지 마세요."/>
          {/if}
          {#if group.pairCount<3||group.pearson===null||group.spearman===null}
            <StatusNotice kind="uncertain" message="관측 짝이 부족하거나 상수 신호 등으로 관계 계수를 계산할 수 없습니다. 무관계(0)로 간주하지 마세요."/>
          {/if}
          <details>
            <summary>서버가 제공한 관측 짝 보기 ({group.points.length}개)</summary>
            <div class="table-scroll"><table>
              <caption>각 행은 동일 원본 출처·측정 지점·시각의 실제 저장 관측 짝입니다.</caption>
              <thead><tr><th scope="col">시각 (KST)</th><th scope="col">{x}</th><th scope="col">{y}</th></tr></thead>
              <tbody>{#each group.points.slice(0,100) as item,i (i)}
                <tr><td>{asTime(item.at)}</td><td>{item.x}</td><td>{item.y}</td></tr>
              {/each}</tbody>
            </table></div>
            {#if group.points.length>100}<p class="context">표에 최대 100개 짝만 표시합니다.</p>{/if}
          </details>
        </section>
      {/each}
    {/if}
  {/if}
</section>
<style>
  .relation{min-width:0}.context{color:var(--color-ink-muted);overflow-wrap:anywhere}
  .controls,.periods{display:grid;gap:var(--space-3);grid-template-columns:repeat(auto-fit,minmax(175px,1fr));margin-block:var(--space-4)}
  label{display:grid;gap:var(--space-2);font-weight:650}
  select,input{min-width:0;width:100%;padding:var(--space-3);color:var(--color-ink);background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius-control)}
  fieldset{min-width:0;display:grid;gap:var(--space-2);border:1px solid var(--color-border);border-radius:var(--radius-panel)}
  .group{border-top:1px solid var(--color-border);margin-top:var(--space-6);padding-top:var(--space-4)}
  dl{display:flex;flex-wrap:wrap;gap:var(--space-4)}dt{color:var(--color-ink-muted);font-size:var(--font-small)}dd{margin:0;font-weight:700}
  .table-scroll{overflow-x:auto}table{width:100%;border-collapse:collapse}th,td{text-align:left;border-bottom:1px solid var(--color-border);padding:var(--space-2)}
  caption{text-align:left;color:var(--color-ink-muted);font-size:var(--font-small)}
</style>
