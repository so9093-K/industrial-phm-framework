<script lang="ts">
  import {onMount} from "svelte";
  import {findingUrl, readFindingReview, recordFindingAction, type FindingReview} from "../finding-reviews";
  import type {ModelBinding, ModelRun} from "../model-evidence";
  import {readModelReview, requestModelReview} from "../model-explanations";
  import {OutcomeUnknown, WriteForbidden} from "../review-writes";
  import ReviewActions from "./ReviewActions.svelte";
  import StatusNotice from "./StatusNotice.svelte";

  /** Record a decision here, or defer this exact stored result to the existing review queue. */
  type Props = {binding: ModelBinding; run: ModelRun; explanationId: string | null; writable: boolean;
    subject?: string};
  let {binding, run, explanationId, writable, subject = ""}: Props = $props();
  let review: FindingReview | null = $state(null);
  let loading = $state(true);
  let readFailed = $state(false);
  let saving = $state(false);
  let message = $state("");
  let kind: "information" | "uncertain" | "failure" = $state("information");
  let request: AbortController | null = null;
  const STATUS = {open: "검토 대기", acknowledged: "확인함", closed: "검토 종료"};

  async function exact(findingId: string, signal: AbortSignal): Promise<FindingReview> {
    const found = await readFindingReview(binding.assetId, findingId, signal);
    if (!found || found.runId !== run.runId || found.model?.bindingId !== binding.bindingId
      || found.model.position !== run.position) throw new Error("이 측정의 검토 기록을 확인하지 못했습니다.");
    return found;
  }
  async function load(signal: AbortSignal): Promise<boolean> {
    try {
      const current = await readModelReview(binding, run, signal);
      const found = current.findingId ? await exact(current.findingId, signal) : null;
      if (signal.aborted) return false;
      review = found; readFailed = false; loading = false;
      return true;
    } catch {
      if (!signal.aborted) { readFailed = true; loading = false; }
      return false;
    }
  }
  async function ensureReview(signal: AbortSignal): Promise<FindingReview> {
    if (review) return review;
    const findingId = await requestModelReview(binding, run, explanationId, signal);
    const found = await exact(findingId, signal);
    if (!signal.aborted) review = found;
    return found;
  }
  async function defer() {
    if (!writable || saving || readFailed) return;
    request?.abort();
    const pending = new AbortController(); request = pending;
    saving = true; kind = "information"; message = "검토함에 저장하고 있습니다.";
    try {
      await ensureReview(pending.signal);
      if (!pending.signal.aborted) message = "정비 검토함에 보류했습니다.";
    } catch (cause: unknown) {
      if (pending.signal.aborted) return;
      kind = cause instanceof OutcomeUnknown ? "uncertain" : "failure";
      message = cause instanceof OutcomeUnknown ? "저장 결과를 확인하지 못했습니다. 검토함을 확인하거나 다시 시도하세요."
        : cause instanceof WriteForbidden ? cause.message : "검토를 요청하지 못했습니다.";
    } finally {
      if (request === pending) saving = false;
    }
  }
  function retry() {
    request?.abort();
    const pending = request = new AbortController();
    loading = true; void load(pending.signal);
  }
  onMount(() => { retry(); return () => request?.abort(); });
</script>

<section class="review-request" aria-labelledby={"model-review-" + run.runId}>
  <h3 id={"model-review-" + run.runId}>사람 검토</h3>
  {#if subject}<p class="subject">검토할 결과 · <strong>{subject}</strong></p>{/if}
  {#if loading}
    <StatusNotice message="검토 기록을 불러오고 있습니다." />
  {:else if readFailed}
    <StatusNotice kind="failure" message="검토 기록을 불러오지 못했습니다." actionLabel="다시 불러오기" onAction={retry} />
  {:else}
    {#if review}<p><strong>{STATUS[review.status]}</strong> · <a href={findingUrl(binding.assetId, review.findingId)}>정비 검토함에서 보기 →</a></p>{/if}
    <ReviewActions id={run.runId} status={review?.status ?? "open"} events={review?.events ?? []}
      eventsTotal={review?.eventsTotal ?? 0} writable={writable && !saving} confirmLabel="판단 저장"
      closeQuestion="검토를 종료할까요? 종료하면 이 결과에 기록을 더 남길 수 없습니다."
      submit={async (action, note, eventId, signal, decision) => {
        const item = await ensureReview(signal);
        return recordFindingAction(item, action, note, eventId, signal, decision);
      }} reload={load} />
    {#if !review && writable}
      <p class="context">나중에 검토하려면 <button type="button" class="ui-button" disabled={saving} onclick={() => void defer()}>검토함에 보류</button></p>
    {/if}
  {/if}
  {#if message}<p class:uncertain={kind === "uncertain"} class:failure={kind === "failure"} role={kind === "failure" ? "alert" : "status"}>{message}</p>{/if}
</section>

<style>
  .review-request { margin-top: var(--space-4); display: grid; gap: var(--space-3); }
  h3 { margin: 0; font-size: var(--font-section); }
  p { margin: 0; overflow-wrap: anywhere; }
  .context { color: var(--color-ink-muted); font-size: var(--font-small); }
  .uncertain { color: var(--color-caution-ink); }
  .failure { color: var(--color-failure-ink); }
</style>
