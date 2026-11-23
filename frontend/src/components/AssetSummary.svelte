<script lang="ts">
  import {type PlaybackScope, scopeParams} from "../record-playback";
  import {recordParams} from "../record-context";
  import {readOverview, type OverviewRow} from "../asset-overview";
  import OverviewTrace from "./OverviewTrace.svelte";
  import ChangeContext from "./ChangeContext.svelte";
  import ChangeActions from "./ChangeActions.svelte";
  import DecisionPanel from "./DecisionPanel.svelte";
  import ChangeInvestigation from "./ChangeInvestigation.svelte";
  import OperationLevels from "./OperationLevels.svelte";
  import AssetTimeline from "./AssetTimeline.svelte";
  import {clockText, episodes, operationColumns, type Span, type TimelineLane, type TimelineOperation, type TimelinePoint} from "../asset-timeline";
  import {readAcquisitionTrend} from "../acquisition-trend";
  import {readTrends, trendRange} from "../history";
  import {readChangeReviews} from "../change-reviews";
  import {DECISION_LABEL} from "../review-writes";
  import {readVibrationFindings, vibrationLinks, type VibrationFindings as VibrationRecord} from "../vibration-findings";
  import type {EvidenceFocus} from "../change-evidence";
  import type {Evidence} from "../change-investigation";
  import SourceIdentity from "./SourceIdentity.svelte";
  import {onMount,untrack} from "svelte";
  import {flowLabel, type Asset} from "../monitor";
  import {measurementLabel} from "../time-axis";
  import StatusNotice from "./StatusNotice.svelte";
  import type {AssetData} from "../asset-data";
  import {assetTabUrl, summarySelectionUrl} from "../routes";
  import AnalysisOptions from "./AnalysisOptions.svelte";
  import {attentionText, readAttention, type AttentionState, type Note} from "../monitor-attention";
  import {changeValue, copiedGroups, findingLinks, findingText, readRecordFindings, bandName, unjudgedText, type CheckedSignal, type FoundInterval, type RecordFindings} from "../record-findings";
  import {CHANGE_WHY, plainLabel, versusStart, changeEnded} from "../change-story";
  import {measure} from "../chart-axis";
  type Props = {
    asset: Asset;
    data: AssetData | null;
    dataState: "loading" | "ready" | "failed";
    observed: (at: string | null) => string;
    selectedAt?: number | null;
    revision?:number;scope?:PlaybackScope|null;onBusy?:(busy:boolean)=>void;onInvestigate?:()=>void;
  };
  let {asset, data, dataState, observed, selectedAt = $bindable(null),scope=null,revision=0,onBusy,onInvestigate}: Props = $props();
  const assetId=$derived(asset.assetId);
  const readRevision=$derived(assetId+":"+JSON.stringify(scope)+":"+revision);
  const stored = $derived.by(() => {
    if (dataState === "loading") return "확인하는 중";
    if (dataState === "failed" || !data) return "확인하지 못함";
    const parts: string[] = [];
    if (data.history) parts.push("시계열 신호 " + data.history.signals + "개");
    if (data.vibration) parts.push("진동 측정 " + data.vibration.measurements + "회 ("
      + data.vibration.first + "~" + data.vibration.last + "번째)");
    return parts.length ? parts.join(" · ") : "분석할 저장 데이터 없음";
  });
  // The same items 관측 현황 lists for this asset; null while unread or unreadable.
  let notes: Note[] | null = $state(null);
  let notesState: AttentionState = $state("loading");
  let noteRequest: AbortController | null = null;
  async function readNotes() {
    noteRequest?.abort();
    const request = new AbortController(); noteRequest = request;
    notes = null; notesState = "loading";
    try {
      const read = await readAttention(request.signal,assetId);
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
  const busy=$derived.by(()=>{
    const history:string=findingState, vibration:string=vibrationState;
    return history==="loading"||vibration==="loading";
  });
  $effect(()=>onBusy?.(busy));

  $effect(() => {
    if (!data?.vibration) return;
    readRevision;
    const request = new AbortController();
    untrack(()=>{if(scope&&vibration?.last!=null&&vibration.last>scope.until){vibration=null;quietMain=null;}});
    vibrationState = "loading";
    void readVibrationFindings(assetId, request.signal, scope).then((value) => {
      if (!request.signal.aborted) {
        vibration = value; vibrationState = "ready";
        if(!value.intervals.length) {
          void readAcquisitionTrend(assetId,"feature.Vertical_vibration_signals.rms",request.signal).then(trend=>{
            if(request.signal.aborted)return;
            quietMain={label:trend.label,unit:trend.unit,axis:"acquisition",periodSeconds:trend.periodSeconds,
              latest:trend.points.length?{at:null,position:trend.points.at(-1)!.ordinal,value:trend.points.at(-1)!.value}:null,
              trace:trend.points.map((p,i)=>({x:p.ordinal,value:p.value,join:i>0&&p.ordinal===trend.points[i-1].ordinal+1}))};
          }).catch(()=>{});
        }
      }
    }).catch(() => {if (!request.signal.aborted) vibrationState = "failed";});
    return () => request.abort();
  });
  // One selected phenomenon owns the chart and the next investigation.
  type Pick = {kind: "history" | "vibration"; index: number};
  const initialSelection=new URLSearchParams(location.search);
  const seedContext=!["monitor_channel","vibration_feature","vibration_at","acquisition_feature","acq_forecast_feature"].some(key=>initialSelection.has(key));
  let pickedKey = $state(initialSelection.get("summary_change"));
  let seeded=$state(false);
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
  function selectChange(pick:Pick,manual=true) {
    if(manual)onInvestigate?.();
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
      target.searchParams.set("acq_forecast_feature",change.feature);
      target.searchParams.set("spectrum_channel",change.feature.slice(8,change.feature.lastIndexOf(".")));
      target.searchParams.set("vibration_at",String(change.from));
      if(measured.bindingId)target.searchParams.set("acquisition_binding",measured.bindingId);
      if(measured.sourceId)target.searchParams.set("acquisition_source",measured.sourceId);
      target.searchParams.set("acq_relation_x",change.feature);
      if(change.related[0])target.searchParams.set("acq_relation_y",change.related[0].feature);
      for(const part of ["a_from","a_to","b_from","b_to"])
        target.searchParams.set("acq_"+part,target.searchParams.get("feature_"+part)!);
      key=vibrationKey(change);
    } else return;
    for(const [name,value] of Object.entries(scopeParams(scope)))target.searchParams.set(name,value);
    target.searchParams.set("summary_label",pick.kind==="history"?records!.intervals[pick.index].label:plainLabel(measured!.intervals[pick.index].label,measured!.intervals[pick.index].feature));
    history.replaceState(history.state,"",summarySelectionUrl(location.href,target.href,key,pick.kind));
    pickedKey=key;
    selectedAt=null;
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
    if(current&&ready&&seedContext&&!seeded)untrack(()=>{seeded=true;selectChange(current,false);});
  });
  // 설비 시간축: 고른 변화와 시간이 겹치는 변화를 한 시기로 묶어 같은 가로축에 쌓는다.
  type Item = {key: string; pick: Pick; span: Span};
  const items = $derived.by((): Item[] => {
    const history: RecordFindings | null = findings, measured: VibrationRecord | null = vibration;
    return [
      ...(history?.intervals.map((item, index) => ({key: historyKey(item), pick: {kind: "history" as const, index},
        span: {from: Date.parse(item.start), to: Date.parse(item.end)}})) ?? []),
      ...(measured?.intervals.map((change, index) => ({key: vibrationKey(change), pick: {kind: "vibration" as const, index},
        span: {from: change.from, to: change.to}})) ?? []),
    ];
  });
  const grouped = $derived(focus ? episodes(items.filter(item => item.pick.kind === focus!.kind), item => item.span) : []);
  const current = $derived(grouped.find(group => group.members.some(member => member.pick.index === focus?.index)) ?? null);
  // 진동 특징은 기록 전체 값을 따로 읽는다(변화 응답에는 일부만 실린다).
  let traces: Record<string, TimelinePoint[]> = $state({});
  $effect(()=>{readRevision;untrack(()=>traces={});});
  $effect(() => {
    readRevision;
    const measured: VibrationRecord | null = vibration, group = current;
    if (!measured || !group || focus?.kind !== "vibration") return;
    const request = new AbortController();
    for (const member of group.members) {
      const change = measured.intervals[member.pick.index];
      if (!change || untrack(() => traces[change.feature])) continue;
      void readAcquisitionTrend(assetId, change.feature, request.signal).then(read => {
        if (request.signal.aborted || read.sampled || read.sourceId !== measured.sourceId || read.bindingId !== measured.bindingId) return;
        traces = {...traces, [change.feature]: read.points.map((point, i) => ({x: point.ordinal, value: point.value,
          join: i > 0 && point.ordinal === read.points[i - 1].ordinal + 1}))};
      }).catch(() => {});
    }
    return () => request.abort();
  });
  const magnitude = (reference: number | null, typical: number | null, unit: string | null) =>
    reference != null && typical != null ? changeValue(reference, null) + " → " + changeValue(typical, unit) + " · " + versusStart(typical, reference, unit) : "";
  function historyLane(history: RecordFindings, item: FoundInterval, focused: boolean): TimelineLane {
    const own = item.operation ? history.operation.find(entry => entry.key === item.operation?.key) : undefined;
    const kind = item.overviewKind ?? "all";
    // 판단한 값(같은 운전 수준의 값)만 잇는다. 빠진 칸 다음 값은 앞과 잇지 않는다.
    const points: TimelinePoint[] = [];
    let skipped = false;
    for (const row of item.overview ?? []) {
      const value = row.mean;
      if (value === null) { skipped = true; continue; }
      points.push({x: Date.parse(row.at), value, join: row.join && !skipped});
      skipped = false;
    }
    const ongoing = endedText(history, item) === null;
    const own_ = history.signals.find(row => item.context ? row.context?.key === item.context.key : row.channel === item.channel);
    const latest = ongoing && own_?.latest ? " · 마지막 " + changeValue(own_.latest.value, item.unit) : "";
    return {key: historyKey(item), reviewKey: item.reviewKey, label: plainLabel(item.label, item.channel), unit: item.unit,
      condition: own && item.band != null ? bandName(own, item.band) : null,
      points, detail: [],
      matched:kind!=="all"?(item.overview??[]).flatMap(row=>row.judged!==null?[{x:Date.parse(row.at),value:row.judged,join:row.join}]:[]):[],
      usual: item.usual, interval: {from: Date.parse(item.start), to: Date.parse(item.end)},
      values:{before:item.reference,after:item.typical,latest:own_?.latest?{value:own_.latest.value,at:Date.parse(own_.latest.at)}:null},
      numbers: magnitude(item.reference, item.typical, item.unit) + latest, focus: focused, up: item.direction === "up"};
  }
  function vibrationLane(measured: VibrationRecord, change: VibrationRecord["intervals"][number], focused: boolean): TimelineLane {
    const points = traces[change.feature] ?? change.trace.map(point => ({x: point.at, value: point.value, join: point.join}));
    const last = change.to === measured.last ? points.at(-1) : undefined;
    const latest = last && last.x === measured.last ? " · 마지막 " + measure(last.value, change.unit) + "(" + versusStart(last.value, change.reference, change.unit) + ")" : "";
    return {key: vibrationKey(change), reviewKey: change.reviewKey, label: plainLabel(change.label, change.feature), unit: change.unit, condition: null,
      points, detail: [], usual: change.usual, interval: {from: change.from, to: change.to},
      values:{before:change.reference,after:change.typical,latest:last&&last.x===measured.last?{value:last.value,at:last.x}:null},
      numbers: magnitude(change.reference, change.typical, change.unit) + latest, focus: focused, up: change.direction === "up"};
  }
  // 시간축 줄마다 마지막으로 남긴 판단: 다음에 와도 무엇을 결정했는지 그 변화 옆에 보인다.
  let decisions: Record<string, string> = $state({});
  let reviewRevision = $state(0);
  $effect(() => {
    reviewRevision;
    const group = current, history: RecordFindings | null = findings, measured: VibrationRecord | null = vibration;
    if (!group) return;
    const request = new AbortController();
    for (const member of group.members) {
      const key = member.pick.kind === "history" ? history?.intervals[member.pick.index]?.reviewKey : measured?.intervals[member.pick.index]?.reviewKey;
      if (!key) continue;
      void readChangeReviews(assetId, request.signal, {finding_id: key}).then(page => {
        const decided = page.captures[0]?.review.events.filter(event => event.decision).at(-1);
        if (request.signal.aborted || !decided?.decision) return;
        const day = new Date(decided.recordedAt).toLocaleDateString("ko-KR", {timeZone: "Asia/Seoul", month: "long", day: "numeric"});
        decisions = {...decisions, [member.key]: DECISION_LABEL[decided.decision] + " · " + day};
      }).catch(() => {});
    }
    return () => request.abort();
  });
  const lanes = $derived.by((): TimelineLane[] => {
    const group = current, history: RecordFindings | null = findings, measured: VibrationRecord | null = vibration, shown = focus;
    if (!group || !shown) return [];
    return group.members.flatMap(member => {
      const focused = member.pick.index === shown.index;
      if (member.pick.kind === "history" && history?.intervals[member.pick.index]) return [{...historyLane(history, history.intervals[member.pick.index], focused), decision: decisions[member.key] ?? null}];
      if (member.pick.kind === "vibration" && measured?.intervals[member.pick.index]) return [{...vibrationLane(measured, measured.intervals[member.pick.index], focused), decision: decisions[member.key] ?? null}];
      return [];
    });
  });
  const ongoing=$derived.by(()=>{
    const shown=focus, history:RecordFindings|null=findings, measured:VibrationRecord|null=vibration;
    if(shown?.kind==="history"&&history?.intervals[shown.index]){
      const item=history.intervals[shown.index];
      return changeEnded(item.end,item.context?.record.to??history.record?.to,item.bucketSeconds??history.bucketSeconds)===null;
    }
    return shown?.kind==="vibration"&&measured?.intervals[shown.index]?.to===measured?.last;
  });
  /** 부하 신호(운전 수준을 나눈 전류): 조사 화면이 고른 변화 아래 같은 시간축에 그 실제 추이를 그린다. */
  const timelineLoad = $derived.by(() => {
    const shown = evidenceFocus, history: RecordFindings | null = findings;
    if (shown?.kind !== "history" || !history || !shown.item.operation) return null;
    const own = history.operation.find(entry => entry.key === shown.item.operation?.key);
    if (!own?.context || !own.channel) return null;
    const {sourceId, interpretationId} = own.context, channel = own.channel;
    return {label: own.label, unit: own.unit, read: async (from: number, to: number, signal: AbortSignal) => {
      // 기록 전체(37일 등)는 고른 기간의 한도를 넘으므로 기록 전체로 읽는다.
      const trend = (await readTrends(assetId, [channel], trendRange(from, to), "latest", signal, sourceId)).get(channel)!;
      const step = (trend.bucketSeconds ?? 0) * 1000;
      const own = trend.buckets.filter(bucket => bucket.interpretationId === interpretationId && bucket.mean !== null);
      // 평균과 함께 그 시간의 최저~최고: 두 수준을 오가는 설비는 평균이 실제로 돌지 않은 값이 된다.
      return own.map((bucket, index) => ({x: Date.parse(bucket.bucketStart), value: bucket.mean!,
        low: bucket.minimum ?? bucket.mean!, high: bucket.maximum ?? bucket.mean!,
        join: index > 0 && Date.parse(bucket.bucketStart) - Date.parse(own[index - 1].bucketStart) <= step * 1.5}));
    }};
  });
  /** 고른 변화가 판단된 출처의 운전 수준 시간표. */
  const timelineOperation = $derived.by((): TimelineOperation | null => {
    const shown = evidenceFocus, history: RecordFindings | null = findings;
    if (shown?.kind !== "history" || !history || !shown.item.operation) return null;
    const own = history.operation.find(entry => entry.key === shown.item.operation?.key);
    return own ? {names: own, columns: operationColumns(own.timeline, own.bucketSeconds)} : null;
  });
  const recordSpan = $derived.by((): Span | null => {
    const shown = focus, history: RecordFindings | null = findings, measured: VibrationRecord | null = vibration;
    if (shown?.kind === "history" && history?.record){const own=history.intervals[shown.index]?.context?.record??history.record;return {from:Date.parse(own.from),to:Date.parse(own.to)};}
    if (shown?.kind === "vibration" && measured?.first != null && measured.last != null) return {from: measured.first, to: measured.last};
    return null;
  });
  // 특이사항 시기를 고르는 칩: 날짜로 부르고, 같은 날의 시기가 여럿이면 시각까지 붙여 서로 구분한다.
  const dayOf = (at: number) => clockText(at).replace(/ \d\d:\d\d$/, "");
  const episodeChoices = $derived(grouped.map(group => ({
    label: focus?.kind !== "history" ? group.from + "~" + group.to + "번째"
      : grouped.filter(other => dayOf(other.from) === dayOf(group.from)).length > 1 ? clockText(group.from).replace(/\(.\)/, "") : dayOf(group.from),
    selected: group === current, onPick: () => selectChange(group.members[0].pick)})));
  $effect(() => {
    if (!data?.history) return;
    readRevision;
    const request = new AbortController();
    untrack(()=>{if(scope&&findings?.record&&Date.parse(findings.record.to)>scope.until){findings=null;quietMain=null;}});
    findingState = "loading";
    void readRecordFindings(assetId, request.signal, scope).then(async(value) => {
      if (!request.signal.aborted) {
        findings = value; findingState = "ready";
        const preview=value.signals.find(row=>row.channel===data?.history?.preferred&&row.preview?.length)??value.signals.find(row=>row.preview?.length);
        if(preview)quietMain={context:preview.context,label:preview.label,unit:preview.unit,axis:"time",periodSeconds:null,latest:preview.latest?{at:preview.latest.at,position:null,value:preview.latest.value}:null,trace:preview.preview!};
      }
      if(!request.signal.aborted&&!quietMain&&!scope&&!value.intervals.length){
        try{const overview=await readOverview(assetId,request.signal);if(!request.signal.aborted)quietMain=overview.main;}catch{ /* The raw signal remains available if its preview fails. */ }
      }
    }).catch(() => {if (!request.signal.aborted) findingState = "failed";});
    return () => request.abort();
  });
  onMount(() => {
    void readNotes();
    return () => noteRequest?.abort();
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
  // AI 조사의 답을 판단 메모로 옮긴 것: 그 변화의 판단·메모 대화상자가 이 초안으로 열린다.
  let memo: {reviewKey: string; sequence: number; text: string} | null = $state(null);
  // 판단하는 곳: 가운데 변화를 저장할 수 있을 때만 연다.
  const decision = $derived.by((): {reviewKey:string}|null => {
    const shown=evidenceFocus;
    const key=shown?.kind==="history"?shown.item.reviewKey:shown?.change.reviewKey;
    return key?{reviewKey:key}:null;
  });
  const focusReason = $derived.by(() => {
    const shown = evidenceFocus;
    const reason = shown?.kind === "history" ? shown.item.reason : shown?.kind === "vibration" ? shown.change.reason : null;
    return reason ? CHANGE_WHY[reason] : null;
  });
  const endedText = (history: RecordFindings, item: FoundInterval): string | null =>
    changeEnded(item.end, item.context?.record.to ?? history.record?.to, item.bucketSeconds ?? history.bucketSeconds);
  // Vibration deliveries carry an order, not always a clock; say which one is last.
  const lastMeasured = $derived.by(()=>{
    const measured:VibrationRecord|null=vibration, history:RecordFindings|null=findings;
    if(scope?.kind==="vibration")return measurementLabel(measured?.last??scope.until,measured?.periodSeconds);
    if(scope?.kind==="history")return observed(history?.signals.map(row=>row.latest?.at).filter((at):at is string=>!!at).sort().at(-1)??null);
    return !asset.lastObservedAt&&data?.vibration?measurementLabel(data.vibration.last,data.vibration.timing?.periodSeconds)+" · 측정 시각 기록 없음":observed(asset.lastObservedAt);
  });
  // The same count as the asset list: the monitor's own items plus model, receipt and baseline notes.
  const attentionCount = $derived.by((): number | null => {
    const read: Note[] | null = notes;
    return asset.attentionCount === null && read === null ? null : (asset.attentionCount ?? 0) + (read?.length ?? 0);
  });
  function attention(count: number | null): string {
    return attentionText(count,notesState);
  }
</script>

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
  <details class="context small"><summary>누적 기록의 분석 방식</summary><p>누적값은 처음 값과 마지막 값을 표시하며, 초기와 견주는 특이사항 판단에서는 제외합니다.</p></details>
{/snippet}

{#snippet context()}{#if evidenceFocus}<ChangeContext assetId={asset.assetId} focus={evidenceFocus} selected={selectedAt} onClear={() => selectedAt = null}/>{/if}{/snippet}

{#snippet assistant({colorOf, labelOf, point, close}: {colorOf: (reviewKey: string) => string | null; labelOf: (reviewKey: string) => string | null;
  point: (evidence: Evidence | null) => void; close: () => void})}
  {#if evidenceFocus && decision}{#key decision.reviewKey}
    <ChangeInvestigation assetId={asset.assetId} focus={evidenceFocus} together={lanes.length} {colorOf} {labelOf} {point} onStart={onInvestigate} onClose={close}
      onMemo={text => memo = {reviewKey: decision!.reviewKey, sequence: (memo?.sequence ?? 0) + 1, text}}/>
  {/key}{/if}
{/snippet}

{#snippet actions()}
  <div class="investigation-actions" inert={busy}>
    {#if evidenceFocus}<ChangeActions assetId={asset.assetId} focus={evidenceFocus} {onInvestigate}/>{/if}
    {#if decision}{#key decision.reviewKey}<DecisionPanel assetId={asset.assetId} reviewKey={decision.reviewKey} memo={memo?.reviewKey === decision.reviewKey ? memo : null} {onInvestigate} onCommitted={() => reviewRevision++}/>{/key}{/if}
  </div>
{/snippet}

<div class="monitor">
<section class="ui-panel facts-panel" aria-label="고른 변화" aria-busy={busy}>
  {#if current && recordSpan && lanes.length}
    <AssetTimeline context={evidenceFocus?context:undefined} assistant={evidenceFocus&&decision?assistant:undefined} axis={focus?.kind === "history" ? "time" : "acquisition"} record={recordSpan} episode={current} {ongoing}
      episodes={episodeChoices} {actions} {lanes} operation={timelineOperation} load={timelineLoad}
      periodSeconds={vibration?.periodSeconds ?? null}
      selected={selectedAt} onSelect={at => {onInvestigate?.();selectedAt = at;}}
      onFocus={key => { const item = items.find(row => row.key === key); if (item) selectChange(item.pick); }} />
  {:else if data?.history && findingState === "loading" && !quietMain}
    <p class="context">기록 전체를 기록 처음 30%와 비교하고 있습니다.</p>
  {:else if data?.history && findingState === "failed"}
    <p class="context">기록의 특이사항을 불러오지 못했습니다.
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
  {:else if data?.vibration && vibrationState === "loading" && !quietMain}
    <p class="context">진동 측정 전체를 처음 30%와 비교하고 있습니다.</p>
  {:else if data?.vibration && vibrationState === "failed"}
    <p class="context">진동 측정의 특이사항을 불러오지 못했습니다. <a href={assetTabUrl(asset.assetId, "signals", null, "vibration")}>진동 특징 추이 보기 →</a></p>
  {:else if data?.vibration && vibration}
    {#if quietMain}<h3>{quietMain.label}</h3><OverviewTrace main={quietMain} height={260}/>{/if}
    <p class="context">{vibration.judged?"초반 측정과 비교해 크게 달라진 구간이 없습니다.":"변화를 비교할 초기 측정이 아직 부족합니다."} <a href={assetTabUrl(asset.assetId, "signals", null, "vibration")}>진동 특징 추이 보기 →</a></p>
  {/if}

  {#if !evidenceFocus && settled}{@render analysisOptions()}{/if}
</section>
</div>

<details class="ui-panel provenance"><summary>측정 현황·데이터 출처·계산 범위</summary>
  {#if focusReason}<p class="context small">{focusReason}</p>{/if}
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
  .monitor{min-width:0;display:grid;gap:var(--space-3)}
  /* 오른쪽 칸 아래: 더 볼 분석(같은 모양의 줄) 다음에 판단(폭을 채운 주요 동작 하나). */
  .investigation-actions{display:grid;gap:var(--space-3)}
  .investigation-actions :global(.ui-button){min-height:40px;padding:8px 14px;font-size:var(--font-small);font-weight:650}
  .facts-panel { min-width: 0; display: grid; gap: var(--space-2); align-content: start; padding:var(--space-4); }


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
