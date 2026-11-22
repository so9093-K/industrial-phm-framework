<script lang="ts">
  import {untrack} from "svelte";
  import type {Asset} from "../monitor";
  import type {AssetData} from "../asset-data";
  import {sourceSummary,type Sources} from "../operations-status";
  import {clockText} from "../asset-timeline";
  import {streamKey} from "../observation";
  import {playbackScope, scopeParams, type PlaybackScope} from "../record-playback";
  import AssetSummary from "./AssetSummary.svelte";
  import StatusNotice from "./StatusNotice.svelte";
  import RecentObservation from "./RecentObservation.svelte";
  let {asset,data,dataState,observed,sources,sourceState,cycle,selectedAt=$bindable(null)}:{asset:Asset;data:AssetData|null;
    dataState:"loading"|"ready"|"failed";observed:(at:string|null)=>string;sources:Sources|null;
    sourceState:"loading"|"ready"|"failed";cycle:number;selectedAt?:number|null}=$props();
  const params=new URLSearchParams(location.search);
  let view:"recent"|"record"|null=$state(params.get("observation_view")==="recent"?"recent":params.get("observation_view")==="record"?"record":null);
  const sourcePrefix=params.get("observation_asset")===untrack(()=>asset.assetId)?"observation_":"monitor_";
  let chosen=$state(params.has(sourcePrefix+"source")?JSON.stringify([params.get(sourcePrefix+"source"),params.get(sourcePrefix+"point")||null]):"");
  const streams=$derived(data?.history?.streams??[]);
  // 관제 모니터링 중 들어오면 그 시점까지의 기록(scope)으로 조사한다. 재생 조작은 관제 화면에만 있다.
  let scope:PlaybackScope|null=$state(playbackScope(location.search)), replayBusy=$state(false);
  const replayKind=$derived(scope?.kind??(data?.history&&!data.vibration?"history":!data?.history&&data?.vibration?"vibration":null));
  const scopedData=$derived(scope&&data?{...data,...(scope.kind==="history"?{vibration:null}:{history:null})}:data);
  const replayFrom=$derived(replayKind==="history"?Math.min(...streams.map(s=>Date.parse(s.startAt))):data?.vibration?.first??0);
  const replayTo=$derived(replayKind==="history"?Math.max(...streams.map(s=>Date.parse(s.endAt)))+1000:data?.vibration?.last??0);
  $effect(()=>{
    const current=scope;
    const url=new URL(location.href);
    url.searchParams.delete("record_until");url.searchParams.delete("acquisition_until");
    for(const [key,value] of Object.entries(scopeParams(current)))url.searchParams.set(key,value);
    history.replaceState(history.state,"",url);
  });

  const stream=$derived(chosen?streams.find(row=>streamKey(row)===chosen)??null:[...streams].sort((a,b)=>Date.parse(b.endAt)-Date.parse(a.endAt))[0]??null);
  const source=$derived(sources?.items.find(row=>row.assetId===asset.assetId&&row.sourceId===stream?.sourceId));
  $effect(()=>{
    if(view!==null||dataState!=="ready")return;
    const latest=Math.max(...streams.map(row=>Date.parse(row.endAt)));
    const initial=!params.has("summary_change")&&streams.length>0&&latest>=Date.now()-3600_000?"recent":"record";
    untrack(()=>view=initial);
  });
  const displayView=$derived(view??(!params.has("summary_change")&&streams.some(row=>Date.parse(row.endAt)>=Date.now()-3600_000)?"recent":"record"));
  // '최근 측정'은 지금 받고 있는 측정(최근 1시간)이 있을 때만 뜻이 있다. 저장된 과거 기록에서는 전환을 두지 않는다.
  const receiving=$derived(streams.some(row=>Date.parse(row.endAt)>=Date.now()-3600_000));
  const place=(n:number)=>replayKind==="history"?clockText(n):Math.floor(n)+"번째 측정";
  $effect(()=>{
    if(displayView!=="recent"||!stream||chosen)return;
    const current=stream;
    untrack(()=>{
      chosen=streamKey(current);
      const url=new URL(location.href);url.searchParams.set("monitor_source",current.sourceId);url.searchParams.set("monitor_point",current.pointId??"");
      history.replaceState(history.state,"",url);
    });
  });
  function choose(next:"recent"|"record"){
    const url=new URL(location.href);
    for(const key of [...url.searchParams.keys()])if(key.startsWith("summary_")||key.startsWith("compare_")||key.startsWith("monitor_")&&key!=="monitor_asset"||key.startsWith("observation_"))url.searchParams.delete(key);
    url.searchParams.set("observation_view",next);
    if(next==="recent"&&stream){url.searchParams.set("monitor_source",stream.sourceId);url.searchParams.set("monitor_point",stream.pointId??"");}
    scope=null;history.replaceState(history.state,"",url);view=next;
  }
  function chooseStream(key:string){
    const next=streams.find(row=>streamKey(row)===key);if(!next)return;
    choose("recent");chosen=key;
    const url=new URL(location.href);url.searchParams.set("monitor_source",next.sourceId);url.searchParams.set("monitor_point",next.pointId??"");history.replaceState(history.state,"",url);
  }
</script>
<!-- 보기 전환과 기록 범위는 한 줄: 그래프보다 조작이 먼저 오지 않게 한다. -->
<div class="entry-row">
{#if streams.length&&(receiving||displayView==="recent")}
  <div class="observation-entry"><div class="choices" role="group" aria-label="관측 보기">
    <button type="button" aria-pressed={displayView==="recent"} onclick={()=>choose("recent")}>최근 측정</button>
    <button type="button" aria-pressed={displayView==="record"} onclick={()=>choose("record")}>기록 변화 조사</button>
  </div>
  {#if displayView==="recent"&&(streams.length>1||!stream)}<label>측정 기록<select value={stream?streamKey(stream):""} onchange={e=>chooseStream(e.currentTarget.value)}>{#if !stream}<option value="" disabled>측정 기록 선택</option>{/if}{#each streams as row(streamKey(row))}<option value={streamKey(row)}>{sources?.items.find(s=>s.sourceId===row.sourceId&&s.assetId===asset.assetId)?.name??sourceSummary(row.sourceId,streams.map(item=>item.sourceId))}{row.pointId?" · "+row.pointId:""}</option>{/each}</select></label>
  {/if}</div>
{/if}
{#if displayView==="record"&&!(dataState==="loading"&&!data)&&replayKind&&Number.isFinite(replayFrom)&&replayTo>replayFrom}
  {#if scope}<p class="span" aria-busy={replayBusy}>모니터링 시점 <b>{place(scope.until)}</b>까지의 기록{replayBusy?" · 읽는 중":""}
    <button type="button" class="whole" onclick={()=>scope=null}>전체 기록 보기</button></p>
  {:else}<p class="span" aria-busy={replayBusy}>{place(replayFrom)} — {place(replayTo-(replayKind==="history"?1000:0))}{replayBusy?" · 읽는 중":""}</p>{/if}
{/if}
</div>
{#if dataState==="loading"&&!data}<StatusNotice message="저장된 측정 목록을 읽고 있습니다."/>
{:else if displayView==="recent"&&stream}
  {#key streamKey(stream)}<RecentObservation assetId={asset.assetId} {stream} {source} preferred={data?.history?.preferred??null} sourceReadable={sourceState==="ready"} {cycle} {observed}/>{/key}
{:else if displayView==="recent"}<StatusNotice kind="uncertain" message={dataState==="failed"?"측정 기록을 불러오지 못했습니다.":"선택한 측정 기록을 찾지 못했습니다. 다른 기록을 선택하세요."}/>
{:else}
  <AssetSummary {asset} data={scopedData} {dataState} {observed} {scope} bind:selectedAt onBusy={(value)=>replayBusy=value}/>
{/if}
<style>
  .entry-row{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:var(--space-2) var(--space-4);margin-bottom:var(--space-3)}
  .span{margin:0 0 0 auto;font-size:var(--font-small);color:var(--color-ink-muted);font-variant-numeric:tabular-nums}
  .span b{color:var(--color-ink);font-weight:650}
  .whole{margin-left:8px;border:0;background:none;padding:0;font:inherit;color:var(--color-action);text-decoration:underline;cursor:pointer}

  .observation-entry{display:flex;align-items:center;flex-wrap:wrap;gap:var(--space-3)}.choices{display:inline-flex;border:1px solid var(--color-control-border);border-radius:var(--radius-control);overflow:hidden}.choices button{border:0;background:var(--color-surface);color:var(--color-ink);padding:6px 12px;font:inherit;font-size:var(--font-small);cursor:pointer}.choices button+button{border-left:1px solid var(--color-border)}.choices button[aria-pressed="true"]{background:var(--color-surface-selected);color:var(--color-action);font-weight:650}label{display:flex;gap:8px;align-items:center;font-size:var(--font-small)}select{max-width:min(460px,65vw)}
</style>
