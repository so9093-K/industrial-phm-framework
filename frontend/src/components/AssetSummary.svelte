<script lang="ts">
  import {onMount} from "svelte";
  import {flowLabel, type Asset} from "../monitor";
  import {loadLatestScores, scoreSummary, type LatestScore} from "../model-evidence";
  import {num} from "../format";
  import StatusNotice from "./StatusNotice.svelte";
  import type {AssetData} from "../asset-data";
  import {assetTabUrl, routeUrl} from "../routes";
  import CautionNote from "./CautionNote.svelte";
  import AnalysisOptions from "./AnalysisOptions.svelte";
  type Props = {
    asset: Asset;
    data: AssetData | null;
    dataState: "loading" | "ready" | "failed";
    observed: (at: string | null) => string;
  };
  let {asset, data, dataState, observed}: Props = $props();
  const stored = $derived.by(() => {
    if (dataState === "loading") return "확인하는 중";
    if (dataState === "failed" || !data) return "확인하지 못함";
    const parts: string[] = [];
    if (data.history) parts.push("시계열 신호 " + data.history.signals + "개");
    if (data.vibration) parts.push("진동 측정 " + data.vibration.measurements + "회 (측정 순서 #"
      + data.vibration.first + "~#" + data.vibration.last + ")");
    return parts.length ? parts.join(" · ") : "분석할 저장 데이터 없음";
  });
  let scores: LatestScore[] = $state([]);
  let scoreState: "loading" | "ready" | "failed" = $state("loading");
  onMount(() => {
    const request = new AbortController();
    void loadLatestScores(asset.assetId, request.signal).then((value) => {
      if (request.signal.aborted) return;
      scores = value; scoreState = "ready";
    }).catch(() => { if (!request.signal.aborted) scoreState = "failed"; });
    return () => request.abort();
  });
  function verdict(exceeds: boolean | null): string {
    return exceeds === null ? "기준 대비 정보 없음" : exceeds ? "모델 기준 초과" : "모델 기준 이하";
  }
  function attention(count: number | null): string {
    if (count === null) return "확인하지 못함";
    return count ? count + "건" : "없음";
  }
</script>

<section class="ui-panel" aria-labelledby="state-title">
  <h2 id="state-title">이상 징후</h2>
  {#if scoreState === "loading"}
    <p class="context">최근 모델 점수를 불러오고 있습니다.</p>
  {:else if scoreState === "failed"}
    <StatusNotice kind="failure" message="최근 모델 점수를 불러오지 못했습니다. 이상이 없다는 뜻은 아닙니다." />
  {:else if !scores.length}
    <p class="context">이 설비에 적용한 이상 탐지 모델이 없습니다.
      <a href={assetTabUrl(asset.assetId, "anomaly", "baseline")}>모델 없이 기준 구간 이탈 보기 →</a></p>
  {:else}
    <ul class="scores">
      {#each scores as item (item.binding.bindingId)}
        {@const summary = item.run ? scoreSummary(item.run.output) : null}
        <li>
          <strong class="verdict">{summary ? verdict(summary.exceeds) : "분석한 측정 없음"}</strong>
          <span>{item.binding.packageId}
            {#if item.run && summary}
              · 측정 순서 #{item.run.position} · 점수 {num(summary.score, "기록 없음")} / 기준 {num(summary.threshold, "기록 없음")}
            {/if}</span>
        </li>
      {/each}
    </ul>
    <p class="context"><a href={assetTabUrl(asset.assetId, "anomaly", "model")}>측정별 모델 점수 보기 →</a></p>
  {/if}
</section>

<section class="ui-panel facts-panel" aria-labelledby="summary-title">
  <h2 id="summary-title">기록 현황</h2>
  <dl class="facts">
    <div><dt>마지막 측정</dt><dd>{observed(asset.lastObservedAt)}</dd></div>
    <div><dt>수신 상태</dt><dd>{flowLabel(asset.flow)}</dd></div>
    <div><dt>확인할 항목</dt><dd>{attention(asset.attentionCount)}</dd></div>
    <div><dt>저장된 데이터</dt><dd>{stored}</dd></div>
  </dl>
  <CautionNote message="모델 점수는 학습한 평소 상태와의 차이이고, 수신 상태와 확인할 항목은 기록 현황입니다. 설비의 고장 여부를 판정하지 않습니다." />
</section>

<section class="ui-panel next">
  <AnalysisOptions assetId={asset.assetId} />
  <p class="context"><a href={routeUrl({page: "maintenance", assetId: asset.assetId, tab: "summary", method: null, data: null})}>
    정비 검토함 보기 →</a></p>
</section>

<style>
  .facts {
    margin: 0;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: var(--space-4);
  }
  .facts div { padding-bottom: var(--space-3); border-bottom: 1px solid var(--color-border); min-width: 0; }
  dt { font-size: var(--font-small); color: var(--color-ink-muted); }
  dd { margin: var(--space-2) 0 0; font-weight: 700; overflow-wrap: anywhere; }
  .next, .facts-panel { margin-top: var(--space-4); }
  .next { display: grid; gap: var(--space-3); }
  .context { color: var(--color-ink-muted); overflow-wrap: anywhere; }
  .scores { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
  .scores li { display: grid; gap: var(--space-1); padding: var(--space-3) 0; border-bottom: 1px solid var(--color-border); }
  .scores .verdict { font-size: var(--font-section); }
  .scores span { color: var(--color-ink-muted); font-size: var(--font-small); overflow-wrap: anywhere; }
</style>
