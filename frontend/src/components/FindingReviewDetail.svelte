<script lang="ts">
  import {tick} from "svelte";
  import type {Evidence} from "../reviews";
  import {modelResultUrl, readFindingReviews, recordFindingAction, type FindingReview} from "../finding-reviews";
  import {assetTabUrl} from "../routes";
  import CautionNote from "./CautionNote.svelte";
  import ReviewActions from "./ReviewActions.svelte";

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
  const clock = (at: string | null) => at ? new Date(at).toLocaleString("ko-KR", {timeZone: "Asia/Seoul"}) : "기록 없음";
  const missing = $derived(linked === null ? [] : review.evidenceIds.filter(
    (evidenceId) => !linked.some((item) => item.evidenceId === evidenceId)));

  async function refresh(signal: AbortSignal): Promise<boolean> {
    try {
      const page = await readFindingReviews(review.assetId, signal);
      const updated = page.items.find((item) => item.findingId === review.findingId);
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
  <p class="context">분석 대상 {clock(review.observedAt)}{review.pointId ? " · 측정 위치 " + review.pointId : ""}</p>

  <section aria-labelledby={"subject-" + review.findingId}>
    <h3 id={"subject-" + review.findingId}>검토 대상</h3>
    {#if review.subject === "model"}
      {#if review.model}
        <p>이상 탐지 모델이 모델 입력 #{review.model.position}에서 계산한 점수입니다.</p>
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
            · 원본 품질 {evidence.quality ?? "미확인"} · 분석 {clock(evidence.completedAt)}</li>
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
    submit={(action, text, eventId, signal) => recordFindingAction(review, action, text, eventId, signal)}
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
