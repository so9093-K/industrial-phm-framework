<script lang="ts">
  import {onMount} from "svelte";
  import {readSourceNames, sourceLabel} from "../operations-status";
  import {readSignalNames,signalName,type SignalNames} from "../history";
  import {defaultPeriods,readSources,validatePeriods,NoHistoryError,type Periods,type SourceHistory} from "../comparison";
  import {readRelation,RelationUnavailable,type Relation} from "../relation";
  import StatusNotice from "./StatusNotice.svelte";
  import {num} from "../format";
  import CautionNote from "./CautionNote.svelte";
  import {strength} from "../relation";
  import {assetTabUrl} from "../routes";
  let {assetId}:{assetId:string}=$props();
  let sourceNames: Map<string, string> = $state(new Map());
  $effect(() => { void readSourceNames().then((value) => sourceNames = value); });
  let names: SignalNames = $state(new Map());
  $effect(() => { const asset = assetId; void readSignalNames(asset).then((value) => { if (asset === assetId) names = value; }); });
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
  <h2 id="relation-title">신호 관계</h2>
  <p class="context">같은 시각에 함께 기록된 두 신호가 같이 움직이는지 봅니다. 데이터 출처·측정 위치·시각이 같은 측정끼리만 짝짓습니다.</p>
  {#if listState==="loading"}
    <StatusNotice message="신호 목록을 불러오고 있습니다."/>
  {:else if listState==="failed"}
    <StatusNotice kind="failure" title="신호 목록을 불러오지 못했습니다" message={error} actionLabel="다시 불러오기" onAction={()=>void sourceList()}/>
  {:else if listState==="empty"||listState==="unavailable"}
    <StatusNotice kind="uncertain" title="비교할 신호가 부족합니다"
      message="같은 출처·시각에 함께 기록된 서로 다른 신호가 두 개 이상 있어야 합니다. 이상이 없다는 뜻은 아닙니다."
      actionLabel="신호 보기" actionHref={assetTabUrl(assetId, "signals")}/>
  {:else if available&&periods}
    <div class="controls">
      <label for="relation-x">신호 X
        <select id="relation-x" value={x} onchange={e=>switchChannel("x",e.currentTarget.value)}>
          {#each available.channels as id(id)}<option value={id}>{signalName(names,id)}</option>{/each}
        </select>
      </label>
      <label for="relation-y">신호 Y
        <select id="relation-y" value={y} onchange={e=>switchChannel("y",e.currentTarget.value)}>
          {#each available.channels as id(id)}<option value={id}>{signalName(names,id)}</option>{/each}
        </select>
      </label>
    </div>
    <div class="periods">
      {#each ["a","b"] as name(name)}
        {@const n=name as "a"|"b"}
        <fieldset><legend>기간 {n.toUpperCase()} (KST)</legend>
          <label>시작 <input type="datetime-local" value={localTime(periods[n].from)}
            onchange={e=>editPeriod(n,"from",e.currentTarget.value)}/></label>
          <label>끝 <input type="datetime-local" value={localTime(periods[n].to)}
            onchange={e=>editPeriod(n,"to",e.currentTarget.value)}/></label>
        </fieldset>
      {/each}
    </div>
    <button type="button" class="ui-button ui-button-primary" onclick={()=>void compare()}>
      관계 계산하기
    </button>
    {#if resultState==="loading"}
      <StatusNotice message="같은 시각에 기록된 측정 짝을 찾고 있습니다."/>
    {:else if resultState==="failed"}
      <StatusNotice kind="failure" title="신호 관계를 불러오지 못했습니다" message={error}
        actionLabel="같은 조건으로 다시 불러오기" onAction={()=>void compare()}/>
    {:else if resultState==="unavailable"}
      <StatusNotice kind="uncertain" title="비교할 기록이 없습니다" message={error}/>
    {:else if resultState==="empty"}
      <StatusNotice title="조건에 맞는 측정 짝이 없습니다"
        message="시각이나 출처가 다른 측정은 짝짓지 않습니다. 기간이나 신호를 바꿔 보세요."/>
    {:else if relation}
      <p class="context">기간 A {periodText("a")} · 기간 B {periodText("b")}</p>
      {#each relation.groups as group(group.id)}
        <section class="group">
          <h3>기간 {group.period.toUpperCase()} · {sourceLabel(sourceNames, group.source)} / {group.point??"측정 위치 미확인"}</h3>
          {#if group.pearson!==null}<p class="headline">{strength(group.pearson)}</p>{/if}
          <p class="context">{signalName(names,x)} ({group.xUnit??names.get(x)?.unit??"단위 미확인"}) / {signalName(names,y)} ({group.yUnit??names.get(y)?.unit??"단위 미확인"})</p>
          <dl>
            <div><dt>같은 시각 측정 짝</dt><dd>{group.pairCount}개</dd></div>
            <div><dt>피어슨 상관</dt><dd>{group.pearson===null?"계산 안 됨":group.pearson.toFixed(3)}</dd></div>
            <div><dt>스피어먼 상관</dt><dd>{group.spearman===null?"계산 안 됨":group.spearman.toFixed(3)}</dd></div>
          </dl>
          {#if group.sampled}
            <StatusNotice kind="uncertain" message="짝이 많아 일부만 골라 계산했습니다. 전체 분포로 단정하지 마세요."/>
          {/if}
          {#if group.pairCount<3||group.pearson===null||group.spearman===null}
            <StatusNotice kind="uncertain" message="짝이 부족하거나 값이 변하지 않아 관계를 계산할 수 없습니다. 관계가 없다는 뜻은 아닙니다."/>
          {/if}
          <details>
            <summary>같은 시각 측정 짝 보기 ({group.points.length}개)</summary>
            <div class="table-scroll"><table>
              <caption>각 행은 같은 출처·측정 위치·시각에 저장된 실제 측정 짝입니다</caption>
              <thead><tr><th scope="col">시각 (KST)</th><th scope="col">{signalName(names,x)}</th><th scope="col">{signalName(names,y)}</th></tr></thead>
              <tbody>{#each group.points.slice(0,100) as item,i (i)}
                <tr><td>{asTime(item.at)}</td><td>{num(item.x)}</td><td>{num(item.y)}</td></tr>
              {/each}</tbody>
            </table></div>
            {#if group.points.length>100}<p class="context">표에 최대 100개 짝만 표시합니다.</p>{/if}
          </details>
        </section>
      {/each}
      <CautionNote message="두 신호가 함께 움직여도 한쪽이 다른 쪽의 원인이라는 뜻은 아닙니다. 고장 여부도 판단하지 않습니다."/>
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
  .headline{font-size:var(--font-section);font-weight:700}
</style>
