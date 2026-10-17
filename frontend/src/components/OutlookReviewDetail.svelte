<script lang="ts">
  import {onMount, tick} from "svelte";
  import {
    compareReobservation, positionText, readCaptures, recomputeForComparison, recordReview,
    reobservationUrl, CompareUnavailable, type Capture, type Reobservation, type SourceRecheck,
  } from "../outlook-captures";
  import {reachText} from "../reach";
  import {num} from "../format";
  import CautionNote from "./CautionNote.svelte";
  import ReviewActions from "./ReviewActions.svelte";
  import StatusNotice from "./StatusNotice.svelte";

  type Props = {capture: Capture; writable: boolean; onUpdated: (capture: Capture) => void};
  let {capture, writable, onUpdated}: Props = $props();
  const saved = $derived(capture.outlook);
  const axis = $derived(saved.kind === "acquisition" ? "acquisition" as const : "time" as const);
  const status = $derived(capture.review.status);
  const main = $derived(saved.scenarios.find((item) => item.id === "current") ?? saved.scenarios[0]);
  let comparison: Reobservation | null = $state(null);
  let comparedLast: string | number | null = $state(null);
  let compareState: "idle" | "loading" | "failed" = $state("idle");
  let compareError = $state("");
  let heading: HTMLElement | null = $state(null);
  let compareRequest: AbortController | null = null;

  const STATUS = {open: "검토 대기", acknowledged: "확인함", closed: "검토 종료"};
  const RECHECK: Record<SourceRecheck, string> = {
    same_measurement_projection: "원본 데이터: 요청 때와 같음",
    changed: "원본 데이터: 요청 뒤 바뀜 (새 측정이 들어왔거나 수정됨)",
    different_source: "원본 데이터: 지금은 다른 출처·측정 위치로 조회됨",
    unavailable: "원본 데이터: 지금은 확인할 수 없음 · 요청 당시 결과만 볼 수 있음",
  };
  const SCENARIO: Record<string, string> = {current: "기본 설정", recent: "최근 구간 중심",
    responsive: "변화에 민감", linear: "최근 속도 유지"};
  const clock = (at: string) => new Date(at).toLocaleString("ko-KR", {timeZone: "Asia/Seoul"});

  async function refresh(signal: AbortSignal): Promise<boolean> {
    try {
      const page = await readCaptures(saved.assetId, {captureId: capture.id}, signal);
      if (signal.aborted) return false;
      onUpdated(page.captures[0]);
      await tick();
      heading?.focus();
      return true;
    } catch {
      return false;
    }
  }
  async function compare() {
    compareRequest?.abort();
    const request = new AbortController(); compareRequest = request;
    compareState = "loading"; comparison = null; compareError = "";
    try {
      const current = await recomputeForComparison(saved, request.signal);
      if (request.signal.aborted) return;
      comparison = compareReobservation(saved, current);
      comparedLast = current.record.last;
      compareState = "idle";
    } catch (cause: unknown) {
      if (request.signal.aborted) return;
      compareState = "failed";
      compareError = cause instanceof Error ? cause.message : "지금 데이터로 다시 계산하지 못했습니다.";
      if (cause instanceof CompareUnavailable) compareState = "failed";
    }
  }
  onMount(() => () => compareRequest?.abort());
</script>

<article class="detail" data-capture-id={capture.id} aria-labelledby={"capture-" + capture.id}>
  <div class="head">
    <h2 id={"capture-" + capture.id} tabindex="-1" bind:this={heading}>{saved.assetId} · {saved.series} 전망</h2>
    <span class="badge">{STATUS[status]}</span>
  </div>
  <p class="context">{clock(capture.capturedAt)} 요청 · {positionText(saved.record.last)}까지의 데이터
    · 관리 기준 {num(saved.conditions.management, "없음")} / 종료 기준 {num(saved.conditions.end, "없음")}</p>

  <section aria-labelledby={"then-" + capture.id}>
    <h3 id={"then-" + capture.id}>요청 당시 결과</h3>
    <div class="tiles">
      {#if saved.conditions.management !== null}
        <div><span>관리 기준 {num(saved.conditions.management)}</span><strong>{reachText(main?.management, axis)}</strong></div>
      {/if}
      {#if saved.conditions.end !== null}
        <div><span>종료 기준 {num(saved.conditions.end)}</span><strong>{reachText(main?.end, axis)}</strong></div>
      {/if}
      {#if saved.conditions.management === null && saved.conditions.end === null}
        <p class="context">기준 없이 요청한 전망입니다.</p>
      {/if}
    </div>
    <p class="recheck">{RECHECK[capture.sourceRecheck]}</p>
  </section>

  <section aria-labelledby={"now-" + capture.id}>
    <h3 id={"now-" + capture.id}>이후 측정과 비교</h3>
    {#if compareState === "loading"}
      <StatusNotice message="같은 조건으로 지금 데이터를 다시 계산하고 있습니다." />
    {:else if compareState === "failed"}
      <StatusNotice kind="failure" title="다시 계산하지 못했습니다" message={compareError}
        actionLabel="다시 계산해 비교" onAction={() => void compare()} />
    {:else if !comparison}
      <p class="context">같은 조건으로 지금 데이터를 다시 계산해 요청 당시 결과와 나란히 봅니다.</p>
      <button type="button" class="ui-button" onclick={() => void compare()}>지금 데이터로 다시 계산해 비교</button>
    {:else if comparison.kind === "different-subject"}
      <p>지금 데이터의 출처·측정 위치·적용 모델·측정 간격 근거가 요청 때와 달라 직접 비교하지 않습니다.</p>
    {:else if comparison.kind === "changed-assumptions"}
      <p>계산 조건이 달라 비교하지 않습니다: {comparison.changes.join(", ")}. 조건이 바뀐 것은 상태가 나빠진 것이 아닙니다.</p>
    {:else if comparison.kind === "same-measurement"}
      <p>요청 뒤 새로 들어온 측정이 없습니다. 같은 데이터에 대한 결과입니다.</p>
      {#if comparison.anomalyEvidenceChanged}
        <p class="context">측정 데이터는 같지만 이상 탐지 결과는 요청 때와 다릅니다.</p>
      {/if}
    {:else}
      <p>같은 조건 · {comparison.moved ? "새 측정이 들어옴" : "같은 마지막 측정의 값이 수정됨"}
        ({positionText(comparison.before)} → {positionText(comparison.after)})</p>
      {#if comparison.limits.length}
        <div class="scroll"><table>
          <caption>같은 조건으로 계산한 기준 도달 비교 (기본 설정)</caption>
          <thead><tr><th scope="col">기준</th><th scope="col">요청 당시</th><th scope="col">지금</th></tr></thead>
          <tbody>
            {#each comparison.limits as limit (limit.name)}
              <tr><th scope="row">{limit.name === "management" ? "관리 기준" : "종료 기준"}</th>
                <td>{reachText(limit.before, axis)}</td><td><strong>{reachText(limit.after, axis)}</strong></td></tr>
            {/each}
          </tbody>
        </table></div>
      {/if}
    {/if}
    {#if comparison && comparison.kind !== "different-subject" && comparison.kind !== "changed-assumptions" && !comparison.bindingRecorded}
      <p class="context">요청 당시 적용 모델이 기록되지 않아 같은 모델 입력인지는 확인할 수 없습니다.</p>
    {/if}
    {#if comparedLast !== null}
      <p class="context"><a href={reobservationUrl(saved)}>설비 화면에서 이 조건으로 다시 보기 →</a></p>
    {/if}
  </section>

  <ReviewActions id={capture.id} {status} events={capture.review.events} {writable}
    closeQuestion="검토를 종료할까요? 종료하면 이 요청에 기록을 더 남길 수 없습니다."
    submit={(action, text, eventId, signal) => recordReview(capture, action, text, eventId, signal)}
    reload={refresh} />

  <CautionNote message="검토 종료는 정비 완료나 고장 판정이 아닙니다. 요청 당시 결과는 그때의 계산이며, 원본 측정 전체를 보관하지는 않습니다." />

  <details>
    <summary>요청 당시 계산 전체 보기</summary>
    {#if saved.scenarios.length}
      <div class="scroll"><table>
        <caption>계산 방식별 기준 도달 (방식 사이의 차이는 신뢰 구간이 아닙니다)</caption>
        <thead><tr><th scope="col">계산 방식</th>
          {#if saved.conditions.management !== null}<th scope="col">관리 기준</th>{/if}
          {#if saved.conditions.end !== null}<th scope="col">종료 기준</th>{/if}
        </tr></thead>
        <tbody>
          {#each saved.scenarios as scenario (scenario.id)}
            <tr><th scope="row">{SCENARIO[scenario.id] ?? scenario.id}</th>
              {#if saved.conditions.management !== null}<td>{reachText(scenario.management, axis)}</td>{/if}
              {#if saved.conditions.end !== null}<td>{reachText(scenario.end, axis)}</td>{/if}
            </tr>
          {/each}
        </tbody>
      </table></div>
    {/if}
    {#if saved.sentences.length}
      <p><strong>당시 계산 결과 설명</strong></p>
      <ul>{#each saved.sentences as sentence, i (i)}<li>{sentence}</li>{/each}</ul>
    {/if}
    <p class="context">기준 방향 {saved.conditions.direction === "upper" ? "값이 올라갈 때 (상한)" : "값이 내려갈 때 (하한)"}
      · 사용한 측정 {positionText(saved.record.first)} ~ {positionText(saved.record.last)} ({saved.record.points}개)
      · 추세 민감도 {saved.settings.changepointPriorScale} · 변화점 범위 {saved.settings.changepointRange}
      · 학습 {saved.settings.trainingPoints === null ? "전체" : saved.settings.trainingPoints + "개"}
      · 반복 패턴 {saved.settings.seasonality === "off" ? "제외" : "자동"}</p>
  </details>
  <details>
    <summary>기술 상세</summary>
    <dl>
      <div><dt>검토 요청 ID</dt><dd>{capture.id}</dd></div>
      <div><dt>데이터 출처 · 측정 위치</dt><dd>{saved.sourceId} · {saved.pointId ?? "없음"}</dd></div>
      {#if saved.kind === "acquisition"}
        <div><dt>적용 모델(binding) · 측정 간격 근거</dt><dd>{saved.bindingId ?? "요청 당시 기록 없음"} · {saved.timeBasis}</dd></div>
      {/if}
      <div><dt>원본 재확인 (source_recheck)</dt><dd>{capture.sourceRecheck}</dd></div>
      <div><dt>계산 데이터 버전 (measurement_version)</dt><dd>{saved.measurementVersion}</dd></div>
      <div><dt>해설 근거 버전 (data_version)</dt><dd>{saved.dataVersion}</dd></div>
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
  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: var(--space-3); }
  .tiles div { border: 1px solid var(--color-border); border-radius: var(--radius-control); padding: var(--space-4); display: grid; gap: var(--space-1); }
  .tiles span { color: var(--color-ink-muted); font-size: var(--font-small); }
  .tiles strong { font-size: var(--font-section); }
  .recheck { color: var(--color-ink-muted); margin-top: var(--space-3); }
  .scroll { max-width: 100%; overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; }
  caption { text-align: left; color: var(--color-ink-muted); font-size: var(--font-small); }
  th, td { padding: var(--space-2); text-align: left; border-bottom: 1px solid var(--color-border); }
  summary { cursor: pointer; font-weight: 650; color: var(--color-action); padding-block: var(--space-2); }
  dl { display: grid; gap: var(--space-2); margin: var(--space-2) 0; }
  dt { color: var(--color-ink-muted); font-size: var(--font-small); }
  dd { margin: 0; font-family: ui-monospace, monospace; overflow-wrap: anywhere; }
</style>
