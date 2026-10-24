<script lang="ts">
  import {onMount} from "svelte";
  import {findingUrl} from "../finding-reviews";
  import type {ModelBinding, ModelRun} from "../model-evidence";
  import {readModelReview, requestModelReview, type ModelReview} from "../model-explanations";
  import {OutcomeUnknown, WriteForbidden} from "../review-writes";

  /** Leaves this stored model result in the maintenance review queue, linked to the
   * explanation shown with it. Asking again names the same review item. */
  type Props = {binding: ModelBinding; run: ModelRun; explanationId: string | null; writable: boolean;
    subject?: string};
  let {binding, run, explanationId, writable, subject = ""}: Props = $props();
  let review: ModelReview | null = $state(null);
  let readFailed = $state(false);
  let saving = $state(false);
  let message = $state("");
  let kind: "information" | "uncertain" | "failure" = $state("information");
  let request: AbortController | null = null;
  const STATUS = {open: "검토 대기", acknowledged: "확인함", closed: "검토 종료"};

  async function load(signal: AbortSignal) {
    try {
      const current = await readModelReview(binding, run, signal);
      if (!signal.aborted) { review = current; readFailed = false; }
    } catch {
      if (!signal.aborted) readFailed = true;
    }
  }
  async function submit() {
    if (!writable || saving) return;
    request?.abort();
    const pending = new AbortController(); request = pending;
    saving = true; kind = "information"; message = "검토를 요청하고 있습니다.";
    try {
      const findingId = await requestModelReview(binding, run, explanationId, pending.signal);
      if (pending.signal.aborted) return;
      review = {findingId, status: "open"};
      message = "정비 검토함에 남겼습니다.";
      await load(pending.signal);
    } catch (cause: unknown) {
      if (pending.signal.aborted) return;
      kind = cause instanceof OutcomeUnknown ? "uncertain" : "failure";
      message = cause instanceof OutcomeUnknown
        ? "요청이 처리됐는지 확인하지 못했습니다. 다시 요청해도 같은 검토 항목으로 남습니다."
        : cause instanceof WriteForbidden ? cause.message : "검토를 요청하지 못했습니다.";
    } finally {
      if (request === pending) saving = false;
    }
  }
  onMount(() => {
    const reading = new AbortController();
    void load(reading.signal);
    return () => { reading.abort(); request?.abort(); };
  });
</script>

<section class="review-request" aria-labelledby={"model-review-" + run.runId}>
  <h3 id={"model-review-" + run.runId}>사람 검토</h3>
  {#if subject}<p class="subject">검토할 결과 · <strong>{subject}</strong></p>{/if}
  {#if review?.findingId && review.status}
    <p>이 모델 결과는 정비 검토함에 있습니다 · <strong>{STATUS[review.status]}</strong>
      <a href={findingUrl(binding.assetId, review.findingId)}>정비 검토함에서 보기 →</a></p>
  {:else}
    <div class="row">
      <button type="button" class="ui-button ui-button-primary" disabled={!writable || saving || readFailed}
        onclick={() => void submit()}>검토 요청</button>
      <span class="context">{!writable ? "보기 전용이라 검토를 요청할 수 없습니다."
        : readFailed ? "검토 상태를 확인하지 못해 요청을 막았습니다. 새로고침해 주세요."
        : explanationId ? "이 모델 결과와 위의 AI 해설을 정비 검토함에 남깁니다."
        : "이 모델 결과를 정비 검토함에 남깁니다."}</span>
    </div>
  {/if}
  {#if message}
    <p class="message" class:uncertain={kind === "uncertain"} class:failure={kind === "failure"}
      role={kind === "failure" ? "alert" : "status"}>{message}</p>
  {/if}
</section>

<style>
  .review-request { margin-top: var(--space-5); display: grid; gap: var(--space-3); }
  h3 { margin: 0; font-size: var(--font-section); }
  .row { display: flex; flex-wrap: wrap; gap: var(--space-3); align-items: center; }
  .context { color: var(--color-ink-muted); font-size: var(--font-small); }
  p { overflow-wrap: anywhere; margin: 0; }
  p a { margin-inline-start: var(--space-2); }
  .uncertain { background: var(--color-uncertain-surface); padding: var(--space-2) var(--space-3); border-radius: var(--radius-control); }
  .failure { background: var(--color-failure-surface); color: var(--color-failure-ink); padding: var(--space-2) var(--space-3); border-radius: var(--radius-control); }
</style>
