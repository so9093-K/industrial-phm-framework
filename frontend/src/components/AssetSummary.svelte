<script lang="ts">
  import {recordParams} from "../record-context";
  import {readOverview, type OverviewRow} from "../asset-overview";
  import OverviewTrace from "./OverviewTrace.svelte";
  import ChangeInterval from "./ChangeInterval.svelte";
  import FindingContext from "./FindingContext.svelte";
  import OperationLevels from "./OperationLevels.svelte";
  import VibrationFindings from "./VibrationFindings.svelte";
  import RecordStrip from "./RecordStrip.svelte";
  import {readVibrationFindings, vibrationLinks, type VibrationFindings as VibrationRecord} from "../vibration-findings";
  import ChangeReview from "./ChangeReview.svelte";
  import ChangeReviewArchive from "./ChangeReviewArchive.svelte";
  let reviewRevision = $state(0);
  let archiveOpen = $state(false);
  let openReviews:Record<string,boolean> = $state({});
  import SourceIdentity from "./SourceIdentity.svelte";
  import {onMount} from "svelte";
  import {flowLabel, type Asset} from "../monitor";
  import {builtModelNote, isTimeWindow, loadLatestScores, modelName, scoreSummary, windowLabel, type LatestScore} from "../model-evidence";
  import {readScoreTrend, trendSummary, type ScoreTrend} from "../model-trend";
  import {readModelOperation, unlearnedText} from "../model-operation";
  import {modelAtChange, rareAtChange} from "../model-context";
  import type {ModelOperation} from "../model-operation";
  import {measurementLabel} from "../time-axis";
  import {num} from "../format";
  import StatusNotice from "./StatusNotice.svelte";
  import type {AssetData} from "../asset-data";
  import {assetTabUrl, routeUrl} from "../routes";
  import AnalysisOptions from "./AnalysisOptions.svelte";
  import {attentionText, readAttention, type AttentionState, type Note} from "../monitor-attention";
  import {changeValue, copiedGroups, findingLinks, findingSpan, findingText, readRecordFindings, bandName, percent, unjudgedText, type CheckedSignal, type FoundInterval, type RecordFindings} from "../record-findings";
  import {CHANGE_WHY, changeSentence} from "../change-story";
  import ChangeNumbers from "./ChangeNumbers.svelte";
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
  let histories: Record<string, "loading" | "failed" | {trend: ScoreTrend; operation: ModelOperation | null; unlearned: string | null}> = $state({});
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
  // 모델 기준과 견준 확인 항목은 모델 질문 아래에서, 나머지는 마지막 측정 질문 아래에서 답한다.
  const lastNotes = $derived([...departures, ...others.filter((note) => note.kind !== "threshold" && note.kind !== "crossing")]);
  // What the whole stored record held, not only whether it ends away from its start.
  let quietMain:OverviewRow["main"]=$state(null);
  let findings: RecordFindings | null = $state(null);
  let findingState: "idle" | "loading" | "ready" | "failed" = $state("idle");
  const cumulative = $derived.by((): CheckedSignal[] => {
    const read: RecordFindings | null = findings;
    return read?.signals.filter(row => row.state === "cumulative") ?? [];
  });
  const copies = $derived.by(() => { const read: RecordFindings | null = findings; return read ? copiedGroups(read.signals) : []; });
  const copiedCount = $derived.by(() => { const read: RecordFindings | null = findings; return read?.signals.filter(row => row.state === "copied").length ?? 0; });
  const quietSignal=$derived.by(():CheckedSignal|undefined=>{const current:RecordFindings|null=findings;return current?.signals.find(row=>quietMain?.context&&row.context?.key===quietMain.context.key)??current?.signals.find(row=>row.state==="constant"||row.state==="scored");});
  function signalHref(signal:CheckedSignal|undefined):string {
    const url=new URL(assetTabUrl(asset.assetId,"signals",null,"history",signal?.channel??null),location.origin);
    for(const [key,value] of Object.entries(recordParams(signal?.context)))url.searchParams.set(key,value);
    return url.pathname+url.search;
  }
  let showOptions = $state(false);
  // 진동 기록의 변화도 시계열 변화와 같은 자리에서 고르고 본다.
  let vibration: VibrationRecord | null = $state(null);
  let vibrationState: "idle" | "loading" | "ready" | "failed" = $state("idle");
  $effect(() => {
    if (!data?.vibration) return;
    const request = new AbortController();
    vibrationState = "loading";
    void readVibrationFindings(asset.assetId, request.signal).then((value) => {
      if (!request.signal.aborted) {vibration = value; vibrationState = "ready";}
    }).catch(() => {if (!request.signal.aborted) vibrationState = "failed";});
    return () => request.abort();
  });
  // 가운데에는 변화 하나만 크게 보이고, 나머지는 오른쪽 목록에서 골라 바꿔 본다.
  type Pick = {kind: "history" | "vibration"; index: number};
  let picked: Pick | null = $state(null);
  const focus = $derived.by((): Pick | null => {
    if (picked) return picked;
    const history: RecordFindings | null = findings, measured: VibrationRecord | null = vibration;
    if (history?.intervals.length) return {kind: "history", index: 0};
    if (measured?.intervals.length) return {kind: "vibration", index: 0};
    return null;
  });
  const vibrationPlace = (at: number) => measurementLabel(at, vibration?.periodSeconds);
  const focusSpan = $derived.by(() => {
    const shown = focus, history: RecordFindings | null = findings, measured: VibrationRecord | null = vibration;
    if (shown?.kind === "history" && history?.intervals[shown.index]) {
      const item = history.intervals[shown.index];
      const own = item.operation ? history.operation.find(entry => entry.key === item.operation?.key) : undefined;
      return {axis: "time" as const, from: Date.parse(item.start), to: Date.parse(item.end), sourceId: item.context?.sourceId ?? null,
        condition: own && item.band != null ? bandName(own, item.band) : null,
        pointId: item.context?.pointId ?? null, label: findingText(item, item.bucketSeconds ?? history.bucketSeconds).when};
    }
    if (shown?.kind === "vibration" && measured?.intervals[shown.index]) {
      const change = measured.intervals[shown.index];
      return {axis: "acquisition" as const, from: change.from, to: change.to, sourceId: null, pointId: null, condition: null,
        label: vibrationPlace(change.from) + " ~ " + vibrationPlace(change.to)};
    }
    return null;
  });
  /** 이 모델이 가운데 변화와 같은 기록을 분석했는지: 시계열 모델은 같은 출처·위치, 진동 모델은 진동 변화. */
  function readsFocus(binding: LatestScore["binding"]): boolean {
    const span = focusSpan;
    if (!span) return false;
    if (span.axis === "time") return isTimeWindow(binding.stepKind) && binding.sourceId === span.sourceId && (binding.pointId ?? null) === span.pointId;
    return !isTimeWindow(binding.stepKind);
  }
  const otherChanges = $derived.by(() => {
    const history: RecordFindings | null = findings, measured: VibrationRecord | null = vibration, shown = focus;
    const rows: {key: string; pick: Pick; label: string; line: string; when: string; href: string | null}[] = [];
    history?.intervals.forEach((item, index) => {
      if (shown?.kind === "history" && shown.index === index) return;
      rows.push({key: "h" + index, pick: {kind: "history", index}, label: item.label,
        line: "처음 30%보다 " + (item.direction === "up" ? "높음" : "낮음") + (item.reference != null && item.typical != null ? " · " + changeValue(item.reference, null) + " → " + changeValue(item.typical, item.unit) : ""),
        when: findingText(item, item.bucketSeconds ?? history.bucketSeconds).when,
        href: findingLinks(asset.assetId, item, history.baseline, history.bucketSeconds, history.record).signal});
    });
    measured?.intervals.forEach((change, index) => {
      if (shown?.kind === "vibration" && shown.index === index) return;
      rows.push({key: "v" + index, pick: {kind: "vibration", index}, label: change.label,
        line: "처음 30%보다 " + (change.direction === "up" ? "높음" : "낮음") + (change.reference != null && change.typical != null ? " · " + changeValue(change.reference, null) + " → " + changeValue(change.typical, change.unit) : ""),
        when: vibrationPlace(change.from) + " ~ " + vibrationPlace(change.to) + " · " + (change.to - change.from + 1) + "회",
        href: vibrationLinks(asset.assetId, change).signal});
    });
    return rows;
  });
  $effect(() => {
    if (!data?.history) return;
    const request = new AbortController();
    quietMain=null;
    findingState = "loading";
    void readRecordFindings(asset.assetId, request.signal).then(async(value) => {
      if (!request.signal.aborted) {findings = value; findingState = "ready";}
      if(!request.signal.aborted&&!value.intervals.length){
        try{const overview=await readOverview(asset.assetId,request.signal);if(!request.signal.aborted)quietMain=overview.main;}catch{ /* The raw signal remains available if its preview fails. */ }
      }
    }).catch(() => {if (!request.signal.aborted) findingState = "failed";});
    return () => request.abort();
  });
  onMount(() => {
    const request = new AbortController();
    void loadLatestScores(asset.assetId, request.signal).then((value) => {
      if (request.signal.aborted) return;
      scores = value; scoreState = "ready";
      // 최근 결과 하나만으로는 모델이 기록 전체와 이 변화 구간을 어떻게 봤는지 알 수 없어, 점수 기록도 읽는다.
      for (const item of value) {
        const id = item.binding.bindingId;
        histories = {...histories, [id]: "loading"};
        void Promise.all([readScoreTrend(item.binding, request.signal),
          isTimeWindow(item.binding.stepKind) ? readModelOperation(id, request.signal).catch(() => null) : Promise.resolve(null)])
          .then(([trend, operation]) => { if (!request.signal.aborted) histories = {...histories, [id]: {trend, operation, unlearned: operation ? unlearnedText(operation) : null}}; })
          .catch(() => { if (!request.signal.aborted) histories = {...histories, [id]: "failed"}; });
      }
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

{#snippet historyCard(history: RecordFindings, item: FoundInterval)}
  {@const told = findingText(item, item.bucketSeconds ?? history.bucketSeconds)}
  {@const own = item.operation ? history.operation.find(entry => entry.key === item.operation?.key) : undefined}
  {@const links = findingLinks(asset.assetId, item, history.baseline, history.bucketSeconds, history.record)}
  {@const condition = own && item.band != null ? bandName(own, item.band) : null}
  <h3 class="change-sentence">{changeSentence(item, findingSpan(item), condition)}</h3>
  <div class="card-top">
    <ChangeNumbers facts={item} fallback={told.what} />
    <div class="finding-actions">{#if links.signal}<a class="ui-button ui-button-primary" href={links.signal}>변화 구간 조사하기 →</a>{/if}
    {#if item.reviewKey}<details class="review" ontoggle={event=>{openReviews={...openReviews,[item.reviewKey!]:event.currentTarget.open};}}><summary>판단·메모</summary>
      {#if openReviews[item.reviewKey]}<ChangeReview assetId={asset.assetId} finding={item} onSaved={()=>reviewRevision++} />{/if}
    </details>{/if}</div>
  </div>
  <ChangeInterval finding={item} height={240} />
  <RecordStrip finding={item} {condition} />
  {#if item.reason}<p class="change-why">{CHANGE_WHY[item.reason]}</p>{/if}
  <FindingContext {item} operation={own} compareHref={links.compare??links.previous} relation={links.relation}/>
  <details><summary>비교 기준·출처·관련 신호</summary>
  {#if item.context}<SourceIdentity id={item.context.sourceId} pointId={item.context.pointId} interpretationId={item.context.interpretationId} among={history.signals.flatMap(row=>row.context?[row.context.sourceId]:[])}/>{/if}
  <p class="context small">대표값은 집계 구간 평균의 중앙값입니다. {item.kind === "level-change" ? "기준 기간에 일정하던 값이 달라졌습니다." : "비교 범위 " + changeValue(item.usual.low, null) + " ~ " + changeValue(item.usual.high, item.unit) + "와 견줬습니다."}</p>
  {#if item.related.length}<ul class="related" aria-label="같은 구간의 다른 신호">
    {#each item.related as other (other.channel)}
      {@const target = findingLinks(asset.assetId, {...item, channel:other.channel, context:other.context ?? item.context}, history.baseline, history.bucketSeconds, history.record)}
      <li>{#if target.signal}<a href={target.signal}>{other.label}</a>{:else}{other.label}{/if}
        · {changeValue(other.reference, null)} → {changeValue(other.current, other.unit)}
        · {other.state === "within" ? "대표값이 기준 범위 안" : other.state === "higher" ? "함께 높아짐" : "함께 낮아짐"}</li>
    {/each}
  </ul>{/if}
    {#if item.baseline}<p class="context small">비교 기준 · 이 기록의 처음 30% · {observed(item.baseline.from)} ~ {observed(item.baseline.to)}</p>{/if}
    {#if links.previous && links.compare}<a href={links.previous}>변화 직전과 비교 →</a>{/if}
    {#if item.reason === "record-end"}<a href={links.outlook}>이 신호의 기록 마지막 시점 전망 →</a>{/if}
  </details>
{/snippet}

{#snippet cumulativeRecords()}
  <ul aria-label="누적 기록">
    {#each cumulative as row (row.context?.key ?? row.channel)}<li><strong>{row.label}</strong> ·
      {row.first == null ? "처음 값 미확인" : changeValue(row.first, null)} → {row.last == null ? "마지막 값 미확인" : changeValue(row.last, row.unit)}</li>{/each}
  </ul>
  <details class="context small"><summary>누적 기록의 분석 방식</summary><p>누적값은 처음 값과 마지막 값을 표시하며, 기준 기간 대비 변화 구간에서는 제외합니다.</p></details>
{/snippet}

<div class="summary-layout">
<section class="ui-panel facts-panel" aria-labelledby="summary-title">
  <h2 id="summary-title" class="eyebrow">기록에서 찾은 주요 변화</h2>
  {#if notesState === "partial" || notesState === "failed"}
    <StatusNotice kind="uncertain" message="확인 항목을 일부 읽지 못했습니다. 표시된 건수는 확인된 항목만 포함합니다."
      actionLabel="확인 항목 다시 읽기" onAction={() => void readNotes()} />
  {/if}
  {#if data?.history && findingState === "ready" && copies.length}
      <section class="data-check" aria-labelledby="data-check-title">
        <h3 id="data-check-title">데이터 확인 필요 · 신호 {copiedCount}개는 변화 판단에서 제외했습니다</h3>
        <details><summary>해당 신호와 기간 확인</summary><p>아래 신호는 일부 기간에 다른 항목의 값이 그대로 기록되어 있습니다.</p>
        <ul>{#each copies as group (group.from + group.to)}
          <li><strong>{observed(group.from)} ~ {observed(group.to)}</strong> · {group.items.map(item => item.label + "에 " + item.origin + " 값").join(", ")}</li>
        {/each}</ul></details>
      </section>
  {/if}
  {#if focus?.kind === "history" && findings?.intervals[focus.index]}
    <ul class="found" aria-label="주요 변화"><li id="primary-change">{#key focus.index}{@render historyCard(findings, findings.intervals[focus.index])}{/key}</li></ul>
  {:else if focus?.kind === "vibration" && vibration?.intervals[focus.index]}
    <ul class="found" aria-label="주요 변화"><li id="primary-change">{#key focus.index}<VibrationFindings assetId={asset.assetId} record={vibration} change={vibration.intervals[focus.index]} />{/key}</li></ul>
  {:else if data?.history && findingState === "loading"}
    <p class="context">기록 전체를 기록 처음 30%와 비교하고 있습니다.</p>
  {:else if data?.history && findingState === "failed"}
    <p class="context">기록에서 찾은 변화를 불러오지 못했습니다.
      <a href={assetTabUrl(asset.assetId, "anomaly", "baseline")}>신호를 골라 변화 찾기 →</a></p>
  {:else if data?.history && findings && findings.judged}
    <section class="quiet-record" aria-label="변화가 없는 기록 살펴보기">
      <p class="context">{findings.operation.length?"같은 운전 수준의 측정끼리 비교해":"기록 초반과 비교해"} 뚜렷하게 다른 구간을 찾지 못했습니다. 전체 추세와 값의 범위를 살펴보세요.</p>
      {#if quietMain}<h3>{quietMain.label}</h3><OverviewTrace main={quietMain} height={260}/>{#if findings.operation.length}<p class="context small">추세에는 서로 다른 운전 상태의 기록도 함께 표시합니다.</p>{/if}{/if}
      <div class="quiet-facts">
        {#if quietSignal}{#if quietSignal.context}<SourceIdentity id={quietSignal.context.sourceId} pointId={quietSignal.context.pointId} interpretationId={quietSignal.context.interpretationId}/>{/if}
          {#if quietSignal.latest}<p>마지막 구간 평균 <strong>{changeValue(quietSignal.latest.value,quietSignal.unit)}</strong> · {observed(quietSignal.latest.at)}</p>{/if}
          {#if quietSignal.range}<p>구간별 평균의 범위 {changeValue(quietSignal.range.low,null)} ~ {changeValue(quietSignal.range.high,quietSignal.unit)}</p>{/if}
        {/if}
        <a class="ui-button ui-button-primary" href={signalHref(quietSignal)}>원본 신호 추세 보기 →</a>
        <a href={assetTabUrl(asset.assetId,"anomaly","baseline")}>기준 구간과 다른 신호 확인 →</a>
      </div>
    </section>
  {:else if data?.history && cumulative.length}
    {@render cumulativeRecords()}
  {:else if data?.history && findings && !data?.vibration}
    <p class="context">기록 처음 30%와 견줘 판단할 수 있는 신호가 없어, 변화가 있었는지 말할 수 없습니다.
      <a href={assetTabUrl(asset.assetId, "signals")}>신호를 직접 보기 →</a></p>
  {:else if data?.vibration && vibrationState === "loading"}
    <p class="context">진동 측정 전체를 처음 30%와 비교하고 있습니다.</p>
  {:else if data?.vibration && vibrationState === "failed"}
    <p class="context">진동 측정에서 찾은 변화를 불러오지 못했습니다. <a href={assetTabUrl(asset.assetId, "signals", null, "vibration")}>진동 특징 추이 보기 →</a></p>
  {:else if data?.vibration && vibration?.judged}
    <p class="context">진동 특징 {vibration.judged}개에서 처음 30%와 견줘 크게 달라진 구간을 찾지 못했습니다. <a href={assetTabUrl(asset.assetId, "signals", null, "vibration")}>진동 특징 추이 보기 →</a></p>
  {/if}
</section>

<aside class="rail" aria-label="다른 변화와 이어서 확인할 것">
  {#if otherChanges.length}
    <section class="ui-panel rail-section" aria-labelledby="others-title">
      <h2 id="others-title">이 기록의 다른 변화 {otherChanges.length}건</h2>
      <ul class="other-changes">
        {#each otherChanges as row (row.key)}
          <li><button type="button" onclick={() => picked = row.pick} aria-label={row.label + " 변화 크게 보기"}>
            <strong>{row.label}</strong><span>{row.line}</span><small>{row.when}</small></button>
            {#if row.href}<a href={row.href}>구간 조사 →</a>{/if}</li>
        {/each}
      </ul>
      {#if data?.history}<p class="context small"><a href={assetTabUrl(asset.assetId, "anomaly", "baseline")}>다른 신호의 변화 찾기 →</a></p>{/if}
    </section>
  {/if}
  <section class="ui-panel more rail-section" aria-labelledby="more-title">
  <h2 id="more-title">이어서 확인할 것</h2>
  <dl class="rows">
    <div><dt id="state-title">모델은 어떻게 봤나요?</dt><dd>
      {#if scoreState === "loading"}
        <p class="context">최근 모델 점수를 불러오고 있습니다.</p>
      {:else if scoreState === "failed"}
        <StatusNotice kind="failure" message="최근 모델 점수를 불러오지 못했습니다." />
      {:else if !scores.length}
        <p class="context">이 설비에 적용한 이상 탐지 모델이 없어 모델의 판단은 없습니다.
          {#if data?.history}<a href={assetTabUrl(asset.assetId, "anomaly", "model")}>이 설비 데이터로 모델 만들기 →</a>{/if}</p>
      {:else}
        <ul class="scores" aria-labelledby="state-title">
          {#each scores as item (item.binding.bindingId)}
            {@const summary = item.run ? scoreSummary(item.run.output) : null}
            {@const note = builtModelNote(item.binding)}
            {@const read = histories[item.binding.bindingId]}
            {@const span = focusSpan}
            <li>
              <p class="model-name"><strong>{modelName(item.binding)}</strong>{#if note}<span class="note">{note}</span>{/if}</p>
              {#if typeof read === "object"}
                {@const total = trendSummary(read.trend)}
                {#if span && readsFocus(item.binding)}
                  {@const at = modelAtChange(read.trend, span, span.axis)}
                  {@const rare = span.condition && read.operation ? rareAtChange(read.operation, span.condition) : null}
                  <p><span class="what">이 변화 구간</span>{at.analyzed ? "분석 " + at.analyzed.toLocaleString("ko-KR") + "회 중 기준 초과 " + at.exceeded.toLocaleString("ko-KR") + "회" : "이 구간을 분석한 결과가 없습니다"}</p>
                  {#if rare !== null && at.exceeded}<p class="caution-line">이 변화는 {span.condition} 중의 변화인데, 모델을 학습한 기간에는 이 운전 상태가 {rare === 0 ? "전혀 없었습니다" : rare < 0.01 ? "1% 미만이었습니다" : percent(rare) + "뿐이었습니다"}. 이 구간의 기준 초과만으로 변화를 확인했다고 보기는 어렵습니다.</p>{/if}
                {:else if span}
                  <p class="context">가운데 변화와 다른 데이터를 분석한 모델이라, 그 변화 구간의 결과는 없습니다.</p>
                {/if}
                <p><span class="what">기록 전체</span>분석 {total.analyzed.toLocaleString("ko-KR")}회 중 기준 초과 {total.exceeded.toLocaleString("ko-KR")}회{read.trend.truncated ? " (기록이 많아 앞부분만)" : ""}</p>
                {#if read.unlearned}<p class="context">{read.unlearned}</p>{/if}
              {:else if read === "loading"}<p class="context">점수 기록을 읽고 있습니다.</p>{/if}
              <p><span class="what">최근 결과</span>{#if item.run && summary}{isTimeWindow(item.binding.stepKind) ? windowLabel(item.run.position) : measurementLabel(item.run.position, item.binding.sourceId === data?.vibration?.timing?.sourceId ? data.vibration.timing.periodSeconds : null)} · <strong>{verdict(summary.exceeds)}</strong> (점수 {num(summary.score, "기록 없음")} / 기준 {num(summary.threshold, "기록 없음")}){:else}분석한 측정 없음{/if}</p>
            </li>
          {/each}
        </ul>
        {#if split?.same}
          <p class="split">같은 측정에서 모델 판단이 다릅니다 · {split.over.join(", ")}는 기준 초과, {split.under.join(", ")}는 기준 이하입니다.
            같은 측정의 점수와 원본을 함께 확인하세요.</p>
        {:else if split?.why === "stream"}
          <p class="split">모델들이 서로 다른 데이터 출처나 측정 위치를 분석해, 같은 출처·측정 위치·측정의 결과가 아니므로 직접 견줄 수 없습니다.
            모델마다 위에 적힌 결과를 따로 확인하세요.</p>
        {:else if split}
          <p class="split">같은 출처·측정 위치를 분석하지만 마지막으로 분석한 측정이 서로 달라 직접 견줄 수 없습니다. 위에 적힌 각 모델의 마지막 측정을 확인하고,
            같은 측정의 점수는 측정별 모델 점수에서 견줘 보세요.</p>
        {/if}
        <p><a href={assetTabUrl(asset.assetId, "anomaly", "model")}>측정마다 모델 점수가 어떻게 변했는지 보기 →</a></p>
      {/if}
    </dd></div>
    <div><dt>마지막 측정은 어땠나요?</dt><dd>
      <p>{lastMeasured} · {flowLabel(asset.flow)}{#if asset.flow !== "stored-history" && asset.lastReceivedAt} · 마지막 수신 {observed(asset.lastReceivedAt)}{/if}</p>
      {#if notesState === "loading"}
        <p class="context">확인할 항목을 읽고 있습니다.</p>
      {:else if lastNotes.length}
        <ul class="others" aria-label="마지막 측정의 확인 항목">
          {#each lastNotes as note (note.id)}<li><strong>{note.label}</strong> <span>{note.detail}</span> <a href={note.href}>{note.action} →</a></li>{/each}
        </ul>
      {:else if notes}
        <p class="context">마지막 측정에서 따로 확인할 항목은 없습니다.</p>
      {/if}
    </dd></div>
    <div><dt>앞으로 어떻게 될까요?</dt><dd><p><a href={assetTabUrl(asset.assetId, "outlook")}>지금 추세가 이어질 때의 전망 보기 →</a></p></dd></div>
    <div><dt>전에 검토한 적이 있나요?</dt><dd>
      <details ontoggle={event=>archiveOpen=event.currentTarget.open}><summary>저장한 주요 변화 검토</summary>
        {#if archiveOpen}<ChangeReviewArchive assetId={asset.assetId} revision={reviewRevision} />{/if}
      </details>
    </dd></div>
    <div><dt>다른 방법으로도 볼 수 있나요?</dt><dd>
      <details ontoggle={(event) => showOptions=event.currentTarget.open}><summary>이 설비에서 할 수 있는 분석 보기</summary>
        {#if showOptions}<AnalysisOptions assetId={asset.assetId} level={3} />{/if}
      </details>
      <p><a href={assetTabUrl(asset.assetId, "signals")}>원본 신호 추이 보기 →</a>
        <a href={routeUrl({page: "investigations", assetId: asset.assetId, tab: "summary", method: null, data: null})}>저장된 분석 결과 보기 →</a></p>
    </dd></div>
  </dl>
</section>
</aside>
</div>

<details class="ui-panel provenance"><summary>측정 현황·데이터 출처·계산 범위</summary>
  <dl class="facts">
    <div><dt>마지막 측정</dt><dd>{lastMeasured}</dd></div>
    <div><dt>수신 상태</dt><dd>{flowLabel(asset.flow)}{#if asset.flow !== "stored-history" && asset.lastReceivedAt}
      <small>마지막 수신 {observed(asset.lastReceivedAt)}</small>{/if}</dd></div>
    <div><dt>확인할 항목</dt><dd>{attention(attentionCount)}</dd></div>
    <div><dt>저장된 데이터</dt><dd>{stored}</dd></div>
  </dl>
  {#if data?.history}
    {#if findings && findings.intervals.length}
      <p class="context small">변화 선정 방식 · 계산한 신호 {findings.judged}개에서 오래 이어진 구간·기록 끝의 변화·변화 폭을 보고 서로 다른 구간을 골랐습니다.
        대표값은 집계 구간 평균의 중앙값이며, 비교 기준은 각 신호 기록의 처음 30%입니다.
        {#if findings.operation.length}운전 상태를 아는 출처는 같은 운전 상태의 값끼리 견주고, 정지해 있던 동안의 값은 판단하지 않습니다.{/if}</p>
    {/if}
    {#if findingState === "ready" && findings?.operation.length}
      <details class="operation-details"><summary>운전 수준의 전체 분포·시간별 변화</summary>
        {#each findings.operation as operation (operation.key)}<OperationLevels {operation} />{/each}
      </details>
    {/if}
    {#if findingState === "ready" && findings}
      <details class="finding-coverage"><summary>분석한 기록과 계산 범위</summary>
      {#if findings.record}<p class="context small">검토한 기록 · {observed(findings.record.from)} ~ {observed(findings.record.to)}</p>{/if}
      <p class="coverage" aria-label="변화 분석 범위">출처·위치·측정 의미로 구분한 기록 {findings.signals.length + findings.unchecked}개 중
        계산 {findings.judged}개 · 누적 기록 {cumulative.length}개 · 데이터 확인 필요 {copiedCount}개 · 계산 불가 {findings.signals.length - findings.judged - cumulative.length - copiedCount}개 · 미검토 {findings.unchecked}개</p></details>
    {/if}
    {#if cumulative.length && findings?.judged}<details><summary>누적 기록</summary>{@render cumulativeRecords()}</details>{/if}
    {#if findings && findings.signals.some((row) => !["scored", "level-change", "constant", "cumulative", "copied"].includes(row.state))}
      <p class="context small">판단하지 못한 신호 · {findings.signals.filter((row) => !["scored", "level-change", "constant", "cumulative", "copied"].includes(row.state)).map(unjudgedText).join(" · ")}</p>
    {/if}
    {#if findings?.unchecked}<p class="context small">목록 순서에 따라 앞의 {findings.signals.length}개만 확인했습니다. 중요한 신호를 자동 선별한 결과는 아닙니다.
      나머지 {findings.unchecked}개는 <a href={assetTabUrl(asset.assetId, "anomaly", "baseline")}>기록 변화 찾기에서 신호를 골라 확인</a>할 수 있습니다.</p>{/if}
  {/if}
</details>

<style>
  /* PC 화면: 가운데에는 변화 하나와 그래프, 오른쪽 열에는 다른 변화와 이어서 확인할 것. */
  .summary-layout { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: var(--space-4); align-items: start; }
  .facts-panel { min-width: 0; display: grid; gap: var(--space-3); align-content: start; }
  .facts-panel > h2.eyebrow { margin: 0; font-size: var(--font-small); font-weight: 650; color: var(--color-ink-muted); }
  .rail { display: grid; gap: var(--space-4); min-width: 0; }
  .rail-section { padding: var(--space-4) var(--space-5); }
  .rail-section h2 { font-size: var(--font-body); margin: 0 0 var(--space-2); }
  @media (max-width: 1099px) { .summary-layout { grid-template-columns: minmax(0, 1fr); } }

  .found > li :global(.change-sentence) { margin: 0; font-size: 1.3rem; line-height: 1.45; font-weight: 700; overflow-wrap: anywhere; }
  .found > li :global(.card-top) { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--space-2) var(--space-6); }
  .found > li :global(.finding-actions) { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2) var(--space-4); }
  .found > li :global(.finding-actions details[open]) { flex-basis: 100%; }
  .change-why { margin: 0; font-size: var(--font-small); color: var(--color-ink-muted); }

  .other-changes { list-style: none; margin: 0 0 var(--space-2); padding: 0; display: grid; gap: var(--space-2); }
  .other-changes li { display: grid; gap: var(--space-1); padding: var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-control); }
  .other-changes li:hover { border-color: var(--color-action); }
  .other-changes button { display: grid; gap: 2px; padding: 0; border: 0; background: none; text-align: left; color: var(--color-ink); font: inherit; }
  .other-changes button span { font-size: var(--font-small); }
  .other-changes button small { font-size: var(--font-label); color: var(--color-ink-muted); }
  .other-changes a { font-size: var(--font-small); justify-self: start; }

  .quiet-record { display: grid; gap: var(--space-2); }
  .quiet-record h3 { margin: 0; font-size: var(--font-section); }
  .quiet-facts { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2) var(--space-5); }
  .quiet-facts p { margin: 0; }

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
  .rows { margin: 0; }
  .rows > div { display: grid; gap: var(--space-1); padding-block: var(--space-3); border-top: 1px solid var(--color-border); }
  .rows dt { font-weight: 650; font-size: var(--font-small); color: var(--color-ink); }
  .rows dd { margin: 0; font-weight: 400; display: grid; gap: var(--space-2); }
  .rows dd p { margin: 0; display: flex; flex-wrap: wrap; gap: var(--space-1) var(--space-4); }
  .rows dd summary { padding-block: 0; font-weight: 400; color: var(--color-action); }
  .provenance { margin-top: var(--space-4); }
  .provenance > summary { padding-block: 0; }
  .provenance[open] > summary { margin-bottom: var(--space-4); }
  .context { color: var(--color-ink-muted); overflow-wrap: anywhere; }
  .scores { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
  .scores li { display: grid; gap: 2px; padding-bottom: var(--space-2); }
  .scores li + li { border-top: 1px solid var(--color-border); padding-top: var(--space-2); }
  .scores li p { margin: 0; display: block; font-size: var(--font-small); }
  .scores .model-name { font-size: var(--font-body); }
  .scores .model-name .note { display: block; font-size: var(--font-label); }
  .scores .what { display: inline-block; min-width: 6.5em; color: var(--color-ink-muted); }
  .scores .caution-line { padding: var(--space-1) var(--space-2); border-left: 3px solid var(--color-caution-ink); background: var(--color-uncertain-surface); }
  .split { margin: 0; padding: var(--space-3); border-left: 3px solid var(--color-caution-ink); background: var(--color-uncertain-surface); overflow-wrap: anywhere; }
  .scores span { color: var(--color-ink-muted); font-size: var(--font-small); overflow-wrap: anywhere; }
  .others li { margin: 0 0 var(--space-2); overflow-wrap: anywhere; }
  .others span { color: var(--color-ink-muted); font-size: var(--font-small); }
  .others { list-style: none; margin: 0; padding: 0; }
  .small { font-size: var(--font-small); }
  .coverage { padding: var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-control); font-size: var(--font-small); overflow-wrap: anywhere; }
  .found { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-3); }
  .data-check { display: grid; gap: var(--space-1); padding: var(--space-3) var(--space-4); border-inline-start: 4px solid var(--color-uncertain-border); background: var(--color-uncertain-surface); border-radius: var(--radius-control); }
  .data-check h3 { margin: 0; font-size: var(--font-body); }
  .data-check p, .data-check ul { margin: 0; }
  .data-check ul { padding-inline-start: var(--space-4); overflow-wrap: anywhere; }
  .found li { display: grid; gap: var(--space-2); overflow-wrap: anywhere; }
  .finding-coverage{margin-bottom:var(--space-3)}
  .related { list-style: none; padding: 0; margin-block: var(--space-2); font-size: var(--font-small); }
  .related li { display: block; padding-block: var(--space-1); color: var(--color-ink-muted); }
  summary { cursor: pointer; font-weight: 650; padding-block: var(--space-2); }
</style>
