<script lang="ts">
  import {onMount, tick} from "svelte";
  import {
    reviewNote, latestDecision, DECISIONS, DECISION_LABEL, OutcomeUnknown, ReviewConflict, WriteForbidden,
    type ReviewAction, type ReviewDecision, type ReviewEvent, type ReviewStatus,
  } from "../review-writes";

  /** The review history of one subject and the next human actions on it. Confirming records
   * what the person judged it needs (추가 점검 필요 · 계속 관찰 · 점검 불필요) with an optional
   * reason; closing keeps or changes that judgement. The parent owns the write and the reload;
   * this keeps a retried action on its first event ID. */
  type Props = {
    id: string; status: ReviewStatus; events: ReviewEvent[]; eventsTotal?: number; writable: boolean;
    closeQuestion: string;
    submit: (action: ReviewAction, note: string, eventId: string, signal: AbortSignal,
      decision: ReviewDecision | null) => Promise<unknown>;
    reload: (signal: AbortSignal) => Promise<boolean>;
  };
  let {id, status, events, eventsTotal = events.length, writable, closeQuestion, submit, reload}: Props = $props();
  let reason = $state("");
  // The current judgement; a close starts from it and may change it.
  const judged = $derived(latestDecision(events));
  let decision: ReviewDecision | null = $state(null);
  $effect(() => { if (decision === null && judged !== null) decision = judged; });
  let busy = $state(false);
  let message = $state("");
  let messageKind: "information" | "uncertain" | "failure" = $state("information");
  let confirmingClose = $state(false);
  let confirmBox: HTMLElement | null = $state(null);
  let historyHeading: HTMLElement | null = $state(null);
  // A retry of one uncertain action reuses its event ID; a different action gets a new one.
  let pending: {key: string; eventId: string} | null = null;
  let controller: AbortController | null = null;

  const ACTION = {note: "메모", acknowledge: "확인", close: "검토 종료"};
  const clock = (at: string) => new Date(at).toLocaleString("ko-KR", {timeZone: "Asia/Seoul"});

  async function refreshed(signal: AbortSignal): Promise<boolean> {
    if (await reload(signal)) return true;
    if (!signal.aborted) {
      messageKind = "uncertain";
      message = "검토 기록을 다시 불러오지 못했습니다. 새로고침해 확인하세요.";
    }
    return false;
  }
  async function act(action: ReviewAction) {
    if (busy || !writable || status === "closed") return;
    let text: string;
    try { text = reviewNote(action, reason); }
    catch (cause: unknown) {
      messageKind = "failure"; message = cause instanceof Error ? cause.message : "판단 이유를 확인하세요.";
      return;
    }
    if (action !== "note" && !decision) { messageKind = "failure"; message = "판단을 고르세요."; return; }
    const key = action + "\n" + decision + "\n" + text;
    if (!pending || pending.key !== key) pending = {key, eventId: crypto.randomUUID()};
    controller?.abort();
    const request = new AbortController(); controller = request;
    busy = true; messageKind = "information"; message = "검토 기록을 남기고 있습니다.";
    try {
      await submit(action, text, pending.eventId, request.signal, action === "note" ? null : decision);
      if (request.signal.aborted) return;
      pending = null; confirmingClose = false; reason = "";
      if (await refreshed(request.signal)) { messageKind = "information"; message = "검토 기록을 남겼습니다."; }
    } catch (cause: unknown) {
      if (request.signal.aborted) return;
      if (cause instanceof ReviewConflict) {
        pending = null; confirmingClose = false;
        messageKind = "uncertain"; message = "다른 창이나 요청에서 검토 상태가 변경됐습니다. 최신 기록을 다시 불러왔습니다.";
        await refreshed(request.signal);
        return;
      }
      messageKind = cause instanceof OutcomeUnknown ? "uncertain" : "failure";
      message = cause instanceof WriteForbidden ? cause.message
        : "처리 결과를 확인하지 못했습니다. 같은 작업을 다시 시도해도 기록이 겹치지 않습니다.";
    } finally {
      if (controller === request) busy = false;
    }
  }
  async function askClose() { confirmingClose = true; await tick(); confirmBox?.focus(); }
  async function cancelClose() { confirmingClose = false; await tick(); historyHeading?.focus(); }
  onMount(() => () => controller?.abort());
</script>

{#snippet decisionField()}
  <fieldset class="decision" disabled={busy}>
    <legend>판단</legend>
    {#each DECISIONS as option (option)}
      <label><input type="radio" name={"decision-" + id} value={option} checked={decision === option}
        onchange={() => decision = option} /> {DECISION_LABEL[option]}</label>
    {/each}
  </fieldset>
{/snippet}

{#snippet reasonField()}
  <label class="field">판단 이유 (선택)
    <textarea maxlength="1000" rows="2" value={reason} disabled={busy}
      oninput={(event) => reason = event.currentTarget.value}></textarea>
  </label>
{/snippet}

<section aria-labelledby={"review-" + id}>
  <h3 id={"review-" + id} tabindex="-1" bind:this={historyHeading}>검토 기록</h3>
  {#if events.length}
    {#if eventsTotal > events.length}
      <p class="context">최근 {events.length}건만 보입니다 (전체 {eventsTotal}건).</p>
    {/if}
    <ol class="events">
      {#each events as event (event.eventId)}
        <li>{clock(event.recordedAt)} · {ACTION[event.action]}{event.decision ? " · " + DECISION_LABEL[event.decision] : ""}{event.note ? " · " + event.note : ""}</li>
      {/each}
    </ol>
  {:else}
    <p class="context">아직 남긴 검토 기록이 없습니다.</p>
  {/if}
  {#if status === "closed"}
    <p class="context">검토가 종료되어 기록을 더 남길 수 없습니다.</p>
  {:else if !writable}
    <p class="context">보기 전용이라 검토 기록을 남길 수 없습니다. 운영을 시작하면 남길 수 있습니다.</p>
  {:else}
    {#if status === "open"}
      {@render decisionField()}
      <details class="reason">
        <summary>판단 이유 함께 남기기 (선택)</summary>
        {@render reasonField()}
      </details>
      <div class="actions">
        <button type="button" class="ui-button ui-button-primary" disabled={busy || !decision} onclick={() => void act("acknowledge")}>확인함으로 표시</button>
      </div>
      <p class="context">판단을 남기면 확인함이 되고, 그 뒤에 검토를 종료할 수 있습니다.</p>
    {:else if !confirmingClose}
      {#if judged}<p class="current">현재 판단 · <strong>{DECISION_LABEL[judged]}</strong></p>{/if}
      <div class="actions">
        <button type="button" class="ui-button ui-button-primary" disabled={busy} onclick={() => void askClose()}>검토 종료</button>
      </div>
    {/if}
    {#if confirmingClose}
      <div class="confirm" role="group" aria-labelledby={"close-" + id} tabindex="-1" bind:this={confirmBox}>
        <p id={"close-" + id}>{closeQuestion}</p>
        {@render decisionField()}
        {@render reasonField()}
        <div class="actions">
          <button type="button" class="ui-button ui-button-primary" disabled={busy || !decision} onclick={() => void act("close")}>종료하기</button>
          <button type="button" class="ui-button" disabled={busy} onclick={() => void cancelClose()}>취소</button>
        </div>
      </div>
    {/if}
  {/if}
  {#if message}
    <p class="message" class:uncertain={messageKind === "uncertain"} class:failure={messageKind === "failure"}
      role={messageKind === "failure" ? "alert" : "status"}>{message}</p>
  {/if}
</section>

<style>
  h3 { font-size: var(--font-section); margin: var(--space-4) 0 var(--space-2); }
  .context { color: var(--color-ink-muted); overflow-wrap: anywhere; }
  .events { padding-inline-start: var(--space-5); }
  .events li { overflow-wrap: anywhere; }
  .decision { display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-4); margin: var(--space-3) 0 0; padding: var(--space-2) var(--space-3);
    border: 1px solid var(--color-border); border-radius: var(--radius-control); }
  .decision legend { font-weight: 650; font-size: var(--font-small); padding: 0 var(--space-1); }
  .decision label { display: inline-flex; align-items: center; gap: var(--space-1); min-height: 32px; }
  .current { margin: var(--space-2) 0 0; }
  .actions { display: flex; flex-wrap: wrap; gap: var(--space-3); margin-top: var(--space-3); }
  .reason { margin-top: var(--space-3); }
  .reason summary { cursor: pointer; color: var(--color-ink-muted); font-size: var(--font-small); }
  .field { display: grid; gap: var(--space-2); margin-top: var(--space-2); font-weight: 650; font-size: var(--font-small); }
  textarea { width: 100%; min-width: 0; border: 1px solid var(--color-border); border-radius: var(--radius-control);
    padding: var(--space-3); background: var(--color-surface); color: var(--color-ink); font: inherit; font-weight: 400; }
  .confirm { margin-top: var(--space-3); padding: var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-control); }
  .message { overflow-wrap: anywhere; }
  .uncertain { background: var(--color-uncertain-surface); padding: var(--space-2) var(--space-3); border-radius: var(--radius-control); }
  .failure { background: var(--color-failure-surface); color: var(--color-failure-ink); padding: var(--space-2) var(--space-3); border-radius: var(--radius-control); }
</style>
