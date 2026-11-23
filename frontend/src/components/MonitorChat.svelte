<script lang="ts">
  import {onDestroy, tick, untrack} from "svelte";
  import {askChange, readChangeDiscussion, INVESTIGATE, spokenQuestion, type ChangeDiscussion} from "../change-investigation";
  import type {PlaybackScope} from "../record-playback";
  import {readPermission} from "../outlook-briefings";
  import {questionDraft,keepQuestionDraft} from "../question-drafts";
  import {OutcomeUnknown} from "../writes";

  /** 관제 줄 오른쪽의 AI 관제 대화창. AI가 특이사항을 문장으로 알리고(notice), 사람이 남긴 판단은 내 말풍선으로,
   * 앞서 찾은 특이사항은 지난 메시지로 위에 둔다. '원인을 조사해 주세요'나 질문을 보내면 이 자리에서 AI가 확인한
   * 항목과 답을 보인다. 조사 화면의 AI 조사와 같은 대화라 어느 화면에서 이어도 같다. */
  let {assetId, reviewKey, scope, watched, notice, when, judged, earlier, calm, checking, detailHref, canAsk, onPause, heading = true}: {
    assetId: string; reviewKey: string | null; scope: PlaybackScope | null; watched: string;
    notice: string[] | null; when: string | null;
    judged: {verdict: string; day: string; note: string | null} | null | "pending";
    earlier: {key: string; when: string; text: string}[]; calm: string; checking: boolean;
    detailHref: string; canAsk: boolean; onPause: () => void;
    /** 바깥이 이미 제목(AI 조사·확인 범위)을 보이면 false: 대화창 안의 머리줄을 생략한다. */
    heading?: boolean;
  } = $props();

  const draftScope=untrack(()=>"change:"+assetId+":"+reviewKey);
  let records: ChangeDiscussion[] = $state([]), writable = $state(false), question = $state(questionDraft(draftScope)), error = $state("");
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
  onDestroy(() => { keepQuestionDraft(draftScope,question); cancel(); write?.abort(); clearInterval(clock); });
  async function refresh() {
    if (!reviewKey) return;
    cancel();
    const pending = new AbortController(); request = pending;
    try {
      const read = await readChangeDiscussion(assetId, reviewKey, pending.signal, scope);
      if (pending.signal.aborted) return;
      records = read;
      if (awaiting && read.some(row => row.question === awaiting && !previous.has(row.id))) awaiting = null;
      error = "";
      if ((awaiting || read[0]?.status === "pending") && remaining-- > 0) timer = setTimeout(() => void refresh(), 1500);
    } catch (cause) { if (!pending.signal.aborted) error = cause instanceof Error ? cause.message : "대화를 불러오지 못했습니다."; }
  }
  async function ask(text: string) {
    if (!reviewKey || !writable || waiting || !text.trim()) return;
    const submitted = text.trim();
    onPause(); previous = new Set(records.map(row => row.id)); awaiting = submitted; stick = true;
    if (question.trim() === submitted) question = "";
    cancel(); const pending = new AbortController(); write = pending; busy = true; error = ""; remaining = 240;
    try {
      await askChange(assetId, reviewKey, submitted, latest?.status === "complete" ? latest.id : null, pending.signal, scope);
      if (!pending.signal.aborted) { busy = false; await refresh(); }
    } catch (cause) {
      if (pending.signal.aborted) return;
      if (cause instanceof OutcomeUnknown) { busy = false; await refresh(); }
      else { awaiting = null; if (!question) question = submitted; error = cause instanceof Error ? cause.message : "질문을 보내지 못했습니다."; }
    } finally { if (write === pending) { write = null; busy = false; } }
  }
  $effect(() => {
    if (!reviewKey || !canAsk) return;
    const permission = new AbortController();
    void readPermission(permission.signal).then(value => { if (!permission.signal.aborted) writable = value; }).catch(() => {});
    untrack(() => void refresh());
    return () => { permission.abort(); cancel(); };
  });
  function keydown(event: KeyboardEvent) {
    // Enter로 보내고 Shift+Enter는 줄바꿈. 한글을 조합하는 중의 Enter는 글자를 확정할 뿐 보내지 않는다.
    if (event.key !== "Enter" || event.shiftKey || event.isComposing || event.keyCode === 229) return;
    event.preventDefault(); void ask(question);
  }
  // 처음에는 AI의 특이사항 알림이 보이게 둔다(지난 대화는 그 아래). 사람이 질문을 보낸 뒤에는 새 메시지를 따라 내려간다.
  let log: HTMLElement | undefined = $state(), stick = false, placed = false;
  $effect(() => { thread.length; unsent; latest?.status; void tick().then(() => {
    if (!log) return;
    if (!placed) {
      placed = true;
      const head = log.querySelector<HTMLElement>(".notice");
      if (head) log.scrollTop += head.getBoundingClientRect().top - log.getBoundingClientRect().top - 4;
      else log.scrollTop = log.scrollHeight;
    } else if (stick) log.scrollTop = log.scrollHeight;
  }); });
</script>

<section class="agent" aria-label="AI 관제 대화">
  {#if heading}<p class="watch"><span class="avatar" aria-hidden="true">AI</span><b>AI 관제</b><span>{watched}</span></p>{/if}
  <div class="log" bind:this={log} aria-live="polite">
    {#each earlier as row (row.key)}<p class="msg old"><time>{row.when}</time> {row.text}</p>{/each}
    {#if checking}<p class="msg typing"><i></i><i></i><i></i>변화 판정 중</p>
    {:else if notice}
      {#key reviewKey}
        <article class="msg notice">
          {#if when}<time>{when}</time>{/if}
          {#each notice as sentence, index (index)}<p>{sentence}</p>{/each}
          <a class="more" href={detailHref} onclick={onPause}>자세히 보기 →</a>
        </article>
      {/key}
      {#if judged === "pending"}<p class="status">판단 전</p>
      {:else if judged}<p class="me judged"><b>{judged.verdict}</b>{judged.note ? " · " + judged.note : ""}<small>{judged.day}</small></p>{/if}
      {#each thread as row (row.id)}
        <p class="me">{spokenQuestion(row.question)}</p>
        <div class="msg answer">
          {#if row.steps.length}
            <details open={row.status === "pending"}><summary>확인한 항목 {row.steps.length}개</summary>
              <ul>{#each row.steps as step, index (index)}<li><span>{step.label}</span><b>{step.result}</b></li>{/each}</ul></details>
          {/if}
          {#if row.status === "pending"}<p class="typing"><i></i><i></i><i></i>{typing("답 정리 중")}</p>
          {:else if row.status === "complete" && row.answer}
            <p>{row.answer.summary}</p>
            {#if row.answer.source === "computed"}<p class="note">AI 응답을 쓰지 못해 계산 결과 요약으로 답했습니다.</p>{/if}
            {#if row.answer.next_step}<p class="note">{row.answer.next_step}</p>{/if}
          {:else}<p class="note">설명을 만들지 못했습니다. 그래프는 계속 볼 수 있습니다.</p>{/if}
        </div>
      {/each}
      {#if unsent}<p class="me">{spokenQuestion(unsent)}</p><p class="msg typing"><i></i><i></i><i></i>{typing("측정 기록 확인 중")}</p>{/if}
      {#if error}<p class="error" role="alert">{error}</p>{/if}
    {:else}
      <p class="msg">{calm} <a class="more" href={detailHref} onclick={onPause}>보기 →</a></p>
    {/if}
  </div>
  {#if canAsk && notice && reviewKey}
    {#if !thread.length && !unsent}<div class="replies"><button type="button" disabled={!writable} onclick={() => void ask(INVESTIGATE.text)}>{INVESTIGATE.label}</button></div>{/if}
    <div class="composer" class:disabled={!writable}>
      <textarea rows="1" maxlength="600" aria-label="AI 관제에 질문" bind:value={question} onkeydown={keydown} onfocus={onPause} disabled={!writable}
        placeholder={!writable ? "보기 전용에서는 대화를 볼 수만 있습니다" : waiting ? "답을 기다리는 동안 다음 질문을 쓸 수 있습니다" : "이 특이사항에 대해 질문"}></textarea>
      <button type="button" class="send" aria-label="질문 보내기" disabled={!writable || waiting || !question.trim()} onclick={() => void ask(question)}>
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 13V3M3.5 7.5 8 3l4.5 4.5"/></svg></button>
    </div>
  {/if}
</section>

<style>
  .agent{display:flex;flex-direction:column;gap:6px;min-height:0;height:100%;font-size:var(--font-small)}
  .watch{display:flex;align-items:center;gap:6px;margin:0;font-size:12px;color:var(--color-ink-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-variant-numeric:tabular-nums}
  .watch b{color:var(--color-ink);font-weight:650}
  .avatar{flex:none;display:grid;place-items:center;width:20px;height:20px;border-radius:50%;background:var(--color-action);color:#fff;font-size:9px;font-weight:700}
  .log{flex:1;display:flex;flex-direction:column;gap:6px;overflow-y:auto;min-height:0;padding-right:2px;overscroll-behavior:contain}
  p{margin:0;line-height:1.5;overflow-wrap:anywhere}
  .msg{align-self:flex-start;max-width:96%;padding:7px 10px;border-radius:4px 12px 12px 12px;background:#f2f5f7;color:var(--color-ink)}
  .msg.old{padding:4px 9px;font-size:12px;color:var(--color-ink-muted);background:none;border:1px solid var(--color-border)}
  .msg.notice{display:grid;gap:3px;border-left:3px solid var(--color-change-mark);background:#fbfaf6;animation:arrive .5s ease-out}
  @keyframes arrive{from{opacity:0;transform:translateY(4px)}}
  @media (prefers-reduced-motion:reduce){.msg.notice{animation:none}}
  time{font-size:12px;color:var(--color-ink-muted);font-variant-numeric:tabular-nums}
  .more{justify-self:end;font-size:12px;font-weight:650;color:var(--color-action);text-decoration:none}.more:hover{text-decoration:underline}
  .me{align-self:flex-end;max-width:88%;padding:6px 10px;border-radius:12px 4px 12px 12px;background:var(--color-surface-selected)}
  .me.judged{display:grid;gap:1px;font-size:12px}.me.judged b{font-size:var(--font-small)}.me small{font-size:11px;color:var(--color-ink-muted)}
  .status{align-self:flex-end;font-size:12px;color:var(--color-ink-muted)}
  .answer{display:grid;gap:5px}
  details summary{font-size:12px;color:var(--color-ink-muted);cursor:pointer}
  details ul{margin:4px 0 0;padding:0;list-style:none;display:grid;gap:1px}
  details li{display:flex;justify-content:space-between;gap:8px;font-size:12px}details li b{font-weight:600;text-align:right;font-variant-numeric:tabular-nums}
  .note{font-size:12px;color:var(--color-ink-muted)}
  .typing{display:flex;align-items:center;gap:4px;font-size:12px;color:var(--color-ink-muted)}
  .typing i{width:5px;height:5px;border-radius:50%;background:var(--color-ink-muted);animation:blink 1.2s infinite ease-in-out}
  .typing i:nth-child(2){animation-delay:.2s}.typing i:nth-child(3){animation-delay:.4s;margin-right:4px}
  @keyframes blink{0%,80%,100%{opacity:.25}40%{opacity:1}}
  @media (prefers-reduced-motion:reduce){.typing i{animation:none;opacity:.6}}
  .error{font-size:12px;color:var(--color-failure-ink)}
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
