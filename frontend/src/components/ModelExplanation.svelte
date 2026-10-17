<script lang="ts">
  import {onMount} from "svelte";
  import {num} from "../format";
  import {scoreSummary, type ModelBinding, type ModelRun} from "../model-evidence";
  import {
    readModelExplanations, requestModelExplanation, DEFAULT_QUESTION,
    type FeatureChange, type ModelExplanation, type Relation,
  } from "../model-explanations";
  import {WriteForbidden} from "../review-writes";
  import StatusNotice from "./StatusNotice.svelte";

  /** AI explanation of one stored model result against an earlier analyzed measurement.
   * The table shows the comparison the server stored and checked the answer against. */
  type Props = {
    binding: ModelBinding; run: ModelRun; earlier: number[]; writable: boolean;
    place: (position: number) => string; onExplained: (explanationId: string | null) => void;
  };
  let {binding, run, earlier, writable, place, onExplained}: Props = $props();
  let compare: number | null = $state(null);
  let records: ModelExplanation[] = $state([]);
  let loadState: "loading" | "ready" | "failed" = $state("loading");
  let requesting = $state(false);
  let error = $state("");
  let question = $state("");
  let request: AbortController | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let remaining = 40;

  const RELATION: Record<Relation, string> = {increased: "증가", decreased: "감소", unchanged: "거의 같음"};
  const SOURCE = {"model": "AI 해설 · 근거 확인됨", "model-trimmed": "AI 해설 · 근거 없는 문장 제외",
    "verified-comparison": "저장된 비교로 작성 · AI 문장은 근거가 확인되지 않아 뺐습니다"};
  const clock = (at: string) => new Date(at).toLocaleString("ko-KR", {timeZone: "Asia/Seoul"});
  const percent = (value: number | null) => value === null ? "—"
    : (value > 0 ? "+" : "") + value.toLocaleString("ko-KR", {maximumFractionDigits: 1}) + "%";
  const same = (item: ModelExplanation) => item.comparePosition === compare;
  const latest = $derived(records.find((item) => same(item) && item.status === "complete" && item.answer) ?? null);
  const newest = $derived(records.find(same) ?? null);
  const waiting = $derived(newest?.status === "pending");
  const score = $derived(scoreSummary(run.output));
  const mentioned = $derived.by((): {change: FeatureChange; relation: Relation}[] => {
    if (!latest?.answer) return [];
    return latest.answer.observations.flatMap((item) => {
      const change = latest.features.find((row) => row.feature === item.feature);
      return change ? [{change, relation: item.relation}] : [];
    });
  });

  $effect(() => { onExplained(latest?.id ?? null); });

  function cancel() {
    request?.abort();
    if (timer !== null) clearTimeout(timer);
    timer = null;
  }
  async function refresh() {
    cancel();
    const pending = new AbortController(); request = pending;
    loadState = "loading"; error = "";
    try {
      const results = await readModelExplanations(binding, run, pending.signal);
      if (pending.signal.aborted) return;
      records = results; loadState = "ready";
      if (results.some((item) => same(item) && item.status === "pending") && remaining > 0) {
        remaining--;
        timer = setTimeout(() => void refresh(), 1500);
      }
    } catch (cause: unknown) {
      if (pending.signal.aborted) return;
      loadState = "failed";
      error = cause instanceof Error ? cause.message : "해설을 불러오지 못했습니다.";
    }
  }
  async function ask(text: string) {
    if (!writable || requesting || !text.trim()) return;
    cancel();
    const pending = new AbortController(); request = pending;
    requesting = true; error = ""; remaining = 40;
    try {
      // A follow-up continues the shown answer of the same comparison.
      await requestModelExplanation(binding, run, compare, text,
        text === DEFAULT_QUESTION ? null : latest?.id ?? null, pending.signal);
      if (pending.signal.aborted) return;
      question = "";
      requesting = false;
      await refresh();
    } catch (cause: unknown) {
      if (pending.signal.aborted) return;
      requesting = false;
      loadState = "failed";
      error = cause instanceof WriteForbidden ? "보기 전용이라 해설을 만들 수 없습니다."
        : cause instanceof Error ? cause.message : "해설을 요청하지 못했습니다.";
    }
  }
  function choose(value: string) {
    compare = value === "" ? null : Number(value);
    remaining = 40;
    void refresh();
  }
  onMount(() => {
    compare = earlier[0] ?? null;
    void refresh();
    return cancel;
  });
</script>

<section class="explanation" aria-labelledby={"model-ai-" + run.runId}>
  <div class="head">
    <h3 id={"model-ai-" + run.runId}>AI 해설</h3>
    {#if latest?.answer}
      <span class="meta">{latest.answer.modelUnavailable ? "AI 응답 없음 · 저장된 비교로 작성" : SOURCE[latest.answer.source]}
        · {latest.model ?? "모델명 없음"} · {clock(latest.requestedAt)}</span>
    {/if}
  </div>
  {#if earlier.length}
    <label class="compare">비교할 이전 측정
      <select value={compare === null ? "" : String(compare)} disabled={requesting}
        onchange={(event) => choose(event.currentTarget.value)}>
        {#each earlier as position (position)}
          <option value={String(position)}>{place(position)}</option>
        {/each}
      </select>
    </label>
  {:else}
    <p class="context">비교할 이전 분석이 없어 {place(run.position)} 한 시점만 설명합니다.</p>
  {/if}

  {#if requesting}
    <StatusNotice message="해설을 요청하고 있습니다." />
  {:else if loadState === "loading" && !records.length}
    <StatusNotice message="이 결과에 대한 해설을 확인하고 있습니다." />
  {:else if loadState === "failed"}
    <StatusNotice kind="failure" title="해설을 확인하지 못했습니다" message={error + " 모델 점수는 그대로 볼 수 있습니다."}
      actionLabel="다시 확인" onAction={() => { remaining = 40; void refresh(); }} />
  {:else if waiting}
    <StatusNotice message="두 측정의 값과 모델 점수를 비교해 해설을 만들고 있습니다. 잠시 후 자동으로 다시 확인합니다." />
  {:else if latest?.answer}
    <p class="question">질문 · {latest.question}</p>
    <p class="summary">{latest.answer.summary}</p>
    {#if latest.comparePosition !== null}
      <p class="context">모델 점수 {num(latest.previousScore, "기록 없음")} → {num(score.score, "기록 없음")}
        ({place(latest.comparePosition)} → {place(run.position)})</p>
    {/if}
    {#if mentioned.length}
      <div class="scroll"><table>
        <caption>해설이 짚은 측정값</caption>
        <thead><tr><th scope="col">측정값</th><th scope="col">비교 측정</th><th scope="col">고른 측정</th><th scope="col">변화</th></tr></thead>
        <tbody>
          {#each mentioned as {change, relation} (change.feature)}
            <tr><th scope="row">{change.label}</th><td>{num(change.previous, "—")}</td><td>{num(change.current)}</td>
              <td>{RELATION[relation]} {percent(change.relativePercent)}</td></tr>
          {/each}
        </tbody>
      </table></div>
    {/if}
    {#if latest.answer.nextStep}
      <p><strong>다음에 볼 것</strong> · {latest.answer.nextStep}</p>
    {/if}
    {#if latest.features.length}
      <details>
        <summary>저장된 측정값 비교 전체 ({latest.features.length}개)</summary>
        <div class="scroll"><table>
          <thead><tr><th scope="col">측정값</th><th scope="col">비교 측정</th><th scope="col">고른 측정</th><th scope="col">변화율</th></tr></thead>
          <tbody>
            {#each latest.features as row (row.feature)}
              <tr><th scope="row">{row.label}</th><td>{num(row.previous, "—")}</td><td>{num(row.current)}</td>
                <td>{percent(row.relativePercent)}</td></tr>
            {/each}
          </tbody>
        </table></div>
      </details>
    {/if}
  {:else}
    {#if newest?.status === "failed"}
      <StatusNotice kind="uncertain" message="지난번 해설은 만들지 못했습니다. 모델 점수와 측정값은 그대로 볼 수 있습니다." />
    {/if}
    <p class="context">아직 이 비교에 대한 해설이 없습니다.</p>
    {#if writable}
      <button type="button" class="ui-button ui-button-primary" onclick={() => void ask(DEFAULT_QUESTION)}>해설 만들기</button>
    {/if}
  {/if}
  {#if !writable}
    <p class="context">보기 전용이라 해설을 만들 수 없습니다. 운영을 시작하면 만들 수 있습니다.</p>
  {:else}
    <details class="ask">
      <summary>{latest ? "이어서 질문하기" : "직접 질문하기"}</summary>
      <label>AI에게 물을 질문 (최대 600자)
        <input maxlength="600" value={question} disabled={requesting} placeholder={DEFAULT_QUESTION}
          oninput={(event) => question = event.currentTarget.value} />
      </label>
      <button type="button" class="ui-button ui-button-primary" disabled={requesting || waiting || !question.trim()}
        onclick={() => void ask(question)}>질문 보내기</button>
    </details>
  {/if}
</section>

<style>
  .explanation { display: flex; flex-direction: column; gap: var(--space-3); margin-top: var(--space-5); min-width: 0; }
  .head { display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--space-2) var(--space-4); align-items: baseline; }
  h3 { margin: 0; font-size: var(--font-section); }
  .meta, .context, .question { color: var(--color-ink-muted); font-size: var(--font-small); overflow-wrap: anywhere; }
  .summary { font-size: 1.05rem; line-height: 1.6; overflow-wrap: anywhere; }
  .compare, .ask label { display: grid; gap: var(--space-2); font-weight: 650; }
  select, input { width: 100%; min-width: 0; border: 1px solid var(--color-border); border-radius: var(--radius-control);
    padding: var(--space-3); background: var(--color-surface); color: var(--color-ink); font: inherit; font-weight: 400; }
  .ask { display: grid; gap: var(--space-3); }
  .ask button { justify-self: start; margin-top: var(--space-3); }
  .scroll { max-width: 100%; overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; }
  caption { text-align: left; color: var(--color-ink-muted); font-size: var(--font-small); }
  th, td { padding: var(--space-2); text-align: left; border-bottom: 1px solid var(--color-border); }
  thead th { white-space: nowrap; }
  summary { cursor: pointer; font-weight: 650; color: var(--color-action); padding-block: var(--space-2); }
</style>
