<script lang="ts">
  import {onMount} from "svelte";
  import {readSourceNames, sourceLabel} from "../operations-status";
  import {readSignalNames,signalName,type SignalNames} from "../history";
  import {defaultPeriods,readSources,validatePeriods,NoHistoryError,type Periods,type SourceHistory} from "../comparison";
  import {readRelation,RelationUnavailable,type PairedGroup,type Relation} from "../relation";
  import FeatureScatter from "./FeatureScatter.svelte";
  import AnalysisMessage from "./AnalysisMessage.svelte";
  import {relationMessage} from "../analysis-messages";
  import {ORIGIN_TEXT,focusFrom,focusParams,momentWindow,periodOrigin,windowParams,type PeriodOrigin} from "../signal-selection";
  import StatusNotice from "./StatusNotice.svelte";
  import {num} from "../format";
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
  let focus=$state(focusFrom(new URLSearchParams(location.search)));
  let x=$state(new URLSearchParams(location.search).get("relation_x")??"");
  let y=$state(new URLSearchParams(location.search).get("relation_y")??"");
  let periods:Periods|null=$state(null);
  // Periods handed over from a span picked on the signal chart; said on screen until edited.
  let handedOver:PeriodOrigin|null=$state(periodOrigin(location.search));
  // Each source, point and meaning shows both periods side by side on one shared axis range.
  type Pair={key:string;source:string;point:string|null;xMeaning?:string|null;yMeaning?:string|null;a:PairedGroup|null;b:PairedGroup|null};
  const pairs=$derived.by(():Pair[]=>{
    const current:Relation|null=relation;
    if(!current)return [];
    const found=new Map<string,Pair>();
    for(const group of current.groups){
      if(focus && (group.source!==focus.source || (focus.point!==undefined && group.point!==focus.point))) continue;
      if(focus?.interpretation && group.xMeaning !== focus.interpretation) continue;
      const key=JSON.stringify([group.source,group.point,group.meaning]);
      const pair=found.get(key)??{key,source:group.source,point:group.point,xMeaning:group.xMeaning,yMeaning:group.yMeaning,a:null,b:null};
      pair[group.period]=group;found.set(key,pair);
    }
    return [...found.values()];
  });
  let chosen:{key:string;period:"a"|"b";index:number}|null=$state(null);
  function bounds(pair:Pair){
    const all=[...(pair.a?.points??[]),...(pair.b?.points??[])];
    if(!all.length)return null;
    const xs=all.map(p=>p.x),ys=all.map(p=>p.y);
    return {xmin:Math.min(...xs),xmax:Math.max(...xs),ymin:Math.min(...ys),ymax:Math.max(...ys)};
  }
  /** The signals screen for the point's own source and point, narrowly around its time. */
  function around(at:string,channel:string,period:"a"|"b",pair:Pair):string{
    const middle=Date.parse(at);
    const length=periods?Date.parse(periods[period].to)-Date.parse(periods[period].from):0;
    const url=new URL(assetTabUrl(assetId,"signals",null,null,channel),location.origin);
    const params={...windowParams(momentWindow(middle,length),{from:middle,to:middle}),
      ...focusParams({source:pair.source,point:pair.point,interpretation:(channel===x?pair.xMeaning:pair.yMeaning)??undefined})};
    for(const [key,value] of Object.entries(params))url.searchParams.set(key,value);
    return url.pathname+url.search;
  }
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
    if(!a||!b){handedOver=null;return fallback;}
    try{validatePeriods({a,b});return {a,b};}catch{handedOver=null;return fallback;}
  }
  function remember(){
    if(!periods)return;
    const url=new URL(location.href);
    url.searchParams.delete("record_key");
    url.searchParams.set("monitor_range","window");
    url.searchParams.set("monitor_from",periods.b.from);
    url.searchParams.set("monitor_to",periods.b.to);
    url.searchParams.set("monitor_pick",periods.b.from+"~"+periods.b.to);
    url.searchParams.set("monitor_asset",assetId);
    for(const key of ["monitor_source","monitor_point","monitor_interpretation"])url.searchParams.delete(key);
    if(focus)for(const[key,value]of Object.entries(focusParams(focus)))url.searchParams.set(key,value);
    url.searchParams.set("monitor_channel",x);
    url.searchParams.set("relation_x",x);
    url.searchParams.set("relation_y",y);
    url.searchParams.set("compare_a",periods.a.from+"~"+periods.a.to);
    url.searchParams.set("compare_b",periods.b.from+"~"+periods.b.to);
    if(!handedOver)url.searchParams.delete("compare_origin");
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
    if(which==="x"){x=value;if(focus)focus={...focus,interpretation:undefined};}else y=value;
    relationAbort?.abort();relation=null;resultState="empty";remember();
  }
  function editPeriod(n:"a"|"b",edge:"from"|"to",value:string){
    if(!periods)return;
    periods={...periods,[n]:{...periods[n],[edge]:selectedPeriod(value)}};
    relationAbort?.abort();relation=null;resultState="empty";handedOver=null;
  }
  async function compare(){
    relationAbort?.abort();
    const req=new AbortController();relationAbort=req;
    relation=null;chosen=null;resultState="loading";error="";
    try{
      if(!periods)throw new Error("비교 기간을 선택하세요.");
      const frozen:Periods={a:{...periods.a},b:{...periods.b}};
      validatePeriods(frozen);
      const response=await readRelation(assetId,x,y,frozen,req.signal);
      if(req.signal.aborted)return;
      relation=response;resultState=pairs.length?"ready":"empty";
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
      message="같은 출처·시각에 함께 기록된 서로 다른 신호가 두 개 이상 있어야 합니다."
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
    {#if focus}<p class="context">선택한 출처 {sourceLabel(sourceNames,focus.source)}{focus.point===undefined?"":" · 측정 위치 "+(focus.point??"미지정")}의 기록을 보고 있습니다.</p>
      <button type="button" class="ui-button" onclick={()=>{focus=null;remember();void compare();}}>다른 출처의 기록 보기</button>{/if}
    {#if handedOver}
      <p class="handed">{ORIGIN_TEXT[handedOver]}</p>
    {/if}
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
      <StatusNotice title={!relation?"선택한 조건으로 관계를 계산하세요":focus?"선택한 출처에서는 함께 기록된 신호가 없습니다":"조건에 맞는 측정 짝이 없습니다"}
        message={!relation?"신호나 기간을 바꿨습니다. 관계 계산하기를 눌러 확인하세요.":focus?"고른 신호·기간에서 같은 시각의 측정 짝을 찾지 못했습니다. 신호·기간을 바꾸거나 다른 출처의 기록을 확인하세요.":"시각이나 출처가 다른 측정은 짝짓지 않습니다. 기간이나 신호를 바꿔 보세요."}/>
    {:else if relation}
      <p class="context">기간 A {periodText("a")} · 기간 B {periodText("b")}</p>
      {#each pairs as pair(pair.key)}
        {@const axes=bounds(pair)}
        {@const side=(group:PairedGroup|null)=>({pearson:group?.pearson??null,spearman:group?.spearman??null,pairs:group?.pairCount??0})}
        {@const message=relation?relationMessage(relation.x,relation.y,side(pair.a),side(pair.b),null):null}
        <section class="group">
          <h3>{sourceLabel(sourceNames, pair.source, pairs.map((each) => each.source))} / {pair.point??"측정 위치 미확인"}</h3>
          {#if message}<AnalysisMessage {message}
            subject={signalName(names,x) + " × " + signalName(names,y) + " · " + sourceLabel(sourceNames, pair.source, pairs.map((each) => each.source))}
            basis={"기간 A " + periodText("a") + " / 기간 B " + periodText("b")}
            boundary="같은 시각의 측정값에서 계산한 관계입니다. 한쪽이 다른 쪽의 원인이라는 뜻은 아닙니다." />
          {:else}<StatusNotice kind="uncertain" title="관계를 해석할 측정값이 부족합니다"
            message="값의 변동이나 같은 시각의 측정 짝이 부족해 계산할 수 없습니다." />{/if}
          <div class="sides">
            {#each ["a","b"] as name(name)}
              {@const n=name as "a"|"b"}
              {@const group=pair[n]}
              <div class="side">
                <h4>기간 {n.toUpperCase()}</h4>
                {#if !group}
                  <p class="context">이 기간에는 같은 시각 측정 짝이 없습니다.</p>
                {:else}
                  {#if group.pearson!==null}<p class="headline">{strength(group.pearson)}</p>{/if}
                  <dl>
                    <div><dt>같은 시각 측정 짝</dt><dd>{group.pairCount}개</dd></div>
                    <div><dt>피어슨 상관</dt><dd>{group.pearson===null?"계산 안 됨":group.pearson.toFixed(3)}</dd></div>
                    <div><dt>스피어먼 상관</dt><dd>{group.spearman===null?"계산 안 됨":group.spearman.toFixed(3)}</dd></div>
                  </dl>
                  {#if group.sampled}
                    <StatusNotice kind="uncertain" message="짝이 많아 일부만 골라 계산했습니다. 전체 분포로 단정하지 마세요."/>
                  {/if}
                  {#if group.pairCount<3||group.pearson===null||group.spearman===null}
                    <StatusNotice kind="uncertain" message="짝이 부족하거나 값이 변하지 않아 관계를 계산할 수 없습니다."/>
                  {/if}
                  {#if axes&&group.points.length}
                    <FeatureScatter bounds={axes} points={group.points.map(p=>({x:p.x,y:p.y,label:asTime(p.at)}))}
                      xLabel={signalName(names,x)} yLabel={signalName(names,y)}
                      description={"기간 "+n.toUpperCase()+" · 같은 시각 측정 짝 "+group.points.length+"개 산점도."}
                      caption={"한 점은 같은 시각에 함께 기록된 두 측정값입니다. 두 기간은 같은 축 범위로 그립니다. 점을 누르면 그 시각을 봅니다."}
                      picked={chosen?.key===pair.key&&chosen.period===n?chosen.index:null}
                      onPick={(index)=>chosen={key:pair.key,period:n,index}}/>
                  {/if}
                {/if}
              </div>
            {/each}
          </div>
          {#if chosen?.key===pair.key}
            {@const point=pair[chosen.period]?.points[chosen.index]}
            {#if point}
              <div class="chosen" aria-live="polite">
                <p><strong>선택한 점 · 기간 {chosen.period.toUpperCase()} · {asTime(point.at)}</strong></p>
                <p>{signalName(names,x)} {num(point.x)} · {signalName(names,y)} {num(point.y)}</p>
                <p class="links"><a href={around(point.at,x,chosen.period,pair)}>{signalName(names,x)} 신호에서 이 시각 보기 →</a>
                  <a href={around(point.at,y,chosen.period,pair)}>{signalName(names,y)} 신호에서 이 시각 보기 →</a></p>
              </div>
            {/if}
          {/if}
          {#each [pair.a,pair.b] as group,i(i)}
            {#if group}
              <details>
                <summary>기간 {group.period.toUpperCase()} · 같은 시각 측정 짝 보기 ({group.points.length}개)</summary>
                <div class="table-scroll"><table>
                  <caption>각 행은 같은 출처·측정 위치·시각에 저장된 실제 측정 짝입니다</caption>
                  <thead><tr><th scope="col">시각 (KST)</th><th scope="col">{signalName(names,x)}</th><th scope="col">{signalName(names,y)}</th></tr></thead>
                  <tbody>{#each group.points.slice(0,100) as item,i (i)}
                    <tr><td>{asTime(item.at)}</td><td>{num(item.x)}</td><td>{num(item.y)}</td></tr>
                  {/each}</tbody>
                </table></div>
                {#if group.points.length>100}<p class="context">표에 최대 100개 짝만 표시합니다.</p>{/if}
              </details>
            {/if}
          {/each}
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
  .headline{font-size:var(--font-section);font-weight:700;margin:0}
  .sides{display:grid;gap:var(--space-4) var(--space-6);grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}
  .side{min-width:0}.side h4{margin:0 0 var(--space-2)}
  .chosen{margin-top:var(--space-3);padding:var(--space-3) var(--space-4);border:1px solid var(--color-border);
    border-left:4px solid var(--color-focus);border-radius:var(--radius-control);display:grid;gap:var(--space-1)}
  .chosen p{margin:0;overflow-wrap:anywhere}.links{display:flex;flex-wrap:wrap;gap:var(--space-2) var(--space-4)}
  .handed{margin:var(--space-4) 0 0;padding:var(--space-3);border-left:4px solid var(--color-focus);background:var(--color-surface-selected);overflow-wrap:anywhere}
</style>
