<script lang="ts">
  import {onMount} from "svelte";
  import {flowLabel, type Asset} from "../monitor";
  import {builtModelNote, isTimeWindow, loadLatestScores, modelName, scoreSummary, windowLabel, type LatestScore} from "../model-evidence";
  import {measurementLabel} from "../time-axis";
  import {num} from "../format";
  import StatusNotice from "./StatusNotice.svelte";
  import type {AssetData} from "../asset-data";
  import {assetTabUrl, routeUrl} from "../routes";
  import AnalysisOptions from "./AnalysisOptions.svelte";
  import {attentionText, readAttention, type AttentionState, type Note} from "../monitor-attention";
  import {CHANGE_REASON, changeValue, findingLinks, findingText, readRecordFindings, unjudgedText, type RecordFindings} from "../record-findings";
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
  // What the whole stored record held, not only whether it ends away from its start.
  let findings: RecordFindings | null = $state(null);
  let findingState: "idle" | "loading" | "ready" | "failed" = $state("idle");
  let showOptions = $state(false);
  $effect(() => {
    if (!data?.history) return;
    const request = new AbortController();
    findingState = "loading";
    void readRecordFindings(asset.assetId, request.signal).then((value) => {
      if (!request.signal.aborted) {findings = value; findingState = "ready";}
    }).catch(() => {if (!request.signal.aborted) findingState = "failed";});
    return () => request.abort();
  });
  onMount(() => {
    const request = new AbortController();
    void loadLatestScores(asset.assetId, request.signal).then((value) => {
      if (request.signal.aborted) return;
      scores = value; scoreState = "ready";
    }).catch(() => { if (!request.signal.aborted) scoreState = "failed"; });
    void readNotes();
    return () => {request.abort();noteRequest?.abort();};
  });
  // Models reading the same asset can disagree; a "기준 이하" beside a "기준 초과" is not a clean bill.
  // Each model's latest result is read on its own, so they are compared only when every one of them
  // analyzed the same measurement of the same source; otherwise each says where it last stands.
  const split = $derived.by(() => {
    const read = scores.map((item) => ({name: modelName(item.binding), exceeds: item.run ? scoreSummary(item.run.output).exceeds : null}));
    const over = read.filter((item) => item.exceeds === true).map((item) => item.name);
    const under = read.filter((item) => item.exceeds === false).map((item) => item.name);
    if (!over.length || !under.length) return null;
    const stream = scores.map((item) => [item.binding.sourceId, item.binding.pointId ?? "", item.binding.stepKind].join("\n"));
    const sameStream = stream.every((key) => key === stream[0]);
    const samePosition = scores.every((item) => item.run && item.run.position === scores[0].run?.position);
    // Which condition failed is said as it is: another source or point, or another last measurement.
    return {over, under, same: sameStream && samePosition, why: !sameStream ? "stream" : samePosition ? null : "position"};
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
  {#if data?.history}
    <h3 class="recent">주요 변화</h3>
    {#if findingState === "ready" && findings}
      {#if findings.record}<p class="context small">검토한 기록 · {observed(findings.record.from)} ~ {observed(findings.record.to)}</p>{/if}
      <p class="coverage" aria-label="변화 분석 범위">전체 신호 {findings.signals.length + findings.unchecked}개 중
        계산 {findings.judged}개 · 계산 불가 {findings.signals.length - findings.judged}개 · 미검토 {findings.unchecked}개</p>
    {/if}
    {#if findingState === "loading"}
      <p class="context">기록 전체를 기록 처음 30%와 비교하고 있습니다.</p>
    {:else if findingState === "failed"}
      <p class="context">기록에서 찾은 변화를 읽지 못했습니다. 변화가 없다는 뜻은 아닙니다.
        <a href={assetTabUrl(asset.assetId, "anomaly", "baseline")}>기준 구간 이탈에서 직접 보기 →</a></p>
    {:else if findings && findings.intervals.length}
      <ul class="found">
        {#each findings.intervals as item (item.start + item.channel)}
          {@const told = findingText(item, findings.bucketSeconds)}
          {@const links = findingLinks(asset.assetId, item, findings.baseline, findings.bucketSeconds, findings.record)}
          <li>
            <span class="reason">{item.reason ? CHANGE_REASON[item.reason] : "기준 구간과 달라진 구간"}</span>
            <strong>{item.label} · {told.what}</strong><span>{told.when}</span>
            {#if item.related.length}<ul class="related" aria-label="같은 구간의 다른 신호">
              {#each item.related as other (other.channel)}
                {@const target = findingLinks(asset.assetId, {...item, channel:other.channel}, findings.baseline, findings.bucketSeconds, findings.record)}
                <li>{#if target.signal}<a href={target.signal}>{other.label}</a>{:else}{other.label}{/if}
                  · {changeValue(other.reference, null)} → {changeValue(other.current, other.unit)}
                  · {other.state === "within" ? "대표값이 기준 범위 안" : other.state === "higher" ? "함께 높아짐" : "함께 낮아짐"}</li>
              {/each}
            </ul>{/if}
            <span class="go">{#if links.signal}<a href={links.signal}>신호에서 이 구간 보기 →</a>{/if}
              {#if links.previous}<a href={links.previous}>변화 직전과 비교 →</a>
              {:else if links.compare}<a href={links.compare}>기록 처음 30%와 비교 →</a>{/if}</span>
            {#if links.previous && links.compare}<details><summary>처음 기준과 비교</summary><a href={links.compare}>기록 처음 30%와 비교 →</a></details>{/if}
          </li>
        {/each}
      </ul>
      <details class="context small"><summary>변화 선정 방식과 전체 신호</summary>
        <p>계산한 신호 {findings.judged}개에서 오래 이어진 구간·기록 끝의 변화·변화 폭을 보고 서로 다른 구간을 골랐습니다.
          대표값은 집계 구간 평균의 중앙값이며, 비교 기준은 각 신호 기록의 처음 30%입니다.</p>
        <a href={assetTabUrl(asset.assetId, "anomaly", "baseline")}>기준 구간 이탈에서 다른 신호 보기 →</a></details>
    {:else if findings && findings.judged}
      <p class="context">판단한 신호 {findings.judged}개에서 기록 처음 30%의 평소 범위를 크게 벗어난 구간을 찾지 못했습니다.
        <a href={assetTabUrl(asset.assetId, "anomaly", "baseline")}>기준 구간 이탈 보기 →</a></p>
    {:else if findings}
      <p class="context">기록 처음 30%와 견줘 판단할 수 있는 신호가 없어, 변화가 있었는지 말할 수 없습니다.
        <a href={assetTabUrl(asset.assetId, "signals")}>신호를 직접 보기 →</a></p>
    {/if}
    {#if findings && findings.signals.some((row) => row.state !== "scored")}
      <p class="context small">판단하지 못한 신호 · {findings.signals.filter((row) => row.state !== "scored").map(unjudgedText).join(" · ")}</p>
    {/if}
    {#if findings?.unchecked}<p class="context small">목록 순서에 따라 앞의 {findings.signals.length}개만 확인했습니다. 중요한 신호를 자동 선별한 결과는 아닙니다.
      나머지 {findings.unchecked}개는 <a href={assetTabUrl(asset.assetId, "anomaly", "baseline")}>기준 구간 이탈에서 신호를 골라 확인</a>할 수 있습니다.</p>{/if}
  {/if}
  <h3 class="recent">마지막 측정의 확인 항목</h3>
  {#if notesState === "loading"}
    <p class="context">확인할 항목을 읽고 있습니다.</p>
  {:else if departures.length || others.length}
    <ul class="others">
      {#each [...departures, ...others] as note (note.id)}<li><strong>{note.label}</strong> <span>{note.detail}</span> <a href={note.href}>{note.action} →</a></li>{/each}
    </ul>
  {:else if notes}
    <p class="context">기록의 마지막 측정 기준으로 추가 확인 항목은 없습니다.</p>
  {/if}
  <p class="context"><a href={assetTabUrl(asset.assetId, "signals")}>측정 신호 추이 보기 →</a></p>
</section>

<section class="ui-panel scores-panel" aria-labelledby="state-title">
  <h2 id="state-title">이상 징후</h2>
  {#if scoreState === "loading"}
    <p class="context">최근 모델 점수를 불러오고 있습니다.</p>
  {:else if scoreState === "failed"}
    <StatusNotice kind="failure" message="최근 모델 점수를 불러오지 못했습니다. 이상이 없다는 뜻은 아닙니다." />
  {:else if !scores.length}
    <p class="context">이 설비에 적용한 이상 탐지 모델이 없습니다.
      {#if !departures.length}<a href={assetTabUrl(asset.assetId, "anomaly", "baseline")}>모델 없이 기준 구간 이탈 보기 →</a>{/if}
      {#if data?.history}<a href={assetTabUrl(asset.assetId, "anomaly", "model")}>이 설비 데이터로 모델 만들기 →</a>{/if}</p>
  {:else}
    <ul class="scores">
      {#each scores as item (item.binding.bindingId)}
        {@const summary = item.run ? scoreSummary(item.run.output) : null}
        {@const note = builtModelNote(item.binding)}
        <li>
          <strong class="verdict">{summary ? verdict(summary.exceeds) : "분석한 측정 없음"}</strong>
          <span>{modelName(item.binding)}
            {#if item.run && summary}
              · {isTimeWindow(item.binding.stepKind) ? windowLabel(item.run.position) : measurementLabel(item.run.position, item.binding.sourceId === data?.vibration?.timing?.sourceId ? data.vibration.timing.periodSeconds : null)} · 점수 {num(summary.score, "기록 없음")} / 기준 {num(summary.threshold, "기록 없음")}
            {/if}</span>
          {#if note}<span class="note">{note}</span>{/if}
        </li>
      {/each}
    </ul>
    {#if split?.same}
      <p class="split">같은 측정에서 모델 판단이 다릅니다 · {split.over.join(", ")}는 기준 초과, {split.under.join(", ")}는 기준 이하입니다.
        기준 이하가 정상이라는 뜻은 아니므로 측정별 점수와 원본을 함께 확인하세요.</p>
    {:else if split?.why === "stream"}
      <p class="split">모델들이 서로 다른 데이터 출처나 측정 위치를 분석해, 같은 출처·측정 위치·측정의 결과가 아니므로 직접 견줄 수 없습니다.
        모델마다 위에 적힌 결과를 따로 확인하세요.</p>
    {:else if split}
      <p class="split">같은 출처·측정 위치를 분석하지만 마지막으로 분석한 측정이 서로 달라 직접 견줄 수 없습니다. 위에 적힌 각 모델의 마지막 측정을 확인하고,
        같은 측정의 점수는 측정별 모델 점수에서 견줘 보세요.</p>
    {/if}
    <p class="context"><a href={assetTabUrl(asset.assetId, "anomaly", "model")}>측정별 모델 점수 보기 →</a></p>
  {/if}
</section>

<details class="ui-panel next" ontoggle={(event) => showOptions=event.currentTarget.open}>
  <summary>추가 분석</summary>
  {#if showOptions}<AnalysisOptions assetId={asset.assetId} level={3} />{/if}
  <p class="context"><a href={routeUrl({page: "investigations", assetId: asset.assetId, tab: "summary", method: null, data: null})}>
    저장된 분석 결과 보기 →</a></p>
</details>

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
  .next, .scores-panel { margin-top: var(--space-4); }
  .recent { font-size: var(--font-body); margin: var(--space-5) 0 var(--space-2); }
  .next { display: grid; gap: var(--space-3); }
  .context { color: var(--color-ink-muted); overflow-wrap: anywhere; }
  .scores { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
  .scores li { display: grid; gap: var(--space-1); padding: var(--space-3) 0; border-bottom: 1px solid var(--color-border); }
  .scores .verdict { font-size: var(--font-section); }
  .split { margin: 0; padding: var(--space-3); border-left: 3px solid var(--color-caution-ink); background: var(--color-uncertain-surface); overflow-wrap: anywhere; }
  .scores span { color: var(--color-ink-muted); font-size: var(--font-small); overflow-wrap: anywhere; }
  .others li { margin: 0 0 var(--space-3); overflow-wrap: anywhere; }
  .others span { color: var(--color-ink-muted); font-size: var(--font-small); }
  .others { list-style: none; margin: 0; padding: 0; }
  .small { font-size: var(--font-small); }
  .coverage { padding: var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-control); font-size: var(--font-small); overflow-wrap: anywhere; }
  .found { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-3); }
  .found li { display: grid; gap: var(--space-1); overflow-wrap: anywhere; }
  .found > li { padding: var(--space-4); border: 1px solid var(--color-border); border-radius: var(--radius-control); }
  .found .reason { color: var(--color-action); font-weight: 650; font-size: var(--font-small); }
  .related { list-style: none; padding: 0; margin-block: var(--space-2); font-size: var(--font-small); }
  .related li { display: block; padding-block: var(--space-1); color: var(--color-ink-muted); }
  summary { cursor: pointer; font-weight: 650; padding-block: var(--space-2); }
  .found span { color: var(--color-ink-muted); font-size: var(--font-small); }
  .found .go { display: flex; flex-wrap: wrap; gap: var(--space-1) var(--space-4); font-size: var(--font-small); }
</style>
