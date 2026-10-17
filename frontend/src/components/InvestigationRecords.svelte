<script lang="ts">
  import {onMount, untrack} from "svelte";
  import type {Snapshot} from "../monitor";
  import {requestAnalysisReview, type AnalysisRecord, type QualityState} from "../analysis-records";
  import {findingUrl, readFindingReviews, type FindingReview} from "../finding-reviews";
  import {loadModelBindings, type ModelBinding} from "../model-evidence";
  import {num} from "../format";
  import {OutcomeUnknown, WriteForbidden, type ReviewStatus} from "../review-writes";
  import {assetTabUrl, systemUrl} from "../routes";
  import CautionNote from "./CautionNote.svelte";
  import StatusNotice from "./StatusNotice.svelte";

  /** What ran on stored data: analysis results, applied models and analyses that did not
   * run. Each result can be handed to human review; nothing here is recomputed. */
  type Props = {snapshot: Snapshot; writable: boolean; assetId: string};
  let {snapshot, writable, assetId}: Props = $props();
  let chosen = $state(untrack(() => assetId));
  let bindings: ModelBinding[] = $state([]);
  let bindingState: "loading" | "ready" | "failed" = $state("loading");
  let reviews: FindingReview[] | null = $state(null);
  // Reviews requested on this screen, until the next snapshot reports them.
  let requested: Record<string, string> = $state({});
  let pending: Record<string, boolean> = $state({});
  let messages: Record<string, {text: string; kind: "uncertain" | "failure"}> = $state({});

  const KIND = {phase: "3상 불평형 분석", file: "파일 특징 분석"};
  const QUANTITY = {current: "전류", voltage: "전압"};
  const QUALITY: Record<QualityState, string> = {pass: "통과", warning: "주의", error: "오류"};
  const STATUS: Record<ReviewStatus, string> = {open: "검토 대기", acknowledged: "확인함", closed: "검토 종료"};
  const clock = (at: string | null) => at ? new Date(at).toLocaleString("ko-KR", {timeZone: "Asia/Seoul"}) : "기록 없음";
  const key = (item: AnalysisRecord) => item.runId + "\n" + item.evidenceId;
  const matches = (owner: string) => !chosen || owner === chosen;
  const records = $derived(snapshot.analyses.records.filter((item) => matches(item.assetId)));
  const skipped = $derived(snapshot.analyses.skipped.filter((item) => matches(item.assetId)));
  const models = $derived(bindings.filter((item) => matches(item.assetId)));
  // Analyses may name assets the current asset list does not include.
  const assetIds = $derived([...new Set([...snapshot.assets.map((asset) => asset.assetId),
    ...snapshot.analyses.records.map((item) => item.assetId), ...(chosen ? [chosen] : [])])]);

  function review(item: AnalysisRecord): {findingId: string; status: ReviewStatus} | null {
    const same = (entry: {assetId: string; runId: string; evidenceIds: string[]}) => entry.assetId === item.assetId
      && entry.runId === item.runId && entry.evidenceIds.includes(item.evidenceId);
    // The current review list wins; the monitor snapshot is the fallback when it failed.
    const saved = reviews ? reviews.find((entry) => entry.subject === "analysis" && same(entry))
      : snapshot.reviewInbox.reviews.find(same);
    if (saved) return {findingId: saved.findingId, status: saved.status};
    const findingId = requested[key(item)];
    return findingId ? {findingId, status: "open"} : null;
  }
  function choose(value: string) {
    chosen = value;
    const url = new URL(location.href);
    if (value) url.searchParams.set("monitor_asset", value); else url.searchParams.delete("monitor_asset");
    history.replaceState(history.state, "", url);
  }
  async function ask(item: AnalysisRecord) {
    const id = key(item);
    if (!writable || pending[id]) return;
    pending = {...pending, [id]: true};
    const {[id]: _, ...rest} = messages; messages = rest;
    try {
      const findingId = await requestAnalysisReview(item, new AbortController().signal);
      requested = {...requested, [id]: findingId};
    } catch (cause: unknown) {
      messages = {...messages, [id]: cause instanceof OutcomeUnknown
        ? {kind: "uncertain", text: "요청이 처리됐는지 확인하지 못했습니다. 다시 요청해도 같은 검토 항목으로 남습니다."}
        : {kind: "failure", text: cause instanceof WriteForbidden ? cause.message : "검토를 요청하지 못했습니다."}};
    } finally {
      pending = {...pending, [id]: false};
    }
  }
  onMount(() => {
    const request = new AbortController();
    void loadModelBindings(null, request.signal).then((loaded) => {
      if (!request.signal.aborted) { bindings = loaded; bindingState = "ready"; }
    }).catch(() => { if (!request.signal.aborted) bindingState = "failed"; });
    const analyzed = [...new Set(snapshot.analyses.records.map((item) => item.assetId))].slice(0, 20);
    void Promise.all(analyzed.map((id) => readFindingReviews(id, request.signal)))
      .then((pages) => { if (!request.signal.aborted) reviews = pages.flatMap((page) => page.items); })
      .catch(() => {});
    return () => request.abort();
  });
</script>

<label class="asset">설비
  <select value={chosen} onchange={(event) => choose(event.currentTarget.value)}>
    <option value="">전체 설비</option>
    {#each assetIds as id (id)}
      <option value={id}>{id}</option>
    {/each}
  </select>
</label>

<section class="ui-panel" aria-labelledby="analysis-results-title">
  <h2 id="analysis-results-title">분석 결과</h2>
  <p class="context">저장된 3상 불평형 분석과 파일 특징 분석입니다. 분석을 새로 실행하려면
    <a href={systemUrl("connections")}>운영 관리 › 데이터 연결</a>에서 해당 연결의 분석을 실행하세요.</p>
  {#if !snapshot.analyses.available}
    <StatusNotice kind="uncertain" message="이번 조회에 분석 결과 목록이 없습니다. 분석이 없다는 뜻은 아닙니다." />
  {:else}
    {#if snapshot.analyses.truncated}
      <StatusNotice kind="uncertain" message="분석 기록이 많아 최근 일부만 보여 줍니다. 보이지 않는 기록이 없다는 뜻은 아닙니다." />
    {/if}
    {#if !records.length}
      <p class="context">{chosen ? "이 설비에" : "아직"} 저장된 분석 결과가 없습니다.</p>
    {:else}
      <ul class="records">
        {#each records as item (key(item))}
          {@const current = review(item)}
          <li><article aria-labelledby={"record-" + item.evidenceId}>
            <div class="head">
              <h3 id={"record-" + item.evidenceId}>{KIND[item.kind]} · {item.assetId}</h3>
              <span class="badge">{current ? STATUS[current.status] : "검토 요청 전"}</span>
            </div>
            <p class="context">분석 구간 {clock(item.observedStart)} ~ {clock(item.observedEnd)} · 분석 완료 {clock(item.completedAt)}</p>
            <p class="context">데이터 출처 {item.sourceId} · 측정 위치 {item.pointId ?? "미확인"}
              · 원본 품질 {item.quality ? QUALITY[item.quality] : "미확인"}{item.issues.length ? " (" + item.issues.join(", ") + ")" : ""}</p>
            {#if item.kind === "phase"}
              <div class="scroll"><table>
                <caption>3상 불평형률 (%)</caption>
                <thead><tr><th scope="col">대상</th><th scope="col">중앙값</th><th scope="col">상위 5%</th>
                  <th scope="col">최대</th></tr></thead>
                <tbody>
                  {#each item.quantities as row (row.quantity)}
                    <tr><th scope="row">{QUANTITY[row.quantity]}</th><td>{num(row.median, "—")}</td><td>{num(row.p95, "—")}</td>
                      <td>{num(row.max, "—")}</td></tr>
                  {/each}
                </tbody>
              </table></div>
              <ul class="counts">
                {#each item.quantities as row (row.quantity)}
                  <li>{QUANTITY[row.quantity]} · 평가 표본 {row.evaluated}
                    · 제외 표본 {Object.entries(row.excluded).map(([reason, count]) => reason + " " + count).join(", ") || "없음"}
                    {#if row.maxAt}· 최대 시각 {clock(row.maxAt)}{/if}</li>
                {/each}
              </ul>
            {:else}
              <div class="scroll"><table>
                <caption>통계 특징 ({item.features.length}개{item.features.length > 6 ? " 중 6개" : ""})</caption>
                <tbody>
                  {#each item.features.slice(0, 6) as feature (feature.name)}
                    <tr><th scope="row">{feature.name}</th><td>{num(feature.value, "—")}</td></tr>
                  {/each}
                </tbody>
              </table></div>
              {#if item.features.length > 6}
                <details><summary>나머지 통계 특징 {item.features.length - 6}개</summary>
                  <div class="scroll"><table><tbody>
                    {#each item.features.slice(6) as feature (feature.name)}
                      <tr><th scope="row">{feature.name}</th><td>{num(feature.value, "—")}</td></tr>
                    {/each}
                  </tbody></table></div>
                </details>
              {/if}
            {/if}
            <div class="review">
              {#if current}
                <a href={findingUrl(item.assetId, current.findingId)}>정비 검토함에서 보기 →</a>
              {:else if writable}
                <button type="button" class="ui-button" disabled={pending[key(item)]} onclick={() => void ask(item)}>검토 요청</button>
                <span class="context">이 분석 결과를 정비 검토함에 남깁니다.</span>
              {:else}
                <span class="context">보기 전용이라 검토를 요청할 수 없습니다.</span>
              {/if}
              <a href={assetTabUrl(item.assetId, "summary")}>설비 보기 →</a>
            </div>
            {#if messages[key(item)]}
              <p class="message" class:uncertain={messages[key(item)].kind === "uncertain"}
                class:failure={messages[key(item)].kind === "failure"}
                role={messages[key(item)].kind === "failure" ? "alert" : "status"}>{messages[key(item)].text}</p>
            {/if}
            <details>
              <summary>기술 상세</summary>
              <dl>
                <div><dt>분석 실행</dt><dd>{item.runId}</dd></div>
                <div><dt>분석 근거</dt><dd>{item.evidenceId}</dd></div>
                <div><dt>분석 종류 · 계산 버전</dt><dd>{item.capabilityId} · {item.version ?? "기록 없음"}</dd></div>
                {#if item.sha256}<div><dt>원본 파일 확인값 (SHA-256)</dt><dd>{item.sha256}</dd></div>{/if}
              </dl>
            </details>
          </article></li>
        {/each}
      </ul>
      <CautionNote message="3상 불평형률과 통계 특징은 측정값을 요약한 값입니다. 고장 판정이나 경보가 아니며, 파일 특징의 단위와 진동 의미는 확인되지 않았습니다." />
    {/if}
  {/if}
</section>

<section class="ui-panel" aria-labelledby="applied-models-title">
  <h2 id="applied-models-title">적용한 이상 탐지 모델</h2>
  <p class="context">모델 점수, AI 해설과 검토 요청은 설비 화면의 이상 징후 탭에서 봅니다.</p>
  {#if bindingState === "loading"}
    <StatusNotice message="적용한 모델을 확인하고 있습니다." />
  {:else if bindingState === "failed"}
    <StatusNotice kind="uncertain" message="적용한 모델 목록을 불러오지 못했습니다. 모델이 없다는 뜻은 아닙니다." />
  {:else if !models.length}
    <p class="context">{chosen ? "이 설비에" : "아직"} 적용한 이상 탐지 모델이 없습니다.</p>
  {:else}
    <div class="scroll"><table>
      <thead><tr><th scope="col">설비</th><th scope="col">적용 모델</th><th scope="col">데이터 출처</th>
        <th scope="col">마지막 분석</th><th scope="col"><span class="visually-hidden">이동</span></th></tr></thead>
      <tbody>
        {#each models as model (model.bindingId)}
          <tr><th scope="row">{model.assetId}</th><td class="wrap">{model.packageId}</td><td>{model.sourceId}</td>
            <td>{model.lastAnalyzed === null ? "아직 없음" : (model.stepKind === "observation-window" ? "시간 구간 #" : "측정 순서 #") + model.lastAnalyzed}</td>
            <td><a href={assetTabUrl(model.assetId, "anomaly", "model")}>모델 점수 보기 →</a></td></tr>
        {/each}
      </tbody>
    </table></div>
  {/if}
</section>

<section class="ui-panel" aria-labelledby="skipped-title">
  <h2 id="skipped-title">실행되지 않은 분석</h2>
  {#if !snapshot.analyses.skippedComplete}
    <StatusNotice kind="uncertain" message="실행되지 않은 분석 기록을 모두 읽지 못했습니다. 보이지 않는 기록이 없다는 뜻은 아닙니다." />
  {/if}
  {#if !skipped.length}
    <p class="context">{snapshot.analyses.skippedComplete ? "실행되지 않은 분석 기록이 없습니다." : "표시할 기록이 없습니다."}</p>
  {:else}
    <ul class="skipped">
      {#each skipped as item, i (i)}
        <li><strong>{item.assetId} · {item.capabilityId}</strong> · {item.reason}
          <span class="context">분석 구간 {clock(item.observedStart)} ~ {clock(item.observedEnd)} · 데이터 출처 {item.sourceId}</span></li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .asset { display: grid; gap: var(--space-1); max-width: 360px; margin-block: var(--space-4); font-size: var(--font-small); font-weight: 700; }
  select { font: inherit; font-weight: 400; min-height: 40px; padding: var(--space-2) var(--space-3);
    border: 1px solid var(--color-border); border-radius: var(--radius-control); background: var(--color-surface); color: var(--color-ink); }
  section { margin-bottom: var(--space-4); display: flex; flex-direction: column; gap: var(--space-3); min-width: 0; }
  h2 { margin: 0; }
  .context { color: var(--color-ink-muted); overflow-wrap: anywhere; }
  .records, .skipped { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-3); }
  .records > li, .skipped > li { min-width: 0; }
  .counts { margin: 0; padding-inline-start: var(--space-5); color: var(--color-ink-muted); font-size: var(--font-small); }
  .counts li { overflow-wrap: anywhere; }
  .records article { border: 1px solid var(--color-border); border-radius: var(--radius-control); padding: var(--space-4);
    display: flex; flex-direction: column; gap: var(--space-2); min-width: 0; }
  .head { display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--space-2) var(--space-4); align-items: center; }
  h3 { margin: 0; font-size: var(--font-section); overflow-wrap: anywhere; }
  .badge { font-weight: 700; border: 1px solid var(--color-ink); border-radius: 999px; padding: 2px var(--space-3); font-size: var(--font-small); }
  .scroll { max-width: 100%; overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; }
  caption { text-align: left; color: var(--color-ink-muted); font-size: var(--font-small); }
  th, td { padding: var(--space-2); text-align: left; border-bottom: 1px solid var(--color-border); }
  thead th { white-space: nowrap; }
  td.wrap { overflow-wrap: anywhere; }
  .review { display: flex; flex-wrap: wrap; gap: var(--space-3); align-items: center; }
  .message { overflow-wrap: anywhere; }
  .uncertain { background: var(--color-uncertain-surface); padding: var(--space-2) var(--space-3); border-radius: var(--radius-control); }
  .failure { background: var(--color-failure-surface); color: var(--color-failure-ink); padding: var(--space-2) var(--space-3); border-radius: var(--radius-control); }
  .skipped li { overflow-wrap: anywhere; display: grid; gap: var(--space-1); }
  summary { cursor: pointer; font-weight: 650; color: var(--color-action); padding-block: var(--space-2); }
  dl { display: grid; gap: var(--space-2); margin: var(--space-2) 0; }
  dt { color: var(--color-ink-muted); font-size: var(--font-small); }
  dd { margin: 0; font-family: ui-monospace, monospace; overflow-wrap: anywhere; }
</style>
