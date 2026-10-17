<script lang="ts">
  import {onMount} from "svelte";
  import {BriefingEvidenceChanged, readPermission, type BriefingProjection} from "../outlook-briefings";
  import {captureUrl, confirmCapture, CaptureRejected, OutcomeUnknown} from "../outlook-captures";
  import {routeUrl} from "../routes";

  /** Leaves the shown result in the maintenance review queue. The supervisor recomputes and
   * stores every number; this button only names the selection the user is looking at. */
  type Props = {projection: BriefingProjection; onEvidenceChanged: (message: string) => void};
  let {projection, onEvidenceChanged}: Props = $props();
  let writable = $state(false);
  let saving = $state(false);
  let message = $state("");
  let kind: "information" | "uncertain" | "failure" = $state("information");
  let savedId: string | null = $state(null);
  let request: AbortController | null = null;
  const queueUrl = $derived(routeUrl({page: "maintenance", assetId: projection.assetId, tab: "summary",
    method: null, data: null}));

  async function submit() {
    if (!writable || saving) return;
    request?.abort();
    const pending = new AbortController(); request = pending;
    saving = true; savedId = null; kind = "information";
    message = "요청 직전에 결과를 다시 계산해 확인하고 있습니다.";
    try {
      savedId = await confirmCapture(projection, pending.signal);
      if (pending.signal.aborted) return;
      message = "정비 검토함에 남겼습니다.";
    } catch (cause: unknown) {
      if (pending.signal.aborted) return;
      if (cause instanceof BriefingEvidenceChanged || cause instanceof CaptureRejected) {
        onEvidenceChanged(cause instanceof CaptureRejected ? cause.message
          : "요청하는 사이 데이터나 계산 조건이 바뀌어 검토를 요청하지 않았습니다. 다시 계산하세요.");
        return;
      }
      kind = cause instanceof OutcomeUnknown ? "uncertain" : "failure";
      message = cause instanceof OutcomeUnknown
        ? "요청이 처리됐는지 확인하지 못했습니다. 정비 검토함에서 확인하거나 다시 요청하세요. 다시 요청해도 기록이 겹치지 않습니다."
        : cause instanceof Error ? cause.message : "검토를 요청하지 못했습니다.";
    } finally {
      if (request === pending) saving = false;
    }
  }
  onMount(() => {
    const permission = new AbortController();
    void readPermission(permission.signal).then((allowed) => {
      if (!permission.signal.aborted) writable = allowed;
    }).catch(() => {});
    return () => { permission.abort(); request?.abort(); };
  });
</script>

<div class="review-request">
  <div class="row">
    <button type="button" class="ui-button ui-button-primary" disabled={!writable || saving}
      onclick={() => void submit()}>검토 요청</button>
    <span class="context">{writable ? "지금 결과와 조건을 정비 검토함에 남깁니다."
      : "보기 전용이라 검토를 요청할 수 없습니다."}</span>
  </div>
  {#if message}
    <p class="message" class:uncertain={kind === "uncertain"} class:failure={kind === "failure"}
      role={kind === "failure" ? "alert" : "status"}>{message}
      {#if savedId}<a href={captureUrl(projection.assetId, savedId)}>정비 검토함에서 보기 →</a>
      {:else if kind === "uncertain"}<a href={queueUrl}>정비 검토함 열기 →</a>{/if}</p>
  {/if}
</div>

<style>
  .review-request { margin-top: var(--space-4); }
  .row { display: flex; flex-wrap: wrap; gap: var(--space-3); align-items: center; }
  .context { color: var(--color-ink-muted); font-size: var(--font-small); }
  .message { margin-top: var(--space-3); overflow-wrap: anywhere; }
  .message a { margin-inline-start: var(--space-2); }
  .uncertain { background: var(--color-uncertain-surface); padding: var(--space-2) var(--space-3); border-radius: var(--radius-control); }
  .failure { background: var(--color-failure-surface); color: var(--color-failure-ink); padding: var(--space-2) var(--space-3); border-radius: var(--radius-control); }
</style>
