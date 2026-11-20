<script lang="ts">
  import {untrack,onDestroy} from "svelte";
  import {groupHistory,readSignalNames,signalName,signalChart,type SignalNames,type HistoryStream,type TrendWindow} from "../history";
  import {readObservation,readWindow,receiptStatus,observationLink,type Observation} from "../observation";
  import {pickFrom,summarize,type Span} from "../signal-selection";
  import {clockText} from "../asset-timeline";
  import {measure} from "../chart-axis";
  import type {Source} from "../operations-status";
  import ObservationChart from "./ObservationChart.svelte";
  import StatusNotice from "./StatusNotice.svelte";
  let {assetId,stream,source,sourceReadable,cycle,observed,preferred=null}:{assetId:string;stream:HistoryStream;source?:Source;
    sourceReadable:boolean;cycle:number;preferred?:string|null;observed:(at:string|null)=>string}=$props();
  const params=new URLSearchParams(location.search);
  const initialStream=untrack(()=>stream),initialPreferred=untrack(()=>preferred);
  const initialWindow=params.get("observation_follow")==="paused"?readWindow(params.get("monitor_from"),params.get("monitor_to")):null;
  const ranges=[{id:"15m",label:"15분"},{id:"1h",label:"1시간"},{id:"24h",label:"24시간"}];
  let channel=$state(params.has("monitor_channel")?params.get("monitor_channel")!:initialPreferred&&initialStream.channels.includes(initialPreferred)?initialPreferred:initialStream.channels[0]);
  let range=$state(ranges.some(r=>r.id===params.get("observation_range"))?params.get("observation_range")!:"1h");
  let window:TrendWindow|null=$state(initialWindow);
  let following=$state(initialWindow===null);
  const initialSnapshot=Number(params.get("observation_snapshot"));
  let snapshot:number|null=$state(initialWindow&&params.has("observation_snapshot")&&Number.isSafeInteger(initialSnapshot)&&initialSnapshot>=0?initialSnapshot:null);
  let reference:TrendWindow|null=$state(readWindow(params.get("observation_reference_from"),params.get("observation_reference_to")));
  let picked:Span|null=$state(initialWindow?pickFrom(params.get("monitor_pick")):null);
  let anchor:"now"|"latest"=$state(params.get("observation_anchor")==="now"||(!params.has("observation_anchor")&&Date.parse(initialStream.endAt)>Date.now()-3600_000)?"now":"latest");
  let read:Observation|null=$state(null),names:SignalNames=$state(new Map()),loading=$state(false),error=$state("");
  let request:AbortController|null=null,loadedKey="";
  onDestroy(()=>request?.abort());
  const queryKey=$derived(JSON.stringify([channel,range,window,snapshot,reference,anchor]));
  const groups=$derived.by(()=>{const current:Observation|null=read;return current?groupHistory(current.trend):[];});
  const group=$derived([...groups].sort((a,b)=>Date.parse(b.buckets.at(-1)?.lastEventAt??b.buckets.at(-1)?.bucketStart??"")-Date.parse(a.buckets.at(-1)?.lastEventAt??a.buckets.at(-1)?.bucketStart??""))[0]??null);
  const latest=$derived.by(()=>{const current:Observation|null=read;return current?.trend.latest[0]??null;});
  const unit=$derived(latest?.unit??group?.unit??null);
  const comparison=$derived.by(()=>{const current:Observation|null=read;return group?current?.reference?.groups.find(item=>item.interpretationId===group.interpretationId&&item.unit===group.unit)??null:null;});
  const changes=$derived([...(comparison?.intervals??[])].sort((a,b)=>b.from-a.from));
  const chart=$derived.by(()=>{const current:Observation|null=read;return current&&group?signalChart(group,current.trend.startAt,current.trend.endAt,current.trend.bucketSeconds,{start:Date.parse(current.trend.startAt),height:280}):null;});
  const selection=$derived(group&&picked?summarize(group,picked):null);
  const label=$derived(signalName(names,channel));
  function remember(){
    const url=new URL(location.href),q=url.searchParams;
    q.set("observation_view","recent");q.set("observation_follow",following?"following":"paused");q.set("observation_range",range);q.set("observation_anchor",anchor);
    q.set("monitor_channel",channel);q.set("monitor_source",stream.sourceId);q.set("monitor_point",stream.pointId??"");
    if(window){q.set("monitor_range","window");q.set("monitor_from",window.from);q.set("monitor_to",window.to);}else{q.delete("monitor_from");q.delete("monitor_to");q.set("monitor_range",range);}
    if(snapshot!==null)q.set("observation_snapshot",String(snapshot));else q.delete("observation_snapshot");
    if(picked){q.set("monitor_pick",new Date(picked.from).toISOString()+"~"+new Date(picked.to).toISOString());}else q.delete("monitor_pick");
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
    window={from:read.trend.startAt,to:read.trend.endAt};snapshot=read.trend.snapshotId??null;following=false;
    loadedKey=queryKey;remember();
  }
  function choose(span:Span){freeze();picked=span;remember();}
  function resume(){picked=null;window=null;snapshot=null;following=true;remember();}
  function changeChannel(value:string){request?.abort();read=null;picked=null;reference=null;channel=value;remember();}
  function changeRange(value:string){range=value;resume();}
  function setReference(){if(!picked)return;reference={from:new Date(picked.from).toISOString(),to:new Date(picked.to).toISOString()};remember();}
  function href(method:"signals"|"compare"|"relation"){
    if(!picked||!read||!group)return "";
    const url=new URL(observationLink(assetId,channel,stream,group.interpretationId,{from:Date.parse(read.trend.startAt),to:Date.parse(read.trend.endAt)},picked,reference,method,label),location.origin);
    url.searchParams.set("observation_snapshot",String(read.trend.snapshotId));url.searchParams.set("observation_range",range);url.searchParams.set("observation_anchor",anchor);
    if(reference){url.searchParams.set("observation_reference_from",reference.from);url.searchParams.set("observation_reference_to",reference.to);}
    return url.pathname+url.search;
  }
</script>
<section class="ui-panel observation" aria-label="최근 저장 측정 관측">
  <header><label class="signal">조사할 신호<select value={channel} onchange={e=>changeChannel(e.currentTarget.value)}>{#if !stream.channels.includes(channel)}<option value={channel} disabled>다른 신호 선택</option>{/if}{#each stream.channels as id(id)}<option value={id}>{signalName(names,id)}</option>{/each}</select></label>
    <div class="mode"><span>{following?"최근 기록 따라보기":"선택 구간 조사 중"}</span>{#if !following}<button type="button" class="ui-button" onclick={resume}>최근 관측으로</button>{/if}</div>
  </header>
  <div class="reading"><div><span>{picked?"선택 구간 평균":"마지막 저장 측정"} · {label}</span><strong>{picked?selection?.mean!=null?measure(selection.mean,group?.unit??null):"—":latest?.usable&&latest.value!==null?measure(latest.value,unit):"—"}</strong></div>
    <div class="when"><span>{picked?observed(new Date(picked.from).toISOString())+" ~ "+clockText(picked.to):latest?.eventAt?observed(latest.eventAt):"저장된 측정 없음"}</span>
      {#if picked}<small>{selection?.usable?"실제 측정 "+selection.usable+"개":"선택 구간에 비교할 측정 없음"} · 마지막 저장 측정 {latest?.usable&&latest.value!==null?measure(latest.value,unit):"미확인"}</small>
      {:else}<small>{receiptStatus(source,sourceReadable)}{following?" · 새 저장 기록 1분마다 확인":""}</small>{/if}</div></div>
  {#if picked}
    <nav class="selection-actions" aria-label="선택 구간 조사">{#if selection?.mean!=null}<a class="ui-button ui-button-primary" href={href("signals")}>실측 신호 조사 →</a><a class="ui-button" href={href("compare")}>기간 비교</a>{#if stream.channels.length>1}<a class="ui-button" href={href("relation")}>다른 신호와 관계</a>{/if}<button type="button" class="ui-button" onclick={setReference}>이 구간을 비교 기준으로</button>{/if}</nav>
  {:else}
    <div class="toolbar"><div class="choices" role="group" aria-label="관측 범위">{#each ranges as item(item.id)}<button type="button" aria-pressed={range===item.id} onclick={()=>changeRange(item.id)}>{item.label}</button>{/each}</div>
      <label>시간 기준<select bind:value={anchor} onchange={()=>{read=null;resume();}}><option value="now">현재 시각</option><option value="latest">마지막 측정 시각</option></select></label>
      <button type="button" class="ui-button" disabled={loading} onclick={()=>void refresh()}>다시 읽기</button>
    </div>
  {/if}
  {#if error}<StatusNotice kind="uncertain" message={error+(read?" 마지막으로 읽은 관측을 유지합니다.":"")} actionLabel="다시 시도" onAction={()=>void refresh()}/>{/if}
  {#if chart&&read}
    <ObservationChart {chart} origin={Date.parse(read.trend.startAt)} step={read.trend.bucketSeconds?read.trend.bucketSeconds*1000:null} {unit} {label} {picked}
      reference={reference?{from:Date.parse(reference.from),to:Date.parse(reference.to)}:null} intervals={comparison?.intervals??[]} onFreeze={freeze} onSelect={choose}/>
    <div class="caption"><span>구간 평균 · 최소–최대 범위 · 공백은 측정 없음</span><span>{reference?"옅은 파랑: 비교 기준 · 음영: 기준보다 달라진 구간":"점을 선택하거나 드래그해 구간 조사"}</span></div>
  {:else if loading}<StatusNotice message="저장된 최근 측정을 읽고 있습니다."/>
  {:else if read}<p class="empty">이 범위에 그릴 측정이 없습니다. 마지막 측정 시각과 데이터 연결 상태를 확인하세요.</p>{/if}
  {#if reference}<div class="reference"><span>비교 기준 · {clockText(Date.parse(reference.from))} ~ {clockText(Date.parse(reference.to))}{#if comparison?.median!==null&&comparison?.median!==undefined} · 대표값 {measure(comparison.median,comparison.unit)}{/if}</span><button type="button" class="ui-button" onclick={()=>{reference=null;remember();}}>비교 기준 해제</button></div>
    {#if comparison?.state==="ready"}{#if comparison.intervals.length}<div class="changes" aria-label="이번 관측에서 달라진 구간">{#each changes.slice(0,3) as interval(interval.from)}<button type="button" onclick={()=>choose(interval)}>{clockText(interval.from)}부터 기준보다 {interval.up?"높음":"낮음"} · {measure(interval.value,comparison.unit)} →</button>{/each}</div>{#if changes.length>3}<details class="more-changes"><summary>이 범위의 다른 변화 {changes.length-3}개</summary><div class="changes">{#each changes.slice(3) as interval(interval.from)}<button type="button" onclick={()=>choose(interval)}>{clockText(interval.from)}부터 기준보다 {interval.up?"높음":"낮음"} · {measure(interval.value,comparison.unit)} →</button>{/each}</div></details>{/if}{:else}<p class="context">비교 기준 이후의 구간 평균에서 큰 차이를 찾지 못했습니다.</p>{/if}
    {:else}<p class="context">{comparison?.state==="cumulative"?"누적값은 수준 변화로 판단하지 않습니다.":comparison?.state==="no-observations-after-reference"?"비교 기준 이후의 새 측정을 기다립니다.":"같은 측정 조건으로 비교할 기록이 충분하지 않습니다."}</p>{/if}
  {/if}
</section>
<style>
  .observation{display:grid;gap:var(--space-3);min-width:0}header,.reading,.toolbar,.reference{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:var(--space-3)}header .signal{min-width:220px;display:grid;gap:4px;font-size:var(--font-label)}.mode{display:flex;gap:var(--space-3);align-items:center;color:var(--color-ink-muted);font-size:var(--font-small)}.reading{justify-content:flex-start;gap:var(--space-5)}.reading>div:first-child{display:grid;gap:4px}.reading span{font-size:var(--font-small);color:var(--color-ink-muted)}.reading strong{font-size:2rem;font-weight:650;font-variant-numeric:tabular-nums}.when{display:grid;gap:5px}.when small{font-size:var(--font-label);color:var(--color-ink-muted)}.toolbar{justify-content:flex-start;border-top:1px solid var(--color-border);padding-top:var(--space-3);font-size:var(--font-small)}.toolbar label{display:flex;gap:8px;align-items:center}.choices{display:inline-flex;border:1px solid var(--color-control-border);border-radius:var(--radius-control);overflow:hidden}.choices button{border:0;background:var(--color-surface);font:inherit;color:var(--color-ink);padding:6px 12px}.choices button+button{border-left:1px solid var(--color-border)}.choices button[aria-pressed="true"]{background:var(--color-surface-selected);color:var(--color-action);font-weight:650}.caption{display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px;font-size:var(--font-label);color:var(--color-ink-muted)}p{margin:0}.selection-actions{display:flex;flex-wrap:wrap;gap:var(--space-2);border-top:1px solid var(--color-border);padding-top:var(--space-3)}.reference,.context{font-size:var(--font-small);color:var(--color-ink-muted)}.changes{display:flex;flex-wrap:wrap;gap:8px}.changes button{font:inherit;font-size:var(--font-small);color:var(--color-action);background:none;border:1px solid var(--color-border);border-radius:var(--radius-control);padding:8px;cursor:pointer}.empty{color:var(--color-ink-muted);padding:var(--space-5)}select{max-width:100%}
</style>
