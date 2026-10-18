<script lang="ts">
  import type {Snapshot,OperationAttention} from "../monitor";
  import {assetTabUrl,routeUrl,systemUrl} from "../routes";
  import {onMount} from "svelte";
  import {attentionByAsset, readPhmMonitor, type PhmMonitor} from "../monitor-attention";
  import {readSources, type Sources} from "../operations-status";
  import StatusNotice from "./StatusNotice.svelte";

  /** What needs a look, read again every few seconds while this page is visible. A failed
   * read hides the earlier items rather than showing them as current. */
  type Props = {snapshot:Snapshot;onTick: () => Promise<void>; onNotes: (counts: Record<string, number>) => void};
  let {snapshot,onTick, onNotes}: Props = $props();
  const INTERVAL = 3000;
  let phm: PhmMonitor | null = $state(null);
  let sources: Sources | null = $state(null);
  let loadState: "loading" | "ready" | "failed" = $state("loading");
  let readAt: Date | null = $state(null);
  let paused = $state(false);
  let timer: ReturnType<typeof setTimeout> | null = null;
  let request: AbortController | null = null;
  const groups = $derived.by(() => {
    const current: PhmMonitor | null = phm, connections: Sources | null = sources;
    return current ? attentionByAsset(current.models, connections?.items ?? null) : [];
  });
  // The asset list counts these too, so the two never disagree; a failed read counts nothing.
  $effect(() => { const model: PhmMonitor | null = phm; onNotes(Object.fromEntries([...(model?.models.map(item => [item.assetId, 0]) ?? []), ...groups.map(group => [group.assetId, group.notes.length])])); });
  const clock = (at: Date) => at.toLocaleTimeString("ko-KR", {timeZone: "Asia/Seoul"});

  function destination(item:OperationAttention):string|null {
    if(item.destination==="system")return systemUrl("status");
    if(item.destination==="asset-signals"&&item.assetId)return assetTabUrl(item.assetId,"signals");
    if(item.destination==="investigations")return routeUrl({page:"investigations",assetId:item.assetId??"",tab:"summary",method:null,data:null});
    return null;
  }
  function schedule() {
    if (timer !== null) clearTimeout(timer);
    timer = null;
    if (!paused && !document.hidden) timer = setTimeout(() => void read(), INTERVAL);
  }
  async function read() {
    request?.abort();
    const pending = new AbortController(); request = pending;
    try {
      const [model, connections] = await Promise.all([
        readPhmMonitor(pending.signal), readSources(pending.signal).catch(() => null), onTick()]);
      if (pending.signal.aborted) return;
      phm = model; sources = connections; loadState = "ready"; readAt = new Date();
    } catch {
      if (pending.signal.aborted) return;
      phm = null; loadState = "failed";
    }
    schedule();
  }
  function toggle() { paused = !paused; if (paused) { if (timer !== null) clearTimeout(timer); timer = null; } else void read(); }
  onMount(() => {
    const visible = () => { if (document.hidden) { if (timer !== null) clearTimeout(timer); timer = null; } else void read(); };
    document.addEventListener("visibilitychange", visible);
    void read();
    return () => { document.removeEventListener("visibilitychange", visible); request?.abort(); if (timer !== null) clearTimeout(timer); };
  });
</script>

<section class="ui-panel attention" aria-labelledby="attention-title">
  <div class="head">
    <h2 id="attention-title">확인이 필요한 설비</h2>
    <button type="button" class="ui-button" onclick={toggle}>{paused ? "자동 갱신 다시 시작" : "자동 갱신 멈추기"}</button>
  </div>
  <p class="context">{readAt ? clock(readAt) + " 기준 · " : ""}{paused ? "자동 갱신을 멈췄습니다." : "3초마다 다시 읽습니다."}
    모델 기준 초과는 학습한 평소 상태와 다르다는 뜻이며 고장 판정이 아닙니다. 아래 항목에서 확인 이유·근거·다음 행동을 볼 수 있습니다.</p>
  {#if loadState === "loading"}
    <StatusNotice message="모델 처리 상태와 수신 상태를 확인하고 있습니다." />
  {:else if loadState === "failed" || !phm}
    <StatusNotice kind="uncertain" message="모델 처리 상태를 다시 읽지 못했습니다. 이전 결과를 지금 상태로 보여 주지 않습니다." />
  {:else}
    {#if sources === null}<StatusNotice kind="uncertain" message="데이터 연결 상태를 읽지 못해 수신 확인 항목은 빠져 있습니다." />{/if}
    {#if phm.truncated}<StatusNotice kind="uncertain" message="적용 모델이 많아 일부만 확인했습니다." />{/if}
    {#if phm.reviewsUnknown}<p class="context">검토 상태를 읽지 못해 검토 진행 여부는 빠져 있습니다.</p>{/if}
    <section aria-label="운영 확인 항목" class="operations-attention">
      <h3>운영 확인 항목</h3><p class="context">수집·저장·분석 서비스의 처리 상태입니다. 설비의 고장 판정이 아닙니다.</p>
      {#if !snapshot.operationsAttention?.complete}<StatusNotice kind="uncertain" message="운영 확인 항목 전체를 읽지 못했습니다."/>{/if}
      {#if snapshot.operationsAttention?.items.length}<ul>{#each snapshot.operationsAttention.items as item(item.id)}
        <li><strong>{item.title}</strong><span>{item.assetId??"공통 운영 서비스"}{item.sourceId?" · "+item.sourceId:""}{item.at?" · "+new Date(item.at).toLocaleString("ko-KR",{timeZone:"Asia/Seoul"}):""}</span>
          {#if destination(item)}<a href={destination(item)!}>상세 확인 →</a>{/if}</li>
      {/each}</ul>{:else if snapshot.operationsAttention?.complete}<p>운영 처리에서 확인할 항목이 없습니다.</p>{/if}
    </section>
    {#if !groups.length}
      <p>{snapshot.operationsAttention?.items.length?"모델·수신 기준으로 확인할 추가 항목은 없습니다.":"지금 확인할 항목이 없습니다."}</p>
    {:else}
      <ul class="groups">
        {#each groups as group (group.assetId)}
          <li><article aria-labelledby={"attention-" + group.assetId}>
            <h3 id={"attention-" + group.assetId} tabindex="-1">{group.assetId}</h3>
            <ul class="notes">
              {#each group.notes as note (note.kind)}
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
  .operations-attention{margin-block:var(--space-4);padding-block:var(--space-3);border-bottom:1px solid var(--color-border)}.operations-attention ul{padding-left:var(--space-4)}.operations-attention li{display:grid;gap:var(--space-2);padding-block:var(--space-2);overflow-wrap:anywhere}
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
