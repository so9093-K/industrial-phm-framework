<script lang="ts">
  import {onMount, tick} from "svelte";
  import {
    reviewNote, OutcomeUnknown, ReviewConflict, WriteForbidden,
    type ReviewAction, type ReviewEvent, type ReviewStatus,
  } from "../review-writes";

  /** The review history of one subject and the next human actions on it. The parent
   * owns the write and the reload; this keeps a retried action on its first event ID. */
  type Props = {
    id: string; status: ReviewStatus; events: ReviewEvent[]; eventsTotal?: number; writable: boolean;
    closeQuestion: string;
    submit: (action: ReviewAction, note: string, eventId: string, signal: AbortSignal) => Promise<unknown>;
    reload: (signal: AbortSignal) => Promise<boolean>;
  };
  let {id, status, events, eventsTotal = events.length, writable, closeQuestion, submit, reload}: Props = $props();
  let note = $state("");
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
    try { text = reviewNote(action, note); }
    catch (cause: unknown) {
      messageKind = "failure"; message = cause instanceof Error ? cause.message : "메모를 확인하세요.";
      return;
    }
    const key = action + "\n" + text;
    if (!pending || pending.key !== key) pending = {key, eventId: crypto.randomUUID()};
    controller?.abort();
    const request = new AbortController(); controller = request;
    busy = true; messageKind = "information"; message = "검토 기록을 남기고 있습니다.";
    try {
      await submit(action, text, pending.eventId, request.signal);
      if (request.signal.aborted) return;
      pending = null; confirmingClose = false;
      if (action === "note") note = "";
      if (await refreshed(request.signal)) { messageKind = "information"; message = "검토 기록을 남겼습니다."; }
    } catch (cause: unknown) {
      if (request.signal.aborted) return;
      if (cause instanceof ReviewConflict) {
        pending = null; confirmingClose = false;
        messageKind = "uncertain"; message = "다른 사람이 먼저 검토 상태를 바꿨습니다. 최신 기록을 다시 불러왔습니다.";
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

<section aria-labelledby={"review-" + id}>
  <h3 id={"review-" + id} tabindex="-1" bind:this={historyHeading}>검토 기록</h3>
  {#if events.length}
    {#if eventsTotal > events.length}
      <p class="context">최근 {events.length}건만 보입니다 (전체 {eventsTotal}건).</p>
    {/if}
    <ol class="events">
      {#each events as event (event.eventId)}
        <li>{clock(event.recordedAt)} · {ACTION[event.action]}{event.note ? " · " + event.note : ""}</li>
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
    <label>메모 (최대 1000자)
      <textarea maxlength="1000" rows="3" value={note} disabled={busy}
        oninput={(event) => note = event.currentTarget.value}></textarea>
    </label>
    <div class="actions">
      <button type="button" class="ui-button" disabled={busy} onclick={() => void act("note")}>메모 남기기</button>
      {#if status === "open"}
        <button type="button" class="ui-button ui-button-primary" disabled={busy} onclick={() => void act("acknowledge")}>확인함으로 표시</button>
      {:else if !confirmingClose}
        <button type="button" class="ui-button ui-button-primary" disabled={busy} onclick={() => void askClose()}>검토 종료</button>
      {/if}
    </div>
    {#if status === "open"}<p class="context">확인한 뒤에 검토를 종료할 수 있습니다.</p>{/if}
    {#if confirmingClose}
      <div class="confirm" role="group" aria-labelledby={"close-" + id} tabindex="-1" bind:this={confirmBox}>
        <p id={"close-" + id}>{closeQuestion}</p>
        <div class="actions">
          <button type="button" class="ui-button ui-button-primary" disabled={busy} onclick={() => void act("close")}>종료하기</button>
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
  label { display: grid; gap: var(--space-2); font-weight: 650; }
  textarea { width: 100%; min-width: 0; border: 1px solid var(--color-border); border-radius: var(--radius-control);
    padding: var(--space-3); background: var(--color-surface); color: var(--color-ink); font: inherit; }
  .actions { display: flex; flex-wrap: wrap; gap: var(--space-3); margin-top: var(--space-3); }
  .confirm { margin-top: var(--space-3); padding: var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-control); }
  .message { overflow-wrap: anywhere; }
  .uncertain { background: var(--color-uncertain-surface); padding: var(--space-2) var(--space-3); border-radius: var(--radius-control); }
  .failure { background: var(--color-failure-surface); color: var(--color-failure-ink); padding: var(--space-2) var(--space-3); border-radius: var(--radius-control); }
</style>
