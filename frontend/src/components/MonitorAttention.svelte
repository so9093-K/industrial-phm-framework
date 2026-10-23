<script lang="ts">
  import {assetLabel, attentionLabel, type Snapshot, type OperationAttention} from "../monitor";
  import {assetTabUrl,routeUrl,systemUrl} from "../routes";
  import {onMount} from "svelte";
  import {attentionByAsset, attentionComplete, readDepartureStatus, readPhmMonitor, type AttentionState, type Departure, type PhmMonitor} from "../monitor-attention";
  import {readSources, type Sources} from "../operations-status";
  import StatusNotice from "./StatusNotice.svelte";

  /** What needs a look, read again every few seconds while this page is visible. A failed
   * read hides the earlier items rather than showing them as current. */
  type Props = {snapshot:Snapshot;onTick: () => Promise<void>; onNotes: (counts: Record<string, number>,state:AttentionState) => void};
  let {snapshot,onTick, onNotes}: Props = $props();
  const INTERVAL = 3000;
  // The guided demo replays a stored snapshot; reading it again would change nothing.
  const live = import.meta.env.MODE !== "showcase";
  let phm: PhmMonitor | null = $state(null);
  let sources: Sources | null = $state(null);
  // The baseline check reads stored history, so it is asked again only every 30 seconds; a
  // failed check drops its earlier items and is asked again on the next read.
  let departures: Departure[] = $state([]);
  let departuresFailed = $state(false);
  let departuresComplete = $state(false);
  let departuresAt = 0;
  let departuresCheckedAt: Date | null = $state(null);
  const DEPARTURE_INTERVAL = 30_000;
  let loadState: "loading" | "ready" | "failed" = $state("loading");
  let readAt: Date | null = $state(null);
  let sourcesCheckedAt: Date | null = $state(null);
  let paused = $state(false);
  let timer: ReturnType<typeof setTimeout> | null = null;
  let request: AbortController | null = null;
  const groups = $derived.by(() => {
    const current: PhmMonitor | null = phm, connections: Sources | null = sources;
    return current ? attentionByAsset(current.models, connections?.items ?? null, departures) : [];
  });
  const notesState = $derived.by((): AttentionState => {
    const current: PhmMonitor | null = phm, connections: Sources | null = sources;
    if (loadState === "loading") return "loading";
    if (!current || loadState === "failed") return "failed";
    return attentionComplete(current,connections,departuresComplete) ? "ready" : "partial";
  });
  $effect(() => { const model: PhmMonitor | null = phm; onNotes(Object.fromEntries([...(model?.models.map(item => [item.assetId, 0]) ?? []), ...groups.map(group => [group.assetId, group.notes.length])]),notesState); });
  const clock = (at: Date) => at.toLocaleString("ko-KR", {timeZone: "Asia/Seoul"});
  // The server's assessment time, so this panel and the page header name the same moment.
  const assessed = $derived.by((): Date | null => {
    const current: PhmMonitor | null = phm;
    const at = current?.assessedAt ? new Date(current.assessedAt) : readAt;
    return at && !Number.isNaN(at.getTime()) ? at : null;
  });

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
    if (live && !paused && !document.hidden) timer = setTimeout(() => void read(), INTERVAL);
  }
  async function read() {
    request?.abort();
    const pending = new AbortController(); request = pending;
    try {
      const due = Date.now() - departuresAt >= DEPARTURE_INTERVAL;
      const [model, connections, found] = await Promise.all([
        readPhmMonitor(pending.signal), readSources(pending.signal).catch(() => null),
        due ? readDepartureStatus(pending.signal).catch(() => null) : Promise.resolve(undefined), onTick()]);
      if (pending.signal.aborted) return;
      phm = model; sources = connections; loadState = "ready"; readAt = new Date();
      sourcesCheckedAt = connections === null ? null : new Date();
      if (found !== undefined) {
        departures = found?.items ?? []; departuresFailed = found === null;
        departuresComplete = found?.complete ?? false;
        departuresAt = found === null ? 0 : Date.now();
        departuresCheckedAt = found === null ? null : new Date();
      }
    } catch {
      if (pending.signal.aborted) return;
      phm = null; loadState = "failed";
    }
    schedule();
  }
  function toggle() { paused = !paused; if (paused) { if (timer !== null) clearTimeout(timer); timer = null; } else void read(); }
  onMount(() => {
    const visible = () => {
      if (document.hidden) {if (timer !== null) clearTimeout(timer); timer = null;}
      else {
        // After backgrounding, no former model or departure fact is claimed current.
        phm = null; sources = null; departures = []; departuresComplete = false;
        departuresFailed = false; departuresCheckedAt = null; departuresAt = 0;
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
  <li><strong>{attentionLabel(item)}</strong><span>{item.assetId ? assetLabel(snapshot.assets, item.assetId) : "공통 운영 서비스"}{item.sourceId?" · 데이터 출처 "+item.sourceId:""}{item.at?" · "+new Date(item.at).toLocaleString("ko-KR",{timeZone:"Asia/Seoul"}):""}</span>
    {#if destination(item)}<a href={destination(item)!}>상세 확인 →</a>{/if}</li>
{/snippet}

<section class="ui-panel attention" aria-labelledby="attention-title">
  <div class="head">
    <h2 id="attention-title">확인이 필요한 설비</h2>
    {#if live}<button type="button" class="ui-button" onclick={toggle}>{paused ? "자동 갱신 다시 시작" : "자동 갱신 멈추기"}</button>{/if}
  </div>
  <p class="context">{!live ? "저장된 체험 기록입니다." :
    (paused ? "자동 갱신을 멈췄습니다 · " : "") +
    "모델 평가 " + (assessed ? clock(assessed) : "확인 중") +
    " · 수신 조회 " + (sourcesCheckedAt ? clock(sourcesCheckedAt) : "미확인") +
    " · 기준 이탈 조회 " + (departuresCheckedAt ? clock(departuresCheckedAt) : "미확인")}</p>
  {#if live && !paused}<p class="context">모델·수신은 약 3초, 기준 이탈은 최대 30초 간격으로 별도 조회합니다.</p>{/if}
  {#if loadState === "loading"}
    <StatusNotice message="모델 처리 상태와 수신 상태를 확인하고 있습니다." />
  {:else if loadState === "failed" || !phm}
    <StatusNotice kind="uncertain" message="모델 처리 상태를 다시 읽지 못했습니다. 이전 결과를 지금 상태로 보여 주지 않습니다." />
  {:else}
    {#if sources === null}<StatusNotice kind="uncertain" message="데이터 연결 상태를 읽지 못해 수신 확인 항목은 빠져 있습니다." />{/if}
    {#if departuresFailed}<StatusNotice kind="uncertain" message="기준 구간 이탈을 확인하지 못해 해당 항목은 빠져 있습니다." />{/if}
    {#if !departuresFailed && !departuresComplete}<StatusNotice kind="uncertain" message="기준 구간 이탈을 일부만 확인했습니다." />{/if}
    {#if phm.truncated}<StatusNotice kind="uncertain" message="적용 모델이 많아 일부만 확인했습니다." />{/if}
    <!-- With nothing to check, one quiet line says so instead of an empty section per source. -->
    {#if serviceItems.length || dataItems.length || !snapshot.operationsAttention?.complete}
    <section aria-label="운영 확인 항목" class="operations-attention">
      <h3>운영 확인 항목</h3>
      {#if !snapshot.operationsAttention?.complete}<StatusNotice kind="uncertain" message="운영 확인 항목 전체를 읽지 못했습니다."/>{/if}
      {#if serviceItems.length}
        <h4>운영 서비스</h4><p class="context">수집·저장·분석 서비스의 처리 상태입니다.</p>
        <ul>{#each serviceItems as item (item.id)}{@render operation(item)}{/each}</ul>
      {/if}
      {#if dataItems.length}
        <h4>수신·데이터 품질</h4><p class="context">설비 데이터의 수신 상태와 품질을 확인합니다.</p>
        <ul>{#each dataItems as item (item.id)}{@render operation(item)}{/each}</ul>
      {/if}
    </section>
    {/if}
    {#if !groups.length}
      <p>{notesState !== "ready" ? "확인 항목을 일부만 읽었습니다. 미확인 항목이 남아 있습니다." : snapshot.operationsAttention?.items.length?"모델·수신 기준으로 확인할 추가 항목은 없습니다.":"지금 확인할 항목이 없습니다."}</p>
    {:else}
      {#if groups.some((group) => group.notes.some((note) => note.kind === "threshold" || note.kind === "crossing"))}
        <p class="context">모델 기준 초과는 학습한 평소 상태와 다르다는 뜻입니다. 항목을 열면 이유·근거·다음 행동을 봅니다.</p>
      {/if}
      <ul class="groups">
        {#each groups as group (group.assetId)}
          <li><article aria-labelledby={"attention-" + group.assetId}>
            <h3 id={"attention-" + group.assetId} tabindex="-1">{assetLabel(snapshot.assets, group.assetId)}</h3>
            <ul class="notes">
              {#each group.notes as note (note.id)}
                <li data-kind={note.kind}><strong>{note.label}</strong><span>{note.detail}</span>
                  <a href={note.href}>{note.action} →</a></li>
              {/each}
            </ul>
          </article></li>
        {/each}
      </ul>
    {/if}
  {/if}
</section>

<style>
  .attention { margin-bottom: var(--space-4); display: flex; flex-direction: column; gap: var(--space-3); min-width: 0; }
  .operations-attention{margin-block:var(--space-4);padding-block:var(--space-3);border-bottom:1px solid var(--color-border)}.operations-attention ul{padding-left:var(--space-4)}.operations-attention h4{margin:var(--space-3) 0 0}.operations-attention li{display:grid;gap:var(--space-2);padding-block:var(--space-2);overflow-wrap:anywhere}
  .head { display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--space-2) var(--space-4); align-items: center; }
  h2, h3 { margin: 0; }
  h3 { font-size: var(--font-section); overflow-wrap: anywhere; }
  p { margin: 0; overflow-wrap: anywhere; }
  .context { color: var(--color-ink-muted); font-size: var(--font-small); }
  .groups, .notes { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-2); }
  .groups > li { min-width: 0; }
  article { border: 1px solid var(--color-border); border-radius: var(--radius-control); padding: var(--space-3) var(--space-4);
    display: grid; gap: var(--space-2); }
  .notes li { display: flex; flex-wrap: wrap; gap: var(--space-1) var(--space-3); align-items: baseline; overflow-wrap: anywhere; }
  .notes span { color: var(--color-ink-muted); font-size: var(--font-small); }
  .notes li[data-kind="threshold"] strong, .notes li[data-kind="refusal"] strong, .notes li[data-kind="unavailable"] strong { color: var(--color-failure-ink); }
</style>
