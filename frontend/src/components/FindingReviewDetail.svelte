<script lang="ts">
  import {tick} from "svelte";
  import type {Evidence} from "../reviews";
  import {modelResultUrl, readFindingReview, recordFindingAction, type FindingReview} from "../finding-reviews";
  import {assetTabUrl} from "../routes";
  import {num} from "../format";
  import {readReviewEvidence, type ReviewEvidence} from "../review-evidence";
  import {measure} from "../chart-axis";
  import CautionNote from "./CautionNote.svelte";
  import ReviewActions from "./ReviewActions.svelte";
  import StatusNotice from "./StatusNotice.svelte";

  /** One stored analysis or model result a person asked to review. Its numbers stay in
   * the analysis record; this only shows which record it is and what people noted. */
  type Props = {
    review: FindingReview; title: string; linked: Evidence[] | null; writable: boolean;
    onUpdated: (review: FindingReview) => void;
  };
  let {review, title, linked, writable, onUpdated}: Props = $props();
  let heading: HTMLElement | null = $state(null);
  const STATUS = {open: "검토 대기", acknowledged: "확인함", closed: "검토 종료"};
  const ANALYSIS = {phase: "3상 불평형 분석", file: "파일 특징 분석"};
  const QUALITY: Record<string, string> = {pass: "통과", warning: "주의", error: "오류"};
  const PART = {flow: "초과 구간", changes: "전후 비교", ai: "AI 해설", others: "같은 원본의 다른 모델"};
  const clock = (at: string | null) => at ? new Date(at).toLocaleString("ko-KR", {timeZone: "Asia/Seoul"}) : "기록 없음";
  const missing = $derived(linked === null ? [] : review.evidenceIds.filter(
    (evidenceId) => !linked.some((item) => item.evidenceId === evidenceId)));
  // The model result under review and what a person needs to judge it, read from stored records.
  let evidence: ReviewEvidence | null = $state(null);
  let evidenceState: "loading" | "ready" | "failed" = $state("loading");
  let evidenceRevision = $state(0);
  $effect(() => {
    evidenceRevision;
    const location = review.model, assetId = review.assetId;
    evidence = null; evidenceState = "loading";
    if (!location) return;
    const request = new AbortController();
    void readReviewEvidence(assetId, location, request.signal)
      .then((found) => { if (!request.signal.aborted) {evidence = found; evidenceState = found ? "ready" : "failed";} })
      .catch(() => {if (!request.signal.aborted) evidenceState = "failed";});
    return () => request.abort();
  });
  const percent = (value: number | null) => value === null ? "" : " (" + (value > 0 ? "+" : "") + value.toLocaleString("ko-KR", {maximumFractionDigits: 1}) + "%)";
  const ratio = (score: {score: number | null; threshold: number | null}) =>
    score.score !== null && score.threshold ? "기준의 " + (score.score / score.threshold).toLocaleString("ko-KR", {maximumFractionDigits: 2}) + "배" : "";

  async function refresh(signal: AbortSignal): Promise<boolean> {
    try {
      const updated = await readFindingReview(review.assetId, review.findingId, signal);
      if (signal.aborted || !updated) return false;
      onUpdated(updated);
      await tick();
      heading?.focus();
      return true;
    } catch {
      return false;
    }
  }
</script>

<article class="detail" data-finding-id={review.findingId} aria-labelledby={"finding-" + review.findingId}>
  <div class="head">
    <h2 id={"finding-" + review.findingId} tabindex="-1" bind:this={heading}>{title}</h2>
    <span class="badge">{STATUS[review.status]}</span>
  </div>
  <!-- A model result is named by its measurement; a replayed one has no clock of its own. -->
  <p class="context">분석 대상 {review.subject === "model" && evidence ? evidence.at + (evidence.eventStart ? " · " + clock(evidence.eventStart) : "")
    : clock(review.observedAt)}{review.pointId ? " · 측정 위치 " + review.pointId : ""}</p>

  <section aria-labelledby={"subject-" + review.findingId}>
    <h3 id={"subject-" + review.findingId}>검토 대상</h3>
    {#if review.subject === "model"}
      {#if review.model}
        {#if evidence}
          {#if evidence.unread.length}
            <StatusNotice kind="uncertain" message={"확인하지 못한 판단 근거: " + evidence.unread.map(part => PART[part]).join(" · ") + ". 다른 기록으로 대신하지 않습니다."}
              actionLabel="판단 근거 다시 읽기" onAction={() => evidenceRevision++}/>
          {/if}
          <p><strong>{evidence.name}</strong> · {evidence.at} · 점수 {num(evidence.score.score, "기록 없음")} / 기준 {num(evidence.score.threshold, "기록 없음")}{evidence.score.exceeds === null ? "" : evidence.score.exceeds ? " · 기준 초과" : " · 기준 이하"}</p>
          <dl class="grounds" aria-label="판단 근거">
            {#if evidence.flow}<div><dt>언제부터</dt><dd>{evidence.flow.headline}{#if evidence.flow.earlier}<small>{evidence.flow.earlier}</small>{/if}</dd></div>{/if}
            {#if evidence.changes}<div><dt>얼마나</dt><dd>{evidence.changes.against} 대비
              {#each evidence.changes.rows as row, i (row.feature)}{i ? " · " : " "}{row.label} {measure(row.previous ?? 0, row.unit ?? null)} → {measure(row.current, row.unit ?? null)}{percent(row.relativePercent)}{/each}</dd></div>{/if}
            {#if evidence.others.length}<div><dt>다른 모델</dt><dd>{#each evidence.others as other, i (other.name)}{i ? " · " : ""}{other.name} {ratio(other.score)}{other.score.exceeds === null ? "" : other.score.exceeds ? " · 기준 초과" : " · 기준 이하"}{/each}</dd></div>{/if}
            <div><dt>AI 해설</dt><dd>{#if evidence.ai}{evidence.ai.summary}<small>{evidence.ai.byAi ? "AI 해설 · 근거 확인됨" : "AI 없이 저장된 비교로 작성"}</small>{:else if evidence.unread.includes("ai")}해설을 읽지 못했습니다. 해설이 없다는 뜻은 아닙니다.{:else}아직 없습니다. 설비 화면에서 이 결과의 해설을 만들 수 있습니다.{/if}</dd></div>
          </dl>
        {:else}
          {#if evidenceState === "loading"}
            <StatusNotice message="판단 근거를 읽고 있습니다."/>
          {:else}
            <StatusNotice kind="failure" message="판단 근거를 읽지 못했습니다. 다른 결과로 대신하지 않습니다."
              actionLabel="판단 근거 다시 읽기" onAction={() => evidenceRevision++}/>
          {/if}
          <p>이상 탐지 모델이 모델 입력 #{review.model.position}에서 계산한 점수입니다.</p>
        {/if}
        <p class="links"><a href={modelResultUrl(review.assetId, review.model)}>설비 화면에서 이 모델 결과 보기 →</a></p>
      {:else}
        <p class="context">저장된 모델 결과의 위치를 찾지 못했습니다. 다른 결과로 대신 보여 주지 않습니다.</p>
      {/if}
    {:else if linked === null}
      <p class="context">이번 조회에 분석 근거 목록이 없어 근거를 함께 보여 주지 못합니다.</p>
    {:else}
      <ul class="evidence">
        {#each linked as evidence (evidence.evidenceId)}
          <li>{ANALYSIS[evidence.kind]} · 데이터 출처 {evidence.sourceId} · 측정 위치 {evidence.pointId ?? "미확인"}
            · 원본 품질 {QUALITY[evidence.quality ?? ""] ?? evidence.quality ?? "미확인"} · 분석 {clock(evidence.completedAt)}</li>
        {/each}
        {#each missing as evidenceId (evidenceId)}
          <li>분석 근거 {evidenceId}를 이번 목록에서 찾지 못했습니다. 조회 제한이나 오류일 수 있어 다른 근거로 대신하지 않습니다.</li>
        {/each}
      </ul>
      <p class="links"><a href={assetTabUrl(review.assetId, "summary")}>설비 보기 →</a></p>
    {/if}
  </section>

  <ReviewActions id={review.findingId} status={review.status} events={review.events}
    eventsTotal={review.eventsTotal} {writable}
    closeQuestion="검토를 종료할까요? 종료하면 이 분석 결과에 기록을 더 남길 수 없습니다."
    submit={(action, text, eventId, signal, decision) => recordFindingAction(review, action, text, eventId, signal, decision)}
    reload={refresh} />

  <CautionNote message={review.subject === "model"
    ? "검토 종료는 정비 완료나 고장 판정이 아닙니다. 모델 점수는 학습한 평소 상태와의 차이이며, 검토해도 바뀌지 않습니다."
    : "검토 종료는 정비 완료나 고장 판정이 아닙니다. 분석 결과는 검토해도 바뀌지 않습니다."} />

  <details>
    <summary>기술 상세</summary>
    <dl>
      <div><dt>검토 항목 ID</dt><dd>{review.findingId}</dd></div>
      <div><dt>분석 실행</dt><dd>{review.runId}</dd></div>
      <div><dt>분석 근거</dt><dd>{review.evidenceIds.join(", ")}</dd></div>
      <div><dt>분석 종류</dt><dd>{review.capabilityId}</dd></div>
      {#if review.model}<div><dt>적용 모델(binding)</dt><dd>{review.model.bindingId}</dd></div>{/if}
    </dl>
  </details>
</article>

<style>
  .grounds { display: grid; gap: var(--space-2); margin: var(--space-3) 0; }
  .grounds div { display: grid; grid-template-columns: 6.5em minmax(0, 1fr); gap: var(--space-3); }
  .grounds dt { color: var(--color-ink-muted); font-size: var(--font-small); }
  .grounds dd { margin: 0; overflow-wrap: anywhere; }
  .grounds small { display: block; color: var(--color-ink-muted); font-size: var(--font-small); }
  @media (max-width: 520px) { .grounds div { grid-template-columns: 1fr; gap: var(--space-1); } }
  .detail { display: flex; flex-direction: column; gap: var(--space-3); min-width: 0; }
  .head { display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--space-2) var(--space-4); align-items: center; }
  h2 { margin: 0; overflow-wrap: anywhere; }
  h3 { font-size: var(--font-section); margin: var(--space-4) 0 var(--space-2); }
  .badge { font-weight: 700; border: 1px solid var(--color-ink); border-radius: 999px; padding: 2px var(--space-3); font-size: var(--font-small); }
  .context { color: var(--color-ink-muted); overflow-wrap: anywhere; }
  .evidence { padding-inline-start: var(--space-5); color: var(--color-ink-muted); }
  .evidence li { overflow-wrap: anywhere; }
  .links { display: flex; flex-wrap: wrap; gap: var(--space-4); }
  summary { cursor: pointer; font-weight: 650; color: var(--color-action); padding-block: var(--space-2); }
  dl { display: grid; gap: var(--space-2); margin: var(--space-2) 0; }
  dt { color: var(--color-ink-muted); font-size: var(--font-small); }
  dd { margin: 0; font-family: ui-monospace, monospace; overflow-wrap: anywhere; }
</style>
