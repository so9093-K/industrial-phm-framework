<script lang="ts">
  import {onDestroy, tick, untrack} from "svelte";
  import {askChange, newChangeConversation, readChangeDiscussion, STARTERS, LOAD_QUESTION, type ChangeDiscussion, type Pointed} from "../change-investigation";
  import type {PlaybackScope} from "../record-playback";
  import {readPermission} from "../outlook-briefings";
  import {OutcomeUnknown} from "../writes";

  import type {ChangeFollowup} from "../change-evidence";
  import ChangeLoadComparison from "./ChangeLoadComparison.svelte";

  let {assetId, reviewKey, scope, followup, analyses = {}, pointed = null, onUnpoint, savedJudgment, onPause, compareLoad = false}: {
    assetId: string; reviewKey: string; scope: PlaybackScope | null;
    followup: ChangeFollowup | null;
    /** AI가 답과 함께 고를 수 있는 분석 화면(분석 이름 → 링크). */
    analyses?: Record<string, ChangeFollowup>;
    /** 그래프에서 짚은 곳: 질문과 함께 보낸다. 지우면 기록 전체에 대해 묻는다. */
    pointed?: Pointed | null; onUnpoint?: () => void;
    savedJudgment: {label: string; note: string | null} | null;
    onPause: () => void;
    compareLoad?: boolean;
  } = $props();

  const conversation = newChangeConversation();
  let records: ChangeDiscussion[] = $state([]), writable = $state(false), question = $state(""), error = $state("");
  let busy = $state(false), awaiting: string | null = $state(null), remaining = 240;
  let request: AbortController | null = null, write: AbortController | null = null, timer: ReturnType<typeof setTimeout> | null = null;
  let previous = new Set<string>();
  const thread = $derived([...records].reverse());
  const latest = $derived(records[0] ?? null);
  const waiting = $derived(busy || awaiting !== null || latest?.status === "pending");
  const unsent = $derived(awaiting !== null && !records.some(row => row.question === awaiting && !previous.has(row.id)) ? awaiting : null);
  // 기다린 시간: 첫 답은 모델이 쉬고 있었다면 1분 가까이 걸린다. 멈춘 것과 구분되게 초를 센다.
  let since: number | null = $state(null), now = $state(Date.now());
  const clock = setInterval(() => { if (waiting) now = Date.now(); }, 1000);
  $effect(() => { if (waiting && since === null) untrack(() => { since = Date.now(); now = since; }); if (!waiting) since = null; });
  const elapsed = $derived(since !== null ? Math.max(0, Math.round((now - since) / 1000)) : null);
  const typing = (text: string) => text + (elapsed !== null && elapsed >= 3 ? " · " + elapsed + "초" : "");

  function cancel() { request?.abort(); if (timer !== null) clearTimeout(timer); timer = null; }
  onDestroy(() => { cancel(); write?.abort(); clearInterval(clock); });
  async function refresh() {
    cancel();
    const pending = new AbortController(); request = pending;
    try {
      const read = await readChangeDiscussion(assetId, reviewKey, conversation, pending.signal, scope);
      if (pending.signal.aborted) return;
      records = read;
      if (awaiting && read.some(row => row.question === awaiting && !previous.has(row.id))) awaiting = null;
      error = "";
      if (awaiting || read[0]?.status === "pending") {
        if (remaining-- > 0) timer = setTimeout(() => void refresh(), 1500);
        else { awaiting = null; error = "답변 상태를 확인하지 못했습니다."; }
      }
    } catch (cause) { if (!pending.signal.aborted) error = cause instanceof Error ? cause.message : "대화를 불러오지 못했습니다."; }
  }
  async function ask(text: string, runComparison = false) {
    if (!writable || waiting || !text.trim()) return;
    const submitted = text.trim();
    onPause(); previous = new Set(records.map(row => row.id)); awaiting = submitted; stick = true;
    if (question.trim() === submitted) question = "";
    cancel(); const pending = new AbortController(); write = pending; busy = true; error = ""; remaining = 240;
    try {
      await askChange(assetId, reviewKey, conversation, submitted, records.find(row => row.status === "complete" && row.answer)?.id ?? null, pending.signal, scope, runComparison, pointed);
      if (!pending.signal.aborted) { busy = false; await refresh(); }
    } catch (cause) {
      if (pending.signal.aborted) return;
      if (cause instanceof OutcomeUnknown) { busy = false; await refresh(); }
      else { awaiting = null; if (!question) question = submitted; error = cause instanceof Error ? cause.message : "질문을 보내지 못했습니다."; }
    } finally { if (write === pending) { write = null; busy = false; } }
  }
  $effect(() => {
    const permission = new AbortController();
    void readPermission(permission.signal).then(value => { if (!permission.signal.aborted) writable = value; }).catch(() => {});
    return () => { permission.abort(); cancel(); };
  });
  function keydown(event: KeyboardEvent) {
    // Enter로 보내고 Shift+Enter는 줄바꿈. 한글을 조합하는 중의 Enter는 글자를 확정할 뿐 보내지 않는다.
    if (event.key !== "Enter" || event.shiftKey || event.isComposing || event.keyCode === 229) return;
    event.preventDefault(); void ask(question);
  }
  let log: HTMLElement | undefined = $state(), stick = true;
  $effect(() => {
    thread.length; unsent; latest?.status; latest?.comparison?.status;
    if (stick) void tick().then(() => { if (log) log.scrollTop = log.scrollHeight; });
  });
</script>

<section class="agent" aria-label="AI 관제 대화">
  {#if savedJudgment}
    <p class="saved"><b>{savedJudgment.label}</b>{savedJudgment.note ? " · " + savedJudgment.note : ""}</p>
  {/if}
  <div class="log" bind:this={log} onscroll={() => { if (log) stick = log.scrollTop + log.clientHeight >= log.scrollHeight - 48; }} aria-live="polite">
    {#each thread as row (row.id)}
      <p class="me">{row.question}{#if row.pointed}<small>{row.pointed}에서</small>{/if}</p>
      <div class="msg answer" class:charted={row.comparison?.status === "ready"}>
        {#if row.status === "complete" && row.answer}<p>{row.answer.summary}</p>{/if}
        {#if row.comparison}<ChangeLoadComparison {assetId} result={row.comparison}/>{/if}
        {#if row.status === "complete" && row.analysis && analyses[row.analysis]}
          <a class="opened" href={analyses[row.analysis].href} onclick={onPause}>{analyses[row.analysis].label} →</a>{/if}
        {#if row.status === "pending"}<p class="typing"><i></i><i></i><i></i>{typing("답 정리 중")}</p>
        {:else if row.status === "failed"}<p class="note">답을 만들지 못했습니다. 다시 물어 주세요.</p>{/if}
      </div>
    {/each}
    {#if unsent}<p class="me">{unsent}</p><p class="msg typing"><i></i><i></i><i></i>{typing("측정 기록 확인 중")}</p>{/if}
    {#if error}
      <p class="error" role="alert">{error}
        {#if awaiting || latest?.status === "pending"}<button type="button" onclick={() => { remaining = 240; void refresh(); }}>다시 확인</button>{/if}
      </p>
    {/if}
  </div>
  {#if !thread.length && !unsent && writable}
    <div class="replies">{#if compareLoad}<button type="button" onclick={() => void ask(LOAD_QUESTION,true)}>{LOAD_QUESTION}</button>{/if}
      {#each STARTERS as text (text)}<button type="button" onclick={() => void ask(text)}>{text}</button>{/each}</div>
  {:else if latest?.status === "complete" && latest.comparison?.status !== "ready" && !latest.analysis && followup && !waiting}
    <a class="followup" href={followup.href} onclick={onPause}>{followup.label} →</a>
  {/if}
  {#if pointed && writable}
    <p class="pointed">그래프에서 짚은 곳 · <b>{pointed.label}</b>
      {#if onUnpoint}<button type="button" aria-label="짚은 곳 지우기" onclick={onUnpoint}>×</button>{/if}</p>
  {/if}
  <div class="composer" class:disabled={!writable}>
    <textarea rows="1" maxlength="600" aria-label="AI 관제에 질문" bind:value={question} onkeydown={keydown} onfocus={onPause} disabled={!writable}
      placeholder={!writable ? "보기 전용" : waiting ? "답을 기다리는 동안 다음 질문을 쓸 수 있습니다" : pointed ? "짚은 곳에 대해 질문" : "이 특이사항에 대해 질문"}></textarea>
    <button type="button" class="send" aria-label="질문 보내기" disabled={!writable || waiting || !question.trim()} onclick={() => void ask(question)}>
      <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 13V3M3.5 7.5 8 3l4.5 4.5"/></svg></button>
  </div>
</section>

<style>
  .agent{display:flex;flex-direction:column;gap:6px;min-height:0;height:100%;font-size:var(--font-small)}
  .log{flex:1;display:flex;flex-direction:column;gap:6px;overflow-y:auto;min-height:0;padding-right:2px;overscroll-behavior:contain}
  p{margin:0;line-height:1.5;overflow-wrap:anywhere}
  .msg{align-self:flex-start;max-width:96%;padding:7px 10px;border-radius:4px 12px 12px 12px;background:#f2f5f7;color:var(--color-ink)}
  .me{align-self:flex-end;max-width:88%;padding:6px 10px;border-radius:12px 4px 12px 12px;background:var(--color-surface-selected)}
  .answer{display:grid;gap:5px;white-space:pre-wrap}
  .answer.charted{width:100%;max-width:100%;min-width:0;box-sizing:border-box}
  .note{font-size:12px;color:var(--color-ink-muted)}
  .typing{display:flex;align-items:center;gap:4px;font-size:12px;color:var(--color-ink-muted)}
  .typing i{width:5px;height:5px;border-radius:50%;background:var(--color-ink-muted);animation:blink 1.2s infinite ease-in-out}
  .typing i:nth-child(2){animation-delay:.2s}.typing i:nth-child(3){animation-delay:.4s;margin-right:4px}
  @keyframes blink{0%,80%,100%{opacity:.25}40%{opacity:1}}
  @media (prefers-reduced-motion:reduce){.typing i{animation:none;opacity:.6}}
  .error{font-size:12px;color:var(--color-failure-ink)}
  .saved{font-size:var(--font-label);padding:6px 8px;border-left:2px solid var(--color-border);color:var(--color-ink-muted)}
  .followup,.error button{color:var(--color-action);font:inherit;font-weight:650}
  .followup{align-self:start;padding-block:4px}
  .opened{justify-self:start;font-size:12px;font-weight:650;color:var(--color-action);text-decoration:none}.opened:hover{text-decoration:underline}
  .me small{display:block;margin-top:2px;font-size:11px;color:var(--color-ink-muted)}
  .pointed{display:flex;align-items:center;gap:4px;margin:0;font-size:12px;color:var(--color-ink-muted)}.pointed b{color:var(--color-ink)}
  .pointed button{border:0;background:none;padding:0 4px;font:inherit;font-size:14px;line-height:1;color:var(--color-ink-muted);cursor:pointer}
  .error button{border:0;background:none;padding:0;text-decoration:underline;cursor:pointer}
  .replies{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:6px}
  .replies button{font:inherit;font-size:12px;padding:4px 10px;border:1px solid var(--color-action);border-radius:999px;background:var(--color-surface);color:var(--color-action);cursor:pointer}
  .replies button:disabled{opacity:.5;cursor:default}
  .composer{display:grid;grid-template-columns:minmax(0,1fr) 28px;align-items:end;gap:4px;padding:4px 4px 4px 10px;border:1px solid var(--color-control-border);border-radius:12px;background:var(--color-surface)}
  .composer:focus-within{border-color:var(--color-action)}
  .composer.disabled{background:#f4f6f8}
  textarea{border:0;outline:0;resize:none;padding:4px 0;font:inherit;font-size:12px;line-height:1.5;background:transparent;color:var(--color-ink);field-sizing:content;min-height:1.5em;max-height:6em}
  .send{display:grid;place-items:center;width:28px;height:28px;border:0;border-radius:50%;background:var(--color-action);cursor:pointer}
  .send svg{width:14px;height:14px;fill:none;stroke:#fff;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
  .send:disabled{background:var(--color-border);cursor:default}
</style>
