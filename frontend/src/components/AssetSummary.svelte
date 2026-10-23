<script lang="ts">
  import {onMount} from "svelte";
  import {flowLabel, type Asset} from "../monitor";
  import {loadLatestScores, modelName, scoreSummary, type LatestScore} from "../model-evidence";
  import {measurementLabel} from "../time-axis";
  import {num} from "../format";
  import StatusNotice from "./StatusNotice.svelte";
  import type {AssetData} from "../asset-data";
  import {assetTabUrl, routeUrl} from "../routes";
  import AnalysisOptions from "./AnalysisOptions.svelte";
  import {attentionText, readAttention, type AttentionState, type Note} from "../monitor-attention";
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
    if (data.vibration) parts.push("진동 측정 " + data.vibration.measurements + "회 ("
      + data.vibration.first + "~" + data.vibration.last + "번째)");
    return parts.length ? parts.join(" · ") : "분석할 저장 데이터 없음";
  });
  let scores: LatestScore[] = $state([]);
  let scoreState: "loading" | "ready" | "failed" = $state("loading");
  // The same items 관측 현황 lists for this asset; null while unread or unreadable.
  let notes: Note[] | null = $state(null);
  let notesState: AttentionState = $state("loading");
  let noteRequest: AbortController | null = null;
  async function readNotes() {
    noteRequest?.abort();
    const request = new AbortController(); noteRequest = request;
    notes = null; notesState = "loading";
    try {
      const read = await readAttention(request.signal);
      if (!request.signal.aborted) {notes = read.groups.find(group=>group.assetId===asset.assetId)?.notes??[]; notesState = read.state;}
    } catch {if (!request.signal.aborted) {notes = null; notesState = "failed";}}
  }
  const departures = $derived.by((): Note[] => { const read: Note[] | null = notes; return (read ?? []).filter((note) => note.kind === "departure"); });
  // The interval context can differ from the latest score, especially across an allowed gap.
  const others = $derived.by((): Note[] => { const read: Note[] | null = notes; return (read ?? []).filter((note) => note.kind !== "departure"); });
  onMount(() => {
    const request = new AbortController();
    void loadLatestScores(asset.assetId, request.signal).then((value) => {
      if (request.signal.aborted) return;
      scores = value; scoreState = "ready";
    }).catch(() => { if (!request.signal.aborted) scoreState = "failed"; });
    void readNotes();
    return () => {request.abort();noteRequest?.abort();};
  });
  function verdict(exceeds: boolean | null): string {
    return exceeds === null ? "기준 대비 정보 없음" : exceeds ? "모델 기준 초과" : "모델 기준 이하";
  }
  // Vibration deliveries carry an order, not always a clock; say which one is last.
  const lastMeasured = $derived(!asset.lastObservedAt && data?.vibration
    ? measurementLabel(data.vibration.last,data.vibration.timing?.periodSeconds) + " · 측정 시각 기록 없음" : observed(asset.lastObservedAt));
  // The same count as the asset list: the monitor's own items plus model, receipt and baseline notes.
  const attentionCount = $derived.by((): number | null => {
    const read: Note[] | null = notes;
    return asset.attentionCount === null && read === null ? null : (asset.attentionCount ?? 0) + (read?.length ?? 0);
  });
  function attention(count: number | null): string {
    return attentionText(count,notesState);
  }
</script>

<section class="ui-panel" aria-labelledby="state-title">
  <h2 id="state-title">이상 징후</h2>
  {#if scoreState === "loading"}
    <p class="context">최근 모델 점수를 불러오고 있습니다.</p>
  {:else if scoreState === "failed"}
    <StatusNotice kind="failure" message="최근 모델 점수를 불러오지 못했습니다. 이상이 없다는 뜻은 아닙니다." />
  {:else if !scores.length}
    {#each departures as note (note.id)}
      <p class="departure"><strong>{note.label}</strong> <span>{note.detail}</span> <a href={note.href}>{note.action} →</a></p>
    {/each}
    <p class="context">이 설비에 적용한 이상 탐지 모델이 없습니다.
      {#if !departures.length}<a href={assetTabUrl(asset.assetId, "anomaly", "baseline")}>모델 없이 기준 구간 이탈 보기 →</a>{/if}</p>
  {:else}
    <ul class="scores">
      {#each scores as item (item.binding.bindingId)}
        {@const summary = item.run ? scoreSummary(item.run.output) : null}
        <li>
          <strong class="verdict">{summary ? verdict(summary.exceeds) : "분석한 측정 없음"}</strong>
          <span>{modelName(item.binding)}
            {#if item.run && summary}
              · {item.binding.stepKind === "observation-window" ? "시간 구간 #" + item.run.position : measurementLabel(item.run.position, item.binding.sourceId === data?.vibration?.timing?.sourceId ? data.vibration.timing.periodSeconds : null)} · 점수 {num(summary.score, "기록 없음")} / 기준 {num(summary.threshold, "기록 없음")}
            {/if}</span>
        </li>
      {/each}
    </ul>
    <p class="context"><a href={assetTabUrl(asset.assetId, "anomaly", "model")}>측정별 모델 점수 보기 →</a></p>
  {/if}
</section>

<section class="ui-panel facts-panel" aria-labelledby="summary-title">
  <h2 id="summary-title">측정 현황</h2>
  {#if notesState === "partial" || notesState === "failed"}
    <StatusNotice kind="uncertain" message="확인 항목을 일부 읽지 못했습니다. 표시된 건수는 확인된 항목만 포함합니다."
      actionLabel="확인 항목 다시 읽기" onAction={() => void readNotes()} />
  {/if}
  <dl class="facts">
    <div><dt>마지막 측정</dt><dd>{lastMeasured}</dd></div>
    <div><dt>수신 상태</dt><dd>{flowLabel(asset.flow)}{#if asset.flow !== "stored-history" && asset.lastReceivedAt}
      <small>마지막 수신 {observed(asset.lastReceivedAt)}</small>{/if}</dd></div>
    <div><dt>확인할 항목</dt><dd>{attention(attentionCount)}</dd></div>
    <div><dt>저장된 데이터</dt><dd>{stored}</dd></div>
  </dl>
  {#if others.length}
    <ul class="others">
      {#each others as note (note.id)}<li><strong>{note.label}</strong> <span>{note.detail}</span> <a href={note.href}>{note.action} →</a></li>{/each}
    </ul>
  {/if}
</section>

<section class="ui-panel next">
  <AnalysisOptions assetId={asset.assetId} />
  <p class="context"><a href={routeUrl({page: "investigations", assetId: asset.assetId, tab: "summary", method: null, data: null})}>
    저장된 분석 결과 보기 →</a></p>
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
  dd small { display: block; margin-top: var(--space-1); font-weight: 400; font-size: var(--font-small); color: var(--color-ink-muted); }
  .next, .facts-panel { margin-top: var(--space-4); }
  .next { display: grid; gap: var(--space-3); }
  .context { color: var(--color-ink-muted); overflow-wrap: anywhere; }
  .scores { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
  .scores li { display: grid; gap: var(--space-1); padding: var(--space-3) 0; border-bottom: 1px solid var(--color-border); }
  .scores .verdict { font-size: var(--font-section); }
  .scores span { color: var(--color-ink-muted); font-size: var(--font-small); overflow-wrap: anywhere; }
  .departure, .others li { margin: 0 0 var(--space-3); overflow-wrap: anywhere; }
  .departure span, .others span { color: var(--color-ink-muted); font-size: var(--font-small); }
  .others { list-style: none; margin: var(--space-4) 0 0; padding: 0; }
</style>
