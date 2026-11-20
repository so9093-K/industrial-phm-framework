<script lang="ts">
  import {untrack} from "svelte";
  import type {Asset} from "../monitor";
  import type {AssetData} from "../asset-data";
  import {sourceSummary,type Sources} from "../operations-status";
  import {streamKey} from "../observation";
  import AssetSummary from "./AssetSummary.svelte";
  import StatusNotice from "./StatusNotice.svelte";
  import RecentObservation from "./RecentObservation.svelte";
  let {asset,data,dataState,observed,sources,sourceState,cycle,onView,selectedAt=$bindable(null)}:{asset:Asset;data:AssetData|null;
    dataState:"loading"|"ready"|"failed";observed:(at:string|null)=>string;sources:Sources|null;
    sourceState:"loading"|"ready"|"failed";cycle:number;onView?:(view:"recent"|"record")=>void;selectedAt?:number|null}=$props();
  const params=new URLSearchParams(location.search);
  let view:"recent"|"record"|null=$state(params.get("observation_view")==="recent"?"recent":params.get("observation_view")==="record"?"record":null);
  let chosen=$state(params.has("monitor_source")?JSON.stringify([params.get("monitor_source"),params.get("monitor_point")||null]):"");
  let archiveRevision=$state(0);
  const streams=$derived(data?.history?.streams??[]);
  const stream=$derived(chosen?streams.find(row=>streamKey(row)===chosen)??null:[...streams].sort((a,b)=>Date.parse(b.endAt)-Date.parse(a.endAt))[0]??null);
  const source=$derived(sources?.items.find(row=>row.assetId===asset.assetId&&row.sourceId===stream?.sourceId));
  $effect(()=>{
    if(view!==null||dataState!=="ready")return;
    const latest=Math.max(...streams.map(row=>Date.parse(row.endAt)));
    const initial=!params.has("summary_change")&&streams.length>0&&latest>=Date.now()-3600_000?"recent":"record";
    untrack(()=>view=initial);
  });
  const displayView=$derived(view??(!params.has("summary_change")&&streams.some(row=>Date.parse(row.endAt)>=Date.now()-3600_000)?"recent":"record"));
  $effect(()=>onView?.(displayView));
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
    history.replaceState(history.state,"",url);view=next;
  }
  function chooseStream(key:string){
    const next=streams.find(row=>streamKey(row)===key);if(!next)return;
    choose("recent");chosen=key;
    const url=new URL(location.href);url.searchParams.set("monitor_source",next.sourceId);url.searchParams.set("monitor_point",next.pointId??"");history.replaceState(history.state,"",url);
  }
</script>
{#if streams.length}
  <div class="observation-entry"><div class="choices" role="group" aria-label="관측 보기">
    <button type="button" aria-pressed={displayView==="recent"} onclick={()=>choose("recent")}>최근 측정</button>
    <button type="button" aria-pressed={displayView==="record"} onclick={()=>choose("record")}>기록 변화 조사</button>
  </div>
  {#if displayView==="recent"&&(streams.length>1||!stream)}<label>측정 기록<select value={stream?streamKey(stream):""} onchange={e=>chooseStream(e.currentTarget.value)}>{#if !stream}<option value="" disabled>측정 기록 선택</option>{/if}{#each streams as row(streamKey(row))}<option value={streamKey(row)}>{sources?.items.find(s=>s.sourceId===row.sourceId&&s.assetId===asset.assetId)?.name??sourceSummary(row.sourceId,streams.map(item=>item.sourceId))}{row.pointId?" · "+row.pointId:""}</option>{/each}</select></label>
  {:else if displayView==="record"}<button type="button" class="ui-button" onclick={()=>archiveRevision++}>기록 다시 읽기</button>{/if}</div>
{/if}
{#if dataState==="loading"&&!data}<StatusNotice message="저장된 측정 목록을 읽고 있습니다."/>
{:else if displayView==="recent"&&stream}
  {#key streamKey(stream)}<RecentObservation assetId={asset.assetId} {stream} {source} preferred={data?.history?.preferred??null} sourceReadable={sourceState==="ready"} {cycle} {observed}/>{/key}
{:else if displayView==="recent"}<StatusNotice kind="uncertain" message={dataState==="failed"?"측정 기록을 불러오지 못했습니다.":"선택한 측정 기록을 찾지 못했습니다. 다른 기록을 선택하세요."}/>
{:else}
  {#key archiveRevision}<AssetSummary {asset} {data} {dataState} {observed} bind:selectedAt/>{/key}
{/if}
<style>
  .observation-entry{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:var(--space-3);margin-bottom:var(--space-3)}.choices{display:inline-flex;border:1px solid var(--color-control-border);border-radius:var(--radius-control);overflow:hidden}.choices button{border:0;background:var(--color-surface);color:var(--color-ink);padding:8px 14px;font:inherit;font-size:var(--font-small);cursor:pointer}.choices button+button{border-left:1px solid var(--color-border)}.choices button[aria-pressed="true"]{background:var(--color-surface-selected);color:var(--color-action);font-weight:650}label{display:flex;gap:8px;align-items:center;font-size:var(--font-small)}select{max-width:min(460px,65vw)}
</style>
