<script lang="ts">
  import {readableSourceId} from "../operations-status";
  import {assetLabel, attentionLabel, type Snapshot, type OperationAttention} from "../monitor";
  import {assetTabUrl,routeUrl,systemUrl} from "../routes";
  import {onMount} from "svelte";
  import {assetChecks, attentionByAsset, attentionComplete, readPhmMonitor, type AssetChecks, type AttentionState, type PhmMonitor} from "../monitor-attention";
  import {readSources, type Sources} from "../operations-status";
  import StatusNotice from "./StatusNotice.svelte";

  /** 설비별 수신·처리 상태를 화면이 보이는 동안 1분마다 다시 읽어 표에 넘기고,
   * 여기에는 운영 서비스·수신 품질 항목만 보여 준다. 읽지 못하면 이전 항목을 지금 것처럼 남기지 않는다. */
  type Props = {snapshot:Snapshot;onTick: () => Promise<void>; onChecks: (checks: AssetChecks) => void; onSources?:(sources:Sources|null,state:"loading"|"ready"|"failed")=>void};
  let {snapshot,onTick, onChecks,onSources}: Props = $props();
  const INTERVAL = 60_000;
  let phm: PhmMonitor | null = $state(null);
  let sources: Sources | null = $state(null);
  let loadState: "loading" | "ready" | "failed" = $state("loading");
  let sourcesCheckedAt: Date | null = $state(null);
  let timer: ReturnType<typeof setTimeout> | null = null;
  let request: AbortController | null = null;
  const groups = $derived.by(() => {
    const current: PhmMonitor | null = phm, connections: Sources | null = sources;
    return current ? attentionByAsset(current.models, connections?.items ?? null) : [];
  });
  const notesState = $derived.by((): AttentionState => {
    const current: PhmMonitor | null = phm, connections: Sources | null = sources;
    if (loadState === "loading") return "loading";
    if (!current || loadState === "failed") return "failed";
    return attentionComplete(current,connections,true) ? "ready" : "partial";
  });
  $effect(() => { const model: PhmMonitor | null = phm; onChecks(assetChecks(model?.models ?? [], groups, notesState)); });
  const clock = (at: Date) => at.toLocaleString("ko-KR", {timeZone: "Asia/Seoul"});
  $effect(()=>onSources?.(sources,loadState==="loading"?"loading":loadState==="failed"||sources===null?"failed":"ready"));
  const serviceItems = $derived((snapshot.operationsAttention?.items ?? []).filter((item) => item.destination === "system"));
  const dataItems = $derived((snapshot.operationsAttention?.items ?? []).filter((item) => item.destination !== "system"));
  function destination(item:OperationAttention):string|null {
    if(item.destination==="system")return systemUrl("status");
    if(item.destination==="asset-signals"&&item.assetId)return assetTabUrl(item.assetId,"signals");
    if(item.destination==="investigations")return routeUrl({page:"investigations",assetId:item.assetId??"",tab:"summary",method:null,data:null});
    return null;
  }
  function schedule() {
    if (timer !== null) clearTimeout(timer);
    timer = null;
    if (!document.hidden) timer = setTimeout(() => void read(), INTERVAL);
  }
  async function read() {
    request?.abort();
    const pending = new AbortController(); request = pending;
    try {
      const [model, connections] = await Promise.all([
        readPhmMonitor(pending.signal), readSources(pending.signal).catch(() => null), onTick()]);
      if (pending.signal.aborted) return;
      phm = model; sources = connections; loadState = "ready";
      sourcesCheckedAt = connections === null ? null : new Date();
    } catch {
      if (pending.signal.aborted) return;
      phm = null; sources = null; loadState = "failed";
      sourcesCheckedAt = null;
    }
    schedule();
  }
  onMount(() => {
    const visible = () => {
      if (document.hidden) {if (timer !== null) clearTimeout(timer); timer = null;}
      else {
        phm = null; sources = null;
        sourcesCheckedAt = null; loadState = "loading";
        void read();
      }
    };
    document.addEventListener("visibilitychange", visible);
    void read();
    return () => { document.removeEventListener("visibilitychange", visible); request?.abort(); if (timer !== null) clearTimeout(timer); };
  });
</script>

{#snippet operation(item: OperationAttention)}
  <li><strong>{attentionLabel(item)}</strong><span>{item.assetId ? assetLabel(snapshot.assets, item.assetId) : "공통 운영 서비스"}{item.sourceId?" · 데이터 출처 "+readableSourceId(item.sourceId):""}{item.at?" · "+new Date(item.at).toLocaleString("ko-KR",{timeZone:"Asia/Seoul"}):""}</span>
    {#if destination(item)}<a href={destination(item)!}>상세 확인 →</a>{/if}</li>
{/snippet}

<section class="ui-panel attention" aria-label="운영 확인 항목">
  <div class="head">
    <p class="context">수집·처리 상태 확인 {sourcesCheckedAt ? clock(sourcesCheckedAt) : "중"} · 약 1분마다 확인</p>
  </div>
  {#if loadState === "loading"}
    <StatusNotice message="모델 처리 상태와 수신 상태를 확인하고 있습니다." />
  {:else if loadState === "failed" || !phm}
    <StatusNotice kind="uncertain" message="모델 처리 상태를 다시 읽지 못했습니다. 이전 결과를 지금 상태로 보여 주지 않습니다." />
  {:else}
    {#if sources === null}<StatusNotice kind="uncertain" message="데이터 연결 상태를 읽지 못해 수신 확인 항목은 빠져 있습니다." />{/if}
    {#if phm.truncated}<StatusNotice kind="uncertain" message="적용 모델이 많아 일부만 확인했습니다." />{/if}
  {/if}
  {#if !snapshot.operationsAttention?.complete}<StatusNotice kind="uncertain" message="운영 확인 항목 전체를 읽지 못했습니다."/>{/if}
  {#if serviceItems.length}
    <h3>운영 서비스</h3>
    <ul>{#each serviceItems as item (item.id)}{@render operation(item)}{/each}</ul>
  {/if}
  {#if dataItems.length}
    <h3>수신·데이터 품질</h3>
    <ul>{#each dataItems as item (item.id)}{@render operation(item)}{/each}</ul>
  {/if}
  {#if !serviceItems.length && !dataItems.length && snapshot.operationsAttention?.complete !== false}<p>운영 확인 항목 없음</p>{/if}
</section>

<style>
  .attention { margin-bottom: var(--space-4); display: flex; flex-direction: column; gap: var(--space-3); min-width: 0; }
  .head { display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--space-2) var(--space-4); align-items: center; }
  h3 { margin: var(--space-2) 0 0; font-size: var(--font-body); }
  p { margin: 0; overflow-wrap: anywhere; }
  .context { color: var(--color-ink-muted); font-size: var(--font-small); }
  ul { margin: 0; padding-left: var(--space-4); }
  li { display: grid; gap: var(--space-2); padding-block: var(--space-2); overflow-wrap: anywhere; }
</style>
