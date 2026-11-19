<script lang="ts">
  import {recordParams} from "../record-context";
  import {readOverview, type OverviewRow} from "../asset-overview";
  import OverviewTrace from "./OverviewTrace.svelte";
  import ChangeEvidence from "./ChangeEvidence.svelte";
  import DecisionPanel from "./DecisionPanel.svelte";
  import ChangeInterval from "./ChangeInterval.svelte";
  import OperationLevels from "./OperationLevels.svelte";
  import VibrationFindings from "./VibrationFindings.svelte";
  import RecordStrip from "./RecordStrip.svelte";
  import {readVibrationFindings, vibrationLinks, type VibrationFindings as VibrationRecord} from "../vibration-findings";
  import type {EvidenceFocus} from "../change-evidence";
  import SourceIdentity from "./SourceIdentity.svelte";
  import {onMount,untrack} from "svelte";
  import {flowLabel, type Asset} from "../monitor";
  import {isTimeWindow, loadLatestScores, modelName, type LatestScore} from "../model-evidence";
  import {readScoreTrend, type ScoreTrend} from "../model-trend";
  import {readModelOperation, unlearnedText} from "../model-operation";
  import {modelAtChange, modelEvidence, rareAtChange} from "../model-context";
  import type {ModelOperation} from "../model-operation";
  import {measurementLabel} from "../time-axis";
  import StatusNotice from "./StatusNotice.svelte";
  import type {AssetData} from "../asset-data";
  import {assetTabUrl, summarySelectionUrl} from "../routes";
  import AnalysisOptions from "./AnalysisOptions.svelte";
  import {attentionText, readAttention, type AttentionState, type Note} from "../monitor-attention";
  import {changeValue, focusChange, copiedGroups, findingLinks, findingSpan, findingText, readRecordFindings, bandName, unjudgedText, type CheckedSignal, type FoundInterval, type RecordFindings} from "../record-findings";
  import {CHANGE_WHY, afterChange, changeConclusion, latestNumber, plainLabel, type ChangeNumber, changeEnded} from "../change-story";
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
  let scoresState:"loading"|"ready"|"failed"=$state("loading");
  let histories: Record<string, "loading" | "failed" | {trend: ScoreTrend; operation: ModelOperation | null; unlearned: string | null}> = $state({});
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
      if (!request.signal.aborted) {notes = read.notes[asset.assetId] ?? []; notesState = read.state;}
    } catch {if (!request.signal.aborted) {notes = null; notesState = "failed";}}
  }
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
  // One selected phenomenon owns the chart and the next investigation.
  type Pick = {kind: "history" | "vibration"; index: number};
  const initialSelection=new URLSearchParams(location.search);
  const seedContext=!["monitor_channel","vibration_feature","vibration_at","acquisition_feature","acq_forecast_feature"].some(key=>initialSelection.has(key));
  let pickedKey = $state(initialSelection.get("summary_change"));
  const historyKey=(item:FoundInterval)=>JSON.stringify(["history",item.context?.key??item.channel,item.start,item.end]);
  const vibrationKey=(change:VibrationRecord["intervals"][number])=>JSON.stringify(["vibration",change.feature,change.from,change.to]);
  const focus = $derived.by((): Pick | null => {
    const history: RecordFindings | null = findings, measured: VibrationRecord | null = vibration;
    const h=history?.intervals.findIndex(item=>historyKey(item)===pickedKey)??-1;
    if(h>=0)return {kind:"history",index:h};
    const v=measured?.intervals.findIndex(change=>vibrationKey(change)===pickedKey)??-1;
    if(v>=0)return {kind:"vibration",index:v};
    if (history?.intervals.length) return {kind: "history", index: 0};
    if (measured?.intervals.length) return {kind: "vibration", index: 0};
    return null;
  });
  function selectChange(pick:Pick) {
    const records:RecordFindings|null=findings, measured:VibrationRecord|null=vibration;
    let target:URL, key:string;
    if(pick.kind==="history"&&records?.intervals[pick.index]) {
      const item=records.intervals[pick.index];
      const links=findingLinks(asset.assetId,item,records.baseline,records.bucketSeconds,records.record);
      target=new URL(links.compare??links.signal??links.outlook,location.origin);
      if(links.signal) {
        const signal=new URL(links.signal,location.origin);
        for(const name of ["monitor_range","monitor_from","monitor_to","monitor_pick"])
          if(signal.searchParams.has(name))target.searchParams.set(name,signal.searchParams.get(name)!);
      }
      target.searchParams.set("relation_x",item.channel);
      const other=item.related.find(row=>row.state!=="within")??item.related[0];
      if(other)target.searchParams.set("relation_y",other.channel);
      key=historyKey(item);
    } else if(pick.kind==="vibration"&&measured?.intervals[pick.index]) {
      const change=measured.intervals[pick.index];
      target=new URL(vibrationLinks(asset.assetId,change).compare,location.origin);
      target.searchParams.set("vibration_feature",change.feature);
      target.searchParams.set("vibration_at",String(change.from));
      if(measured.bindingId)target.searchParams.set("acquisition_binding",measured.bindingId);
      target.searchParams.set("acq_relation_x",change.feature);
      if(change.related[0])target.searchParams.set("acq_relation_y",change.related[0].feature);
      for(const part of ["a_from","a_to","b_from","b_to"])
        target.searchParams.set("acq_"+part,target.searchParams.get("feature_"+part)!);
      key=vibrationKey(change);
    } else return;
    history.replaceState(history.state,"",summarySelectionUrl(location.href,target.href,key,pick.kind));
    pickedKey=key;
  }
  const vibrationPlace = (at: number) => measurementLabel(at, vibration?.periodSeconds);
  // 이 데이터로 할 수 있는 분석: 판단할 변화가 없을 때의 다음 질문이라 그때는 본문에, 변화가 있으면 데이터 묶음 안에 둔다.
  let showOptions = $state(false);
  const settled = $derived.by(() => {
    const history: string = findingState, measured: string = vibrationState;
    // 설비의 데이터 종류를 아직 모르면 '변화 없음'으로 읽지 않는다.
    return dataState !== "loading" && (!data?.history || history === "ready" || history === "failed")
      && (!data?.vibration || measured === "ready" || measured === "failed");
  });
  $effect(()=>{
    const current=focus;
    const ready=(!data?.history||findingState==="ready"||findingState==="failed")
      &&(!data?.vibration||vibrationState==="ready"||vibrationState==="failed");
    if(current&&pickedKey===null&&ready&&seedContext)untrack(()=>selectChange(current));
  });
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
    const rows: {key: string; pick: Pick; label: string; line: string; when: string}[] = [];
    history?.intervals.forEach((item, index) => {
      if (shown?.kind === "history" && shown.index === index) return;
      rows.push({key: "h" + index, pick: {kind: "history", index}, label: item.label,
        line: "처음 30%보다 " + (item.direction === "up" ? "높음" : "낮음") + (item.reference != null && item.typical != null ? " · " + changeValue(item.reference, null) + " → " + changeValue(item.typical, item.unit) : ""),
        when: findingText(item, item.bucketSeconds ?? history.bucketSeconds).when});
    });
    measured?.intervals.forEach((change, index) => {
      if (shown?.kind === "vibration" && shown.index === index) return;
      rows.push({key: "v" + index, pick: {kind: "vibration", index}, label: plainLabel(change.label, change.feature),
        line: "처음 30%보다 " + (change.direction === "up" ? "높음" : "낮음") + (change.reference != null && change.typical != null ? " · " + changeValue(change.reference, null) + " → " + changeValue(change.typical, change.unit) : ""),
        when: vibrationPlace(change.from) + " ~ " + vibrationPlace(change.to) + " · " + (change.to - change.from + 1) + "회"});
    });
    return rows;
  });
  const changeChoices = $derived.by(() => {
    const history: RecordFindings | null = findings, measured: VibrationRecord | null = vibration;
    return [
      ...(history?.intervals.map((item,index) => ({key:historyKey(item),pick:{kind:"history" as const,index},label:plainLabel(item.label,item.channel)})) ?? []),
      ...(measured?.intervals.map((item,index) => ({key:vibrationKey(item),pick:{kind:"vibration" as const,index},label:plainLabel(item.label,item.feature)})) ?? []),
    ];
  });
  const selectedChange = $derived(focus ? changeChoices.find(row => row.pick.kind === focus.kind && row.pick.index === focus.index)?.key : "");
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
      scores = value;
      scoresState="ready";
      // 최근 결과 하나만으로는 모델이 기록 전체와 이 변화 구간을 어떻게 봤는지 알 수 없어, 점수 기록도 읽는다.
      for (const item of value) {
        const id = item.binding.bindingId;
        histories = {...histories, [id]: "loading"};
        void Promise.all([readScoreTrend(item.binding, request.signal),
          isTimeWindow(item.binding.stepKind) ? readModelOperation(id, request.signal)
            .catch(() => new Promise(done => setTimeout(done, 2000)).then(() => readModelOperation(id, request.signal))).catch(() => null)
            : Promise.resolve(null)])
          .then(([trend, operation]) => { if (!request.signal.aborted) histories = {...histories, [id]: {trend, operation, unlearned: operation ? unlearnedText(operation) : null}}; })
          .catch(() => { if (!request.signal.aborted) histories = {...histories, [id]: "failed"}; });
      }
    }).catch(() => { if(!request.signal.aborted)scoresState="failed"; });
    void readNotes();
    return () => {request.abort();noteRequest?.abort();};
  });
  // 근거를 찾을 변화: 가운데에 보이는 바로 그 변화.
  const evidenceFocus = $derived.by((): EvidenceFocus | null => {
    const shown = focus, history: RecordFindings | null = findings, measured: VibrationRecord | null = vibration;
    if (shown?.kind === "history" && history?.intervals[shown.index]) {
      const item = history.intervals[shown.index];
      const own = item.operation ? history.operation.find(entry => entry.key === item.operation?.key) : undefined;
      return {kind: "history", item, record: history, condition: own && item.band != null ? bandName(own, item.band) : null};
    }
    if (shown?.kind === "vibration" && measured?.intervals[shown.index])
      return {kind: "vibration", change: measured.intervals[shown.index], record: measured};
    return null;
  });
  const modelState=$derived.by(():"loading"|"ready"|"failed"=>{
    const reading=scores.filter(item=>readsFocus(item.binding));
    if(scoresState==="loading"||reading.some(item=>histories[item.binding.bindingId]===undefined||histories[item.binding.bindingId]==="loading"))return "loading";
    if(scoresState==="failed"||(reading.length>0&&reading.every(item=>histories[item.binding.bindingId]==="failed")))return "failed";
    return "ready";
  });
  // 모델 근거 한 줄: 이 변화 구간을 분석한 모델만 센다. 점수 기록을 다 읽기 전에는 말하지 않는다.
  const modelLine = $derived.by((): string | null => {
    const span = focusSpan;
    if (!span) return null;
    const reading = scores.filter(item => readsFocus(item.binding));
    if (!reading.length || reading.some(item => histories[item.binding.bindingId] === "loading" || histories[item.binding.bindingId] === undefined)) return null;
    let unlearned: {condition: string; share: number} | null = null;
    const rows = reading.flatMap(item => {
      const read = histories[item.binding.bindingId];
      if (typeof read !== "object") return [];
      const at = modelAtChange(read.trend, span, span.axis);
      const rare = span.condition && read.operation ? rareAtChange(read.operation, span.condition) : null;
      if (rare !== null && at.exceeded && !unlearned) unlearned = {condition: span.condition!, share: rare};
      return [{name: modelName(item.binding), ...at, complete:!read.trend.truncated}];
    });
    const line=modelEvidence(rows, unlearned);
    return line && reading.some(item=>histories[item.binding.bindingId]==="failed") ? line+" · 일부 모델 결과 조회 실패" : line;
  });
  const modelDestination = $derived.by(():string|null => {
    const span=focusSpan;
    if(!span)return null;
    const candidates=scores.filter(item=>readsFocus(item.binding)).flatMap(item=>{
      const read=histories[item.binding.bindingId];
      if(typeof read!=="object")return [];
      return read.trend.points.filter(point=>{
        const at=span.axis==="time"?point.pointer.position/1000:point.pointer.position;
        return point.pointer.state==="analyzed" && point.score!==null && span.from<=at && at<=span.to;
      }).map(point=>({binding:item.binding.bindingId,position:point.pointer.position}));
    }).sort((a,b)=>a.position-b.position || a.binding.localeCompare(b.binding));
    const first=candidates[0];
    if(!first)return null;
    const url=new URL(assetTabUrl(asset.assetId,"anomaly","model"),location.origin);
    url.searchParams.set("model_binding",first.binding);url.searchParams.set("model_position",String(first.position));
    return url.pathname+url.search;
  });
  // 판단하는 곳: 가운데 변화를 저장할 수 있을 때만 연다.
  const decision = $derived.by((): {reviewKey: string; ai: {change: VibrationRecord["intervals"][number];bindingId:string} | null} | null => {
    const shown = evidenceFocus;
    if (shown?.kind === "history") return shown.item.reviewKey ? {reviewKey: shown.item.reviewKey, ai: null} : null;
    if (shown?.kind === "vibration") return shown.change.reviewKey
      ? {reviewKey: shown.change.reviewKey, ai: shown.record.bindingId ? {change: shown.change,bindingId:shown.record.bindingId} : null} : null;
    return null;
  });
  const focusReason = $derived.by(() => {
    const shown = evidenceFocus;
    const reason = shown?.kind === "history" ? shown.item.reason : shown?.kind === "vibration" ? shown.change.reason : null;
    return reason ? CHANGE_WHY[reason] : null;
  });
  const endedText = (history: RecordFindings, item: FoundInterval): string | null =>
    changeEnded(item.end, item.context?.record.to ?? history.record?.to, item.bucketSeconds ?? history.bucketSeconds);
  /** 기록 끝까지 이어진 변화의 세 번째 숫자: 같은 기록의 마지막 구간 평균. */
  function historyLatest(history: RecordFindings, item: FoundInterval): ChangeNumber | null {
    const own = history.signals.find(row => item.context ? row.context?.key === item.context.key : row.channel === item.channel);
    return own?.latest ? latestNumber("마지막 구간 평균", own.latest.value, item.typical, item.unit) : null;
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
  {@const ended = endedText(history, item)}
  {@const last = ended ? undefined : history.signals.find(row => item.context ? row.context?.key === item.context.key : row.channel === item.channel)?.latest}
  <div class="change-lead"><div class="lead-copy">
  <h3 class="change-sentence">{changeConclusion(item, ended ? {span: findingSpan(item)} : {latest: last ? {caption: "마지막 구간 평균", value: last.value} : null})}</h3>
  {#if !ended || condition}<p class="context">{[ended ? null : findingSpan(item), condition ? condition + " 중의 값끼리 비교" : null].filter(Boolean).join(" · ")}</p>{/if}
  {#if ended}<p class="context">{afterChange(item.end, item.usual, item.overview ?? [], item.overviewKind ?? "all", condition) ?? ended}</p>{/if}</div>
  <ChangeNumbers facts={item} latest={ended ? null : historyLatest(history, item)} fallback={told.what} />
  </div>
  <ChangeInterval finding={item} height={240} focus/>
  <RecordStrip finding={focusChange(item)} {condition} />
  {#if links.signal}<p class="chart-link"><a href={links.signal}>원본 신호에서 이 구간 보기 →</a></p>{/if}
{/snippet}

{#snippet analysisOptions()}
  <details class="options" ontoggle={event => showOptions = event.currentTarget.open}><summary>적용 가능한 분석</summary>
    {#if showOptions}<AnalysisOptions assetId={asset.assetId} level={3} />{/if}
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
  <div class="summary-heading">
    <h2 id="summary-title" class="eyebrow">기록에서 찾은 주요 변화</h2>
    {#if changeChoices.length > 1}<label class="change-picker">살펴볼 변화
      <select aria-label="살펴볼 변화" value={selectedChange} onchange={event => {const choice=changeChoices.find(row=>row.key===event.currentTarget.value);if(choice)selectChange(choice.pick);}}>
        {#each changeChoices as row (row.key)}<option value={row.key}>{row.label}</option>{/each}
      </select>
    </label>{/if}
  </div>
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
      <p class="context">{findings.operation.length?"같은 운전 수준의 측정끼리 비교해":"기록 초반과 비교해"} 뚜렷하게 다른 구간이 없습니다. 아래는 기록 전체의 추세와 값의 범위입니다.</p>
      {#if quietMain}<h3>{quietMain.label}</h3><OverviewTrace main={quietMain} height={260}/>{#if findings.operation.length}<p class="context small">추세에는 서로 다른 운전 상태의 기록도 함께 표시합니다.</p>{/if}{/if}
      <div class="quiet-facts">
        {#if quietSignal}{#if quietSignal.context}<SourceIdentity id={quietSignal.context.sourceId} pointId={quietSignal.context.pointId} interpretationId={quietSignal.context.interpretationId}/>{/if}
          {#if quietSignal.latest}<p>마지막 구간 평균 <strong>{changeValue(quietSignal.latest.value,quietSignal.unit)}</strong> · {observed(quietSignal.latest.at)}</p>{/if}
          {#if quietSignal.range}<p>구간별 평균의 범위 {changeValue(quietSignal.range.low,null)} ~ {changeValue(quietSignal.range.high,quietSignal.unit)}</p>{/if}
        {/if}
        <a class="ui-button ui-button-primary" href={signalHref(quietSignal)}>원본 신호 추세 보기 →</a>
      </div>
    </section>
  {:else if data?.history && cumulative.length}
    {@render cumulativeRecords()}
  {:else if data?.history && findings && !data?.vibration}
    <p class="context">기록 처음 30%와 비교해 판단할 수 있는 신호가 없어 변화 여부를 판단하지 않았습니다.
      <a href={assetTabUrl(asset.assetId, "signals")}>신호를 직접 보기 →</a></p>
  {:else if data?.vibration && vibrationState === "loading"}
    <p class="context">진동 측정 전체를 처음 30%와 비교하고 있습니다.</p>
  {:else if data?.vibration && vibrationState === "failed"}
    <p class="context">진동 측정에서 찾은 변화를 불러오지 못했습니다. <a href={assetTabUrl(asset.assetId, "signals", null, "vibration")}>진동 특징 추이 보기 →</a></p>
  {:else if data?.vibration && vibration?.judged}
    <p class="context">진동 특징 {vibration.judged}개 모두 처음 30% 대비 크게 달라진 구간이 없습니다. <a href={assetTabUrl(asset.assetId, "signals", null, "vibration")}>진동 특징 추이 보기 →</a></p>
  {/if}

  {#if !evidenceFocus && settled}{@render analysisOptions()}{/if}

  {#if evidenceFocus}
    <section class="block" aria-labelledby="evidence-title">
      <h3 id="evidence-title">변화 근거</h3>
      {#key pickedKey ?? focus?.kind + String(focus?.index)}<ChangeEvidence assetId={asset.assetId} focus={evidenceFocus} model={modelLine} {modelState} {modelDestination} />{/key}
      {#if copiedCount}<p class="context small">변화 판단 제외 · 다른 항목의 값이 그대로 기록된 신호 {copiedCount}개 (‘측정 현황·데이터 출처·계산 범위’에서 확인)</p>{/if}
    </section>
  {/if}

  {#if decision}<div class="summary-actions">{#key decision.reviewKey}<DecisionPanel assetId={asset.assetId} reviewKey={decision.reviewKey} ai={decision.ai} />{/key}</div>{/if}
</section>
</div>

<details class="ui-panel provenance"><summary>측정 현황·데이터 출처·계산 범위</summary>
  {#if focusReason}<p class="context small">{focusReason}</p>{/if}
  {#if otherChanges.length}<ul class="other-changes" aria-label="기록의 다른 변화">
    {#each otherChanges as row (row.key)}<li><button type="button" onclick={() => selectChange(row.pick)} aria-label={row.label + " 변화 크게 보기"}>
      <strong>{row.label}</strong><span>{row.line}</span><small>{row.when}</small></button></li>{/each}
  </ul>{/if}
  <dl class="facts">
    <div><dt>마지막 측정</dt><dd>{lastMeasured}</dd></div>
    <div><dt>수신 상태</dt><dd>{flowLabel(asset.flow)}{#if asset.flow !== "stored-history" && asset.lastReceivedAt}
      <small>마지막 수신 {observed(asset.lastReceivedAt)}</small>{/if}</dd></div>
    <div><dt>확인할 항목</dt><dd>{attention(attentionCount)}</dd></div>
    <div><dt>저장된 데이터</dt><dd>{stored}</dd></div>
  </dl>
  {#if notesState === "partial" || notesState === "failed"}
    <StatusNotice kind="uncertain" message="확인 항목을 일부 읽지 못했습니다. 표시된 건수는 확인된 항목만 포함합니다."
      actionLabel="확인 항목 다시 읽기" onAction={() => void readNotes()} />
  {/if}
  {#if evidenceFocus}{@render analysisOptions()}{/if}
  {#if focus?.kind === "history" && findings?.intervals[focus.index]?.context}
    {@const shown = findings.intervals[focus.index]}
    <SourceIdentity id={shown.context!.sourceId} pointId={shown.context!.pointId} interpretationId={shown.context!.interpretationId} among={findings.signals.flatMap(row=>row.context?[row.context.sourceId]:[])}/>
  {/if}
  {#if data?.history}
    {#if findings && findings.intervals.length}
      <p class="context small">변화 선정 방식 · 계산한 신호 {findings.judged}개에서 오래 이어진 구간·기록 끝의 변화·변화 폭을 보고 서로 다른 구간을 골랐습니다.
        대표값은 집계 구간 평균의 중앙값이며, 비교 기준은 각 신호 기록의 처음 30%입니다.
        {#if findings.operation.length}운전 상태를 아는 출처는 같은 운전 상태의 값끼리 비교하고, 정지해 있던 동안의 값은 판단하지 않습니다.{/if}</p>
    {/if}
    {#if findingState === "ready" && copies.length}
      <section class="data-check" aria-labelledby="data-check-title">
        <h3 id="data-check-title">변화 판단에서 뺀 신호 {copiedCount}개</h3>
        <p>아래 신호는 일부 기간에 다른 항목의 값이 그대로 기록되어 있습니다.</p>
        <ul>{#each copies as group (group.from + group.to)}
          <li><strong>{observed(group.from)} ~ {observed(group.to)}</strong> · {group.items.map(item => item.label + "에 " + item.origin + " 값").join(", ")}</li>
        {/each}</ul>
      </section>
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
  .summary-layout { min-width: 0; }
  .summary-heading { display: flex; justify-content: space-between; align-items: center; gap: var(--space-3); flex-wrap: wrap; }
  .summary-heading h2 { margin: 0; font-size: var(--font-small); color: var(--color-ink-muted); }
  .change-picker { display: flex; gap: var(--space-2); align-items: center; font-size: var(--font-small); color: var(--color-ink-muted); }
  .change-picker select { max-width: min(420px, 70vw); padding: var(--space-2); border: 1px solid var(--color-control-border); border-radius: var(--radius-control); font: inherit; color: var(--color-ink); background: var(--color-surface); }
  .summary-actions { display: flex; justify-content: end; border-top: 1px solid var(--color-border); padding-top: var(--space-3); }
  .facts-panel { min-width: 0; display: grid; gap: var(--space-3); align-content: start; }

  .found { list-style: none; margin: 0; padding: 0; }
  .found > li { display: grid; gap: var(--space-2); overflow-wrap: anywhere; }
  .found > li :global(.change-sentence) { margin: 0; font-size: 1.3rem; line-height: 1.45; font-weight: 700; overflow-wrap: anywhere; word-break: keep-all; }
  .chart-link { margin: 0; font-size: var(--font-small); }

  .block { display: grid; gap: var(--space-1); margin-top: var(--space-3); }
  .block > h3 { margin: 0 0 var(--space-1); font-size: var(--font-body); }
  .other-changes { list-style: none; margin: var(--space-1) 0 0; padding: 0; display: grid; gap: var(--space-2);
    grid-template-columns: repeat(auto-fill, minmax(min(100%, 260px), 1fr)); }
  .other-changes button { width: 100%; height: 100%; display: grid; gap: 2px; align-content: start; padding: var(--space-3);
    border: 1px solid var(--color-border); border-radius: var(--radius-control); background: var(--color-surface);
    text-align: left; color: var(--color-ink); font: inherit; cursor: pointer; }
  .other-changes button:hover { border-color: var(--color-action); }
  .other-changes span { font-size: var(--font-small); }
  .other-changes small { font-size: var(--font-label); color: var(--color-ink-muted); }

  .quiet-record { display: grid; gap: var(--space-2); }
  .quiet-record h3 { margin: 0; font-size: var(--font-section); }
  .quiet-facts { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2) var(--space-5); }
  .quiet-facts p { margin: 0; }

  .provenance { margin-top: var(--space-4); display: grid; gap: var(--space-3); }
  .provenance > summary { padding-block: 0; }
  .facts { margin: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: var(--space-4); }
  .facts div { padding-bottom: var(--space-3); border-bottom: 1px solid var(--color-border); min-width: 0; }
  dt { font-size: var(--font-small); color: var(--color-ink-muted); }
  dd { margin: var(--space-2) 0 0; font-weight: 700; overflow-wrap: anywhere; }
  dd small { display: block; margin-top: var(--space-1); font-weight: 400; font-size: var(--font-small); color: var(--color-ink-muted); }
  .data-check { display: grid; gap: var(--space-1); font-size: var(--font-small); }
  .data-check h3 { margin: 0; font-size: var(--font-body); }
  .data-check p, .data-check ul { margin: 0; }
  .data-check ul { padding-inline-start: var(--space-4); overflow-wrap: anywhere; }
  .coverage { padding: var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-control); font-size: var(--font-small); overflow-wrap: anywhere; }
  .context { margin: 0; color: var(--color-ink-muted); overflow-wrap: anywhere; }
  .small { font-size: var(--font-small); }
  summary { cursor: pointer; font-weight: 650; padding-block: var(--space-2); }
  .options > summary { color: var(--color-action); }
</style>
