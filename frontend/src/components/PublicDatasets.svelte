<script lang="ts">
  import {onMount} from "svelte";
  import {explainWrite} from "../connections";
  import {datasetFacts, datasetName, groupDatasets, jobText, readPublicDatasets, startImport,
    type PublicDatasets} from "../public-datasets";
  import {routeUrl} from "../routes";

  /** AI-Hub 239 and XJTU-SY records prepared in the datasets folder, imported in one step each.
   * The list rereads while an import runs, so its progress and the new asset show up here. */
  type Props = {writable: boolean; onImported?: () => Promise<void>};
  let {writable, onImported}: Props = $props();
  let datasets: PublicDatasets | null = $state(null);
  let loadState: "loading" | "ready" | "failed" = $state("loading");
  let message = $state("");
  let pending = $state("");
  const groups = $derived.by(() => {
    const current: PublicDatasets | null = datasets;
    return current ? groupDatasets(current.items) : [];
  });
  const running = $derived.by(() => {
    const current: PublicDatasets | null = datasets;
    return current ? Object.values(current.jobs).some((job) => job.state === "running") : false;
  });
  let request: AbortController | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;

  async function reload() {
    request?.abort();
    const current = new AbortController(); request = current;
    const wasRunning = running;
    try {
      const value = await readPublicDatasets(current.signal);
      if (current.signal.aborted) return;
      datasets = value; loadState = "ready";
      const stillRunning = Object.values(value.jobs).some((job) => job.state === "running");
      if (wasRunning && !stillRunning) await onImported?.();
      if (timer) clearTimeout(timer);
      // Progress is written by the supervisor about once a second.
      if (stillRunning) timer = setTimeout(() => void reload(), 2000);
    } catch {
      if (!current.signal.aborted) loadState = "failed";
    }
  }
  async function begin(datasetId: string) {
    pending = datasetId; message = "";
    try {
      await startImport(datasetId, new AbortController().signal);
    } catch (cause: unknown) {
      message = explainWrite(cause);
    } finally {
      pending = "";
      await reload();
    }
  }
  const assetHref = (assetId: string) => routeUrl({page: "assets", assetId, tab: "summary", method: null, data: null});
  onMount(() => {
    void reload();
    return () => { request?.abort(); if (timer) clearTimeout(timer); };
  });
</script>

<section class="ui-panel datasets" id="public-datasets" aria-labelledby="datasets-title">
  <h2 id="datasets-title">공개 실측 데이터로 시작</h2>
  {#if loadState === "loading"}
    <p class="context">data 폴더의 공개 데이터를 찾고 있습니다.</p>
  {:else if loadState === "failed" || !datasets}
    <p class="context">공개 데이터 목록을 읽지 못했습니다. <button type="button" class="ui-button" onclick={() => void reload()}>다시 읽기</button></p>
  {:else if !datasets.items.length}
    <p class="context">data 폴더에서 가져올 AI-Hub 239·XJTU-SY 기록을 찾지 못했습니다.</p>
  {:else}
    <p class="context">data 폴더에 있는 AI-Hub 239 설비 전력 기록과 XJTU-SY 베어링 진동 기록입니다. 고르면 이 작업공간에 가져와 설비 화면에서 분석합니다.</p>
    {#if message}<p class="message" role="alert">{message}</p>{/if}
    {#each groups as group (group.key)}
      {@const active = group.items.some((item) => item.stored || datasets?.jobs[item.datasetId]?.state === "running")}
      <!-- Groups stay folded, so the list reads as what kinds of records there are; one opens
           once it holds an import. -->
      <details open={active}>
        <summary>{group.title} <span class="count">{group.items.length}개</span></summary>
        <p class="context">{group.kind === "xjtu-sy"
          ? "모델 학습에 쓰지 않은 베어링입니다. 처음 가져올 때 이상 탐지 모델 두 개를 학습용 베어링으로 준비합니다."
          : "설비 하나의 약 한 달 기록입니다. 원본 시각에 시간대가 없어 한국 표준시로 저장합니다."}</p>
        <ul>
          {#each group.items as item (item.datasetId)}
            {@const job = datasets.jobs[item.datasetId]}
            <li>
              <strong>{datasetName(item)}</strong>
              <span class="facts">{datasetFacts(item)}</span>
              {#if job && job.state !== "succeeded"}
                <span class="status" class:failure={job.state === "failed"} role="status">{jobText(job)}</span>
              {/if}
              {#if item.stored && job?.state !== "running"}
                <a href={assetHref(item.assetId)}>설비 화면 보기 →</a>
              {:else if job?.state !== "running"}
                <button type="button" class="ui-button" disabled={!writable || !datasets.canImport || running || pending !== ""}
                  onclick={() => void begin(item.datasetId)}>{pending === item.datasetId ? "시작하는 중" : "가져오기"}</button>
              {/if}
            </li>
          {/each}
        </ul>
      </details>
    {/each}
    {#if !writable || !datasets.canImport}<p class="context">보기 전용이라 가져올 수 없습니다.</p>{/if}
  {/if}
</section>

<style>
  .datasets { display: grid; gap: var(--space-3); margin-bottom: var(--space-4); min-width: 0; }
  h2 { margin: 0; }
  p { margin: 0; overflow-wrap: anywhere; }
  .context { color: var(--color-ink-muted); }
  details { border-top: 1px solid var(--color-border); padding-top: var(--space-2); display: grid; gap: var(--space-2); }
  summary { cursor: pointer; font-weight: 650; color: var(--color-action); padding-block: var(--space-2); }
  .count { color: var(--color-ink-muted); font-weight: 400; font-size: var(--font-small); }
  ul { list-style: none; margin: 0; padding: 0; display: grid; }
  li { display: grid; grid-template-columns: minmax(8rem, 14rem) minmax(0, 1fr) auto; gap: var(--space-1) var(--space-3);
    align-items: center; padding: var(--space-2) 0; border-bottom: 1px solid var(--color-border); min-width: 0; }
  .facts, .status { color: var(--color-ink-muted); font-size: var(--font-small); overflow-wrap: anywhere; }
  .status { grid-column: 1 / -1; }
  .status.failure, .message { color: var(--color-failure-ink); }
  li a { font-weight: 650; white-space: nowrap; }
  @media (max-width: 640px) { li { grid-template-columns: minmax(0, 1fr) auto; } .facts { grid-column: 1 / -1; grid-row: 2; } }
</style>
