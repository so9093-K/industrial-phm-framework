<script lang="ts">
  import {untrack} from "svelte";
  import type {Asset} from "../monitor";
  import type {AssetData} from "../asset-data";
  import {sourceSummary,type Sources} from "../operations-status";
  import {streamKey} from "../observation";
  import RecordPlayback from "./RecordPlayback.svelte";
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
  let archiveRevision=$state(0);
  let scope:PlaybackScope|null=$state(playbackScope(location.search)), replayBusy=$state(false),playing=$state(false);
  let selectedKind=$state<"history"|"vibration"|null>(untrack(()=>scope?.kind??null));
  const replayKind=$derived(selectedKind??(data?.history&&!data.vibration?"history":!data?.history&&data?.vibration?"vibration":null));
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
<!-- 보기 전환과 모니터링 조작은 한 줄: 그래프보다 조작이 먼저 오지 않게 한다. -->
<div class="entry-row">
{#if streams.length}
  <div class="observation-entry"><div class="choices" role="group" aria-label="관측 보기">
    <button type="button" aria-pressed={displayView==="recent"} onclick={()=>choose("recent")}>최근 측정</button>
    <button type="button" aria-pressed={displayView==="record"} onclick={()=>choose("record")}>기록 변화 조사</button>
  </div>
  {#if displayView==="recent"&&(streams.length>1||!stream)}<label>측정 기록<select value={stream?streamKey(stream):""} onchange={e=>chooseStream(e.currentTarget.value)}>{#if !stream}<option value="" disabled>측정 기록 선택</option>{/if}{#each streams as row(streamKey(row))}<option value={streamKey(row)}>{sources?.items.find(s=>s.sourceId===row.sourceId&&s.assetId===asset.assetId)?.name??sourceSummary(row.sourceId,streams.map(item=>item.sourceId))}{row.pointId?" · "+row.pointId:""}</option>{/each}</select></label>
  {/if}</div>
{/if}
{#if displayView==="record"&&!(dataState==="loading"&&!data)}
  {#if data?.history&&data.vibration}<label class="kind-choice">모니터링할 기록<select value={replayKind??""} onchange={e=>{playing=false;scope=null;selectedKind=e.currentTarget.value as "history"|"vibration";}}><option value="" disabled>기록 종류 선택</option><option value="history">시간별 계측</option><option value="vibration">진동 측정</option></select></label>{/if}
  {#if replayKind&&Number.isFinite(replayFrom)&&replayTo>replayFrom}<div class="record-transport"><RecordPlayback kind={replayKind} from={replayFrom} to={replayTo} bind:scope bind:playing busy={replayBusy} onRefresh={()=>archiveRevision++}/></div>{/if}
  {/if}
</div>
{#if dataState==="loading"&&!data}<StatusNotice message="저장된 측정 목록을 읽고 있습니다."/>
{:else if displayView==="recent"&&stream}
  {#key streamKey(stream)}<RecentObservation assetId={asset.assetId} {stream} {source} preferred={data?.history?.preferred??null} sourceReadable={sourceState==="ready"} {cycle} {observed}/>{/key}
{:else if displayView==="recent"}<StatusNotice kind="uncertain" message={dataState==="failed"?"측정 기록을 불러오지 못했습니다.":"선택한 측정 기록을 찾지 못했습니다. 다른 기록을 선택하세요."}/>
{:else}
  <AssetSummary {asset} data={scopedData} {dataState} {observed} {scope} {playing} revision={archiveRevision} bind:selectedAt onBusy={(value)=>replayBusy=value} onInvestigate={()=>playing=false}/>
{/if}
<style>
  .entry-row{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:var(--space-2) var(--space-4);margin-bottom:var(--space-3)}
  .record-transport{flex:1;min-width:min(100%,520px);max-width:820px}
  .record-transport :global(.ui-button){min-height:0;padding:6px 12px;font-size:var(--font-small)}
  .record-transport :global(select){padding:5px 8px;font-size:var(--font-label)}

  .observation-entry{display:flex;align-items:center;flex-wrap:wrap;gap:var(--space-3)}.choices{display:inline-flex;border:1px solid var(--color-control-border);border-radius:var(--radius-control);overflow:hidden}.choices button{border:0;background:var(--color-surface);color:var(--color-ink);padding:6px 12px;font:inherit;font-size:var(--font-small);cursor:pointer}.choices button+button{border-left:1px solid var(--color-border)}.choices button[aria-pressed="true"]{background:var(--color-surface-selected);color:var(--color-action);font-weight:650}label{display:flex;gap:8px;align-items:center;font-size:var(--font-small)}select{max-width:min(460px,65vw)}
</style>
