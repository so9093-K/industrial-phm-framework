<script lang="ts">
  import {untrack,onDestroy} from "svelte";
  import {groupHistory,readSignalNames,signalName,signalChart,type SignalNames,type HistoryStream,type TrendWindow} from "../history";
  import {readObservation,readWindow,receiptStatus,observationLink,observationAnchor,type Observation} from "../observation";
  import {observationOrigin} from "../observation-context";
  import {summarize,type Span} from "../signal-selection";
  import {spanText as timeSpan} from "../asset-timeline";
  import {measure} from "../chart-axis";
  import {elapsedText} from "../time-axis";
  import type {Source} from "../operations-status";
  import ObservationChart from "./ObservationChart.svelte";
  import StatusNotice from "./StatusNotice.svelte";
  let {assetId,stream,source,sourceReadable,cycle,observed,preferred=null}:{assetId:string;stream:HistoryStream;source?:Source;
    sourceReadable:boolean;cycle:number;preferred?:string|null;observed:(at:string|null)=>string}=$props();
  const params=new URLSearchParams(location.search);
  const initialStream=untrack(()=>stream),initialPreferred=untrack(()=>preferred);
  const origin=observationOrigin(params,untrack(()=>assetId));
  const initialWindow=origin?.window??null;
  const ranges=[{id:"15m",label:"15분"},{id:"1h",label:"1시간"},{id:"24h",label:"24시간"}];
  let channel=$state(origin?.channel??(params.has("observation_channel")?params.get("observation_channel")!:initialPreferred&&initialStream.channels.includes(initialPreferred)?initialPreferred:initialStream.channels[0]));
  let range=$state(ranges.some(r=>r.id===params.get("observation_range"))?params.get("observation_range")!:"1h");
  let window:TrendWindow|null=$state(initialWindow);
  let following=$state(initialWindow===null);
  let snapshot:number|null=$state(origin?.snapshot??null);
  let reference:TrendWindow|null=$state(readWindow(params.get("observation_reference_from"),params.get("observation_reference_to")));
  let picked:Span|null=$state(origin?.selection??null);
  let heldAnchor:"now"|"latest"=$state(params.get("observation_anchor")==="now"?"now":"latest");
  const anchor=$derived(following?observationAnchor(stream.endAt,source):heldAnchor);
  let read:Observation|null=$state(null),names:SignalNames=$state(new Map()),loading=$state(false),error=$state("");
  let request:AbortController|null=null,loadedKey="",resumeOnCancel=false;
  onDestroy(()=>request?.abort());
  const queryKey=$derived(JSON.stringify([channel,range,window,snapshot,reference,anchor]));
  const groups=$derived.by(()=>{const current:Observation|null=read;return current?groupHistory(current.trend):[];});
  const group=$derived([...groups].sort((a,b)=>Date.parse(b.buckets.at(-1)?.lastEventAt??b.buckets.at(-1)?.bucketStart??"")-Date.parse(a.buckets.at(-1)?.lastEventAt??a.buckets.at(-1)?.bucketStart??""))[0]??null);
  const latest=$derived.by(()=>{const current:Observation|null=read;return current?.trend.latest[0]??null;});
  const unit=$derived(latest?.unit??group?.unit??null);
  const comparison=$derived.by(()=>{
    const current:Observation|null=read;
    if(!group||!reference||!current?.reference||Date.parse(current.reference.period.from)!==Date.parse(reference.from)||Date.parse(current.reference.period.to)!==Date.parse(reference.to))return null;
    return current.reference.groups.find(item=>item.interpretationId===group.interpretationId&&item.unit===group.unit)??null;
  });
  const changes=$derived([...(comparison?.intervals??[])].sort((a,b)=>b.from-a.from));
  const chart=$derived.by(()=>{const current:Observation|null=read;return current&&group?signalChart(group,current.trend.startAt,current.trend.endAt,current.trend.bucketSeconds,{start:Date.parse(current.trend.startAt),height:300}):null;});
  const selection=$derived(group&&picked?summarize(group,picked):null);
  const label=$derived(signalName(names,channel));
  function remember(){
    const url=new URL(location.href),q=url.searchParams;
    q.set("observation_view","recent");q.set("observation_follow",following?"following":"paused");q.set("observation_range",range);q.set("observation_anchor",anchor);
    q.set("observation_asset",assetId);q.set("observation_channel",channel);q.set("observation_source",stream.sourceId);q.set("observation_point",stream.pointId??"");
    if(window){q.set("observation_from",window.from);q.set("observation_to",window.to);}else{q.delete("observation_from");q.delete("observation_to");}
    if(snapshot!==null)q.set("observation_snapshot",String(snapshot));else q.delete("observation_snapshot");
    if(picked){q.set("observation_pick",new Date(picked.from).toISOString()+"~"+new Date(picked.to).toISOString());}else q.delete("observation_pick");
    for(const [key,value] of [["observation_reference_from",reference?.from],["observation_reference_to",reference?.to]] as const){if(value)q.set(key,value);else q.delete(key);}
    history.replaceState(history.state,"",url);
  }
  async function refresh(key=queryKey){
    request?.abort();const pending=new AbortController();request=pending;loading=true;
    try{
      const next=await readObservation(assetId,stream,channel,{range,window,snapshot,reference,anchor},pending.signal);
      if(pending.signal.aborted)return;read=next;loadedKey=key;error="";
    }catch(cause){if(!pending.signal.aborted)error=cause instanceof Error?cause.message:"관측을 갱신하지 못했습니다.";}
    finally{if(!pending.signal.aborted)loading=false;}
  }
  $effect(()=>{
    const key=queryKey;cycle;
    if(!stream.channels.includes(channel)){error="이 기록에 선택한 신호가 없습니다. 다른 신호를 선택하세요.";return;}
    if(!following&&key===loadedKey)return;
    untrack(()=>void refresh(key));
    return()=>request?.abort();
  });
  $effect(()=>{const id=assetId;void readSignalNames(id).then(value=>names=value);});
  function freeze(){
    if(!following||!read)return;
    request?.abort();loading=false;
    heldAnchor=anchor;window={from:read.trend.startAt,to:read.trend.endAt};snapshot=read.trend.snapshotId??null;following=false;
    loadedKey=queryKey;remember();
  }
  function beginSelection(){resumeOnCancel=following;freeze();}
  function cancelSelection(){if(resumeOnCancel)resume();resumeOnCancel=false;}
  function choose(span:Span){freeze();resumeOnCancel=false;picked=span;remember();}
  function resume(){picked=null;window=null;snapshot=null;following=true;remember();}
  function changeChannel(value:string){request?.abort();read=null;picked=null;reference=null;channel=value;remember();}
  function changeRange(value:string){range=value;resume();}
  function setReference(){
    if(!picked||!selection||selection.usable<5)return;
    reference={from:new Date(picked.from).toISOString(),to:new Date(picked.to).toISOString()};
    resume();
  }
  function clearReference(){reference=null;remember();}
  const spanText=(span:Span)=>timeSpan(span.from,span.to);
  const difference=(value:number,baseline:number,of:string|null)=>
    (value>baseline?"+":"")+measure(value-baseline,of,4);
  function href(method:"signals"|"compare"){
    if(!picked||!read||!group)return "";
    const url=new URL(observationLink(assetId,channel,stream,group.interpretationId,{from:Date.parse(read.trend.startAt),to:Date.parse(read.trend.endAt)},picked,reference,method,label),location.origin);
    url.searchParams.set("observation_snapshot",String(read.trend.snapshotId));url.searchParams.set("observation_range",range);url.searchParams.set("observation_anchor",anchor);
    if(reference){url.searchParams.set("observation_reference_from",reference.from);url.searchParams.set("observation_reference_to",reference.to);}
    return url.pathname+url.search;
  }
</script>
<section class="ui-panel observation" aria-label="측정 추이와 구간 조사">
  <header class="observation-head">
    <label class="signal">신호<select bind:value={channel} onchange={e=>changeChannel(e.currentTarget.value)}>
      {#if !stream.channels.includes(channel)}<option value={channel} disabled>다른 신호 선택</option>{/if}
      {#each stream.channels as id(id)}<option value={id}>{signalName(names,id)}</option>{/each}
    </select></label>
    <div class="reading"><strong>{latest?.usable&&latest.value!==null?measure(latest.value,unit):"—"}</strong>
      <div><span>마지막 측정 · {latest?.eventAt?observed(latest.eventAt):"저장된 측정 없음"}</span>
        <small>{receiptStatus(source,sourceReadable)}</small></div>
    </div>
    <div class="follow-state">
      <span class:following title={following?"1분마다 새로 저장된 측정을 확인합니다":undefined}>{following?"새 기록 자동 확인":"선택 시점에 고정"}</span>
      <button type="button" class="ui-button" disabled={loading&&following} onclick={()=>following?void refresh():resume()}>
        {following?"새로고침":"최신 측정으로"}
      </button>
    </div>
  </header>
  <div class="plot-toolbar">
    <div class="choices" role="group" aria-label="표시 범위">{#each ranges as item(item.id)}
      <button type="button" aria-pressed={range===item.id} onclick={()=>changeRange(item.id)}>{item.label}</button>
    {/each}</div>
    <span class="time-context">{#if read}{spanText({from:Date.parse(read.trend.startAt),to:Date.parse(read.trend.endAt)})}{/if}</span>
    {#if reference}<div class="reference-context"><span>비교 기준 {spanText({from:Date.parse(reference.from),to:Date.parse(reference.to)})}</span>
      <button type="button" class="quiet" onclick={clearReference}>해제</button></div>{/if}
  </div>
  {#if error}<StatusNotice kind="uncertain" message={error+(read?" 마지막으로 읽은 관측을 유지합니다.":"")} actionLabel="다시 시도" onAction={()=>void refresh()}/>{/if}
  {#if chart&&read}
    <ObservationChart {chart} origin={Date.parse(read.trend.startAt)} step={read.trend.bucketSeconds?read.trend.bucketSeconds*1000:null} {unit} {label} {picked}
      reference={reference?{from:Date.parse(reference.from),to:Date.parse(reference.to)}:null} referenceValue={comparison?.median??null}
      intervals={comparison?.intervals??[]} onFreeze={beginSelection} onSelect={choose} onCancel={cancelSelection} onClear={resume}/>
    <div class="caption"><span>구간 평균 · 옅은 선은 최소–최대 · 공백은 측정 없음</span>
      <span>{#if reference}<i class="reference-key"></i> 비교 기준 <i class="change-key"></i> 기준보다 달라진 구간{:else}점을 선택하거나 드래그해 구간 선택{/if}</span>
    </div>
  {:else if loading}<StatusNotice message="저장된 측정을 읽고 있습니다."/>
  {:else if read}<p class="empty">이 범위에 측정이 없습니다. 마지막 측정 시각과 데이터 연결 상태를 확인하세요.</p>{/if}
  {#if picked}
    <aside class="selection" aria-label="선택한 구간">
      <div class="selection-reading"><div><span>{spanText(picked)}</span>
        <strong>{!read?error?"확인 불가":"불러오는 중":selection?.mean!=null?measure(selection.mean,group?.unit,4):"측정 없음"}</strong></div>
        {#if selection?.mean!=null}<small>구간 평균 · 측정 {selection.usable}개{#if selection.minimum!==null&&selection.maximum!==null}<br/>{measure(selection.minimum,group?.unit,4)} ~ {measure(selection.maximum,group?.unit,4)}{/if}</small>{/if}
      </div>
      <nav class="selection-actions" aria-label="선택 구간 작업">
        {#if selection?.mean!=null}<a class="ui-button ui-button-primary" href={href("signals")}>선택 구간 분석 →</a>
          <a class="ui-button" href={href("compare")}>기간 비교</a>
          <button type="button" class="ui-button" disabled={selection.usable<5} title={selection.usable<5?"측정 5개 이상인 구간을 선택하세요":undefined} onclick={setReference}>비교 기준으로 사용</button>{/if}
        <button type="button" class="quiet" onclick={resume}>선택 해제</button>
      </nav>
    </aside>
  {/if}
  {#if reference&&read&&(!loading||comparison)&&(!error||comparison)}
    {#if comparison?.state==="ready"}
      {#if changes.length}<div class="changes" aria-label="기준 이후 달라진 구간">
        <span>달라진 구간 {changes.length}개</span>
        {#each changes.slice(0,3) as interval(interval.from)}<button type="button" onclick={()=>choose(interval)}
          title={spanText(interval)+" · "+measure(interval.value,comparison.unit,4)}>
          {new Date(interval.from).toLocaleTimeString("ko-KR",{timeZone:"Asia/Seoul",hour:"2-digit",minute:"2-digit",hourCycle:"h23"})}
          <strong>최대 {comparison.median!==null?difference(interval.value,comparison.median,comparison.unit):measure(interval.value,comparison.unit,4)}</strong>
          <small>{elapsedText((interval.to-interval.from)/1000)}</small>
        </button>{/each}
        {#if changes.length>3}<details><summary>다른 구간 {changes.length-3}개</summary><div class="changes">
          {#each changes.slice(3) as interval(interval.from)}<button type="button" onclick={()=>choose(interval)}>{spanText(interval)} · {measure(interval.value,comparison.unit,4)}</button>{/each}
        </div></details>{/if}
      </div>{:else}<p class="context">비교 기준 이후에 크게 달라진 구간이 없습니다.</p>{/if}
    {:else}<p class="context">{comparison?.state==="cumulative"?"누적값은 수준 변화로 비교하지 않습니다.":comparison?.state==="no-observations-after-reference"?"비교 기준을 적용했습니다. 이후 측정이 저장되면 비교합니다.":"이 기준으로 비교할 측정이 부족합니다. 더 긴 구간을 기준으로 선택하세요."}</p>{/if}
  {/if}
</section>
<style>
  .observation { display:grid; gap:var(--space-3); min-width:0; }
  .observation-head { display:flex; align-items:center; flex-wrap:wrap; gap:var(--space-4); }
  .signal { display:grid; gap:4px; min-width:200px; font-size:var(--font-label); }
  .signal select { max-width:100%; }
  .reading { display:flex; align-items:center; gap:var(--space-3); }
  .reading strong { font-size:2rem; font-weight:650; font-variant-numeric:tabular-nums; white-space:nowrap; }
  .reading>div { display:grid; gap:4px; }
  .reading span,.reading small { font-size:var(--font-label); color:var(--color-ink-muted); }
  .follow-state { margin-left:auto; display:flex; align-items:center; gap:var(--space-3); font-size:var(--font-label); color:var(--color-ink-muted); }
  .follow-state>span { display:inline-flex; align-items:center; gap:6px; }
  .following::before { content:""; width:6px; height:6px; border-radius:50%; background:var(--color-action); }
  .plot-toolbar { display:flex; flex-wrap:wrap; align-items:center; gap:var(--space-3); border-top:1px solid var(--color-border); padding-top:var(--space-3); }
  .choices { display:inline-flex; border:1px solid var(--color-control-border); border-radius:var(--radius-control); overflow:hidden; }
  .choices button { border:0; background:var(--color-surface); color:var(--color-ink); padding:6px 12px; font:inherit; font-size:var(--font-small); cursor:pointer; }
  .choices button+button { border-left:1px solid var(--color-border); }
  .choices button[aria-pressed="true"] { background:var(--color-surface-selected); color:var(--color-action); font-weight:650; }
  .time-context,.reference-context { font-size:var(--font-label); color:var(--color-ink-muted); }
  .reference-context { display:flex; align-items:center; gap:8px; margin-left:auto; }
  .quiet { color:var(--color-action); background:none; border:0; padding:6px; font:inherit; font-size:var(--font-small); cursor:pointer; white-space:nowrap; }
  .caption { display:flex; flex-wrap:wrap; justify-content:space-between; gap:8px; font-size:var(--font-label); color:var(--color-ink-muted); }
  .caption>span { display:inline-flex; align-items:center; gap:5px; }
  .reference-key,.change-key { display:inline-block; width:12px; height:10px; }
  .reference-key { border-top:2px dashed var(--color-ink-muted); height:0; }
  .change-key { background:var(--color-caution-ink); opacity:.2; margin-left:8px; }
  .selection { display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:var(--space-3); padding:var(--space-3); background:var(--color-surface-selected); border-radius:var(--radius-control); }
  .selection-reading { display:flex; align-items:center; gap:var(--space-4); }
  .selection-reading>div { display:grid; gap:4px; }
  .selection-reading span,.selection-reading small { color:var(--color-ink-muted); font-size:var(--font-label); }
  .selection-reading strong { font-size:1.35rem; font-weight:650; font-variant-numeric:tabular-nums; }
  .selection-actions { display:flex; align-items:center; flex-wrap:wrap; gap:var(--space-2); }
  .changes { display:flex; align-items:center; flex-wrap:wrap; gap:8px; font-size:var(--font-small); }
  .changes>span { color:var(--color-ink-muted); }
  .changes button { display:inline-flex; align-items:center; gap:8px; font:inherit; color:var(--color-action); background:none; border:1px solid var(--color-border); border-radius:var(--radius-control); padding:8px 10px; cursor:pointer; }
  .changes small { color:var(--color-ink-muted); }
  .context,.empty { margin:0; color:var(--color-ink-muted); font-size:var(--font-small); }
  .empty { padding:var(--space-5); }
  @media (max-width:900px) { .follow-state { margin-left:0; } .reference-context { margin-left:0; } }
</style>
