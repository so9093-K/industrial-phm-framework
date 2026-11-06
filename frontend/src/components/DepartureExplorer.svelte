<script lang="ts">
  import SourceIdentity from "./SourceIdentity.svelte";
  import {focusFrom,focusParams,type SourceFocus} from "../signal-selection";
  import {recordParams} from "../record-context";
  import {readableSourceId} from "../operations-status";
  import {short} from "../analysis-messages";
  import AnalysisMessage from "./AnalysisMessage.svelte";
  import {elapsedText} from "../time-axis";
  import { onMount } from "svelte";
  import { readChannels, signalName, type ChannelList } from "../history";
  import { defaultChannel } from "../monitor-attention";
  import {
    NoStoredEvidenceError, departureChart, readDepartures,
    type Baseline, type Departures,
  } from "../departures";
  import StatusNotice from "./StatusNotice.svelte";
  import {num} from "../format";
  import XAxis from "./XAxis.svelte";
  let scoreTable: HTMLDetailsElement | null = $state(null);
  function showFirstExceedance() {
    if (!scoreTable) return;
    scoreTable.open = true;
    scoreTable.querySelector<HTMLElement>('[data-onset="true"]')?.focus();
  }
  import {assetTabUrl, systemUrl} from "../routes";
  import {validatePeriods} from "../comparison";
  import {periodParams, windowParams, zoomWindow, pickFrom, type Span} from "../signal-selection";

  type Props = { assetId: string };
  type LoadState = "loading" | "ready" | "empty" | "unavailable" | "failed";
  let { assetId }: Props = $props();
  let channelState: LoadState = $state("loading");
  let analysisState: LoadState = $state("loading");
  let channels: ChannelList | null = $state(null);
  let result: Departures | null = $state(null);
  let error = $state("");
  let channelError = $state("");
  const params = new URLSearchParams(location.search);
  const investigation=pickFrom(params.get("monitor_pick"));
  let focus:SourceFocus|null=$state(focusFrom(params));
  let selectedRecord = $state(new URLSearchParams(location.search).get("record_key") ?? "");
  let selectedChannel = $state(params.get("monitor_channel") ?? "");
  const requestedBaseline = params.get("departure_baseline");
  let baseline: Baseline = $state(
    requestedBaseline === "first-50" || requestedBaseline === "all"
      ? requestedBaseline : "first-30",
  );
  let channelsRequest: AbortController | null = null;
  let resultRequest: AbortController | null = null;
  const chart = $derived(result ? departureChart(result) : null);

  const bases: Array<{ value: Baseline; label: string }> = [
    { value: "first-30", label: "기록 처음 30%" },
    { value: "first-50", label: "기록 처음 50%" },
    { value: "all", label: "기록 전체" },
  ];
  function date(at: string): string {
    const when = new Date(at);
    return Number.isNaN(when.getTime())
      ? "시각 해석 불가"
      : when.toLocaleString("ko-KR", {timeZone: "Asia/Seoul"});
  }
  function rememberSelection() {
    const url = new URL(location.href);
    url.searchParams.set("monitor_asset", assetId);
    url.searchParams.set("monitor_channel", selectedChannel);
    url.searchParams.set("departure_baseline", baseline);
    if(selectedRecord) url.searchParams.set("record_key",selectedRecord); else url.searchParams.delete("record_key");
    for(const key of ["monitor_source","monitor_point","monitor_interpretation"])url.searchParams.delete(key);
    if(focus)for(const [key,value] of Object.entries(focusParams(focus)))url.searchParams.set(key,value);
    history.replaceState(history.state, "", url);
  }
  function changeChannel(channel: string) {
    if (!channels?.ids.includes(channel)) return;
    selectedChannel = channel; selectedRecord = ""; if(focus)focus={...focus,interpretation:undefined};
    rememberSelection();
    void analyze();
  }
  function changeBaseline(next: Baseline) {
    baseline = next;
    rememberSelection();
    void analyze();
  }

  async function loadChannels() {
    channelsRequest?.abort();
    resultRequest?.abort();
    const request = new AbortController();
    channelsRequest = request;
    channels = null;
    result = null;
    channelState = "loading";
    analysisState = "loading";
    error = "";
    channelError = "";
    try {
      const response = await readChannels(assetId, request.signal);
      if (request.signal.aborted) return;
      channels = response;
      if (!response.ids.length) {
        channelState = "empty";
        return;
      }
      if (!response.ids.includes(selectedChannel)) selectedChannel = await defaultChannel(assetId, response.ids, request.signal);
      if (request.signal.aborted) return;
      channelState = "ready";
      rememberSelection();
      await analyze();
    } catch (cause: unknown) {
      if (request.signal.aborted) return;
      channelState = "failed";
      channelError = cause instanceof Error ? cause.message : "신호 목록 조회 오류";
    }
  }
  async function analyze() {
    resultRequest?.abort();
    const request = new AbortController();
    resultRequest = request;
    result = null;
    analysisState = "loading";
    error = "";
    try {
      const evidence = await readDepartures(assetId, selectedChannel, baseline, request.signal, selectedRecord || undefined, focus);
      if (request.signal.aborted) return;
      result = evidence; if(evidence.context)focus={source:evidence.context.sourceId,point:evidence.context.pointId,interpretation:evidence.context.interpretationId}; selectedRecord = evidence.context?.key ?? ""; rememberSelection();
      analysisState = "ready";
    } catch (cause: unknown) {
      if (request.signal.aborted) return;
      if (cause instanceof NoStoredEvidenceError) {
        analysisState = "unavailable";
      } else {
        analysisState = "failed";
        error = cause instanceof Error ? cause.message : "분석 근거 조회 오류";
      }
    }
  }
  /** A found interval opens the comparison against the baseline it was found with, and the
   * signal zoomed around it with the interval already picked. Too long a span offers neither. */
  // The range a departure is judged by, in the signal's own values, named by the chosen baseline.
  const BASELINE_TEXT: Record<string, string> = {"first-30": "기록 처음 30%", "first-50": "기록 처음 50%", all: "기록 전체"};
  function usualRange(found: Departures, unit: string | null): string {
    const {median, spread} = found.scored;
    const name = (BASELINE_TEXT[found.baseline.name] ?? "기준 구간") + "의 비교 범위";
    if (median === null || spread === null) return name;
    return name + "(" + short(median - found.threshold * spread) + "~" + short(median + found.threshold * spread) + (unit ? " " + unit : "") + ")";
  }
  function intervalLinks(found: Departures, start: string, end: string): {compare: string | null; signal: string | null} {
    const step = (found.bucketSeconds ?? 0) * 1000;
    const span: Span = {from: Date.parse(start), to: Math.max(Date.parse(end), Date.parse(start) + Math.max(step, 1000))};
    const link = (href: string, params: Record<string, string>) => {
      const url = new URL(href, location.origin);
      for (const [key, value] of Object.entries({...recordParams(found.context), ...params})) url.searchParams.set(key, value);
      return url.pathname + url.search;
    };
    const periods = {a: {from: found.baseline.from, to: found.baseline.to},
      b: {from: new Date(span.from).toISOString(), to: new Date(span.to).toISOString()}};
    let compare: string | null = null;
    try {
      validatePeriods(periods);
      compare = link(assetTabUrl(assetId, "change", "compare", "history", found.selectedChannel), periodParams(periods, "departure"));
    } catch { compare = null; }
    const window = zoomWindow(span);
    const signal = window ? link(assetTabUrl(assetId, "signals", null, null, found.selectedChannel), windowParams(window, span)) : null;
    return {compare, signal};
  }
  onMount(() => {
    void loadChannels();
    return () => { channelsRequest?.abort(); resultRequest?.abort(); };
  });
</script>

<section class="ui-panel departures" aria-labelledby="departures-title">
  <h2 id="departures-title">달라진 구간 찾기</h2>
  <p class="context">선택한 기간과 비교해 값이 크게 달라진 때를 찾습니다. 처음에는 기록 앞쪽 30%를 비교 기준으로 사용합니다.</p>
  {#if investigation}<p class="context">이어서 조사하는 구간 · {date(new Date(investigation.from).toISOString())} ~ {date(new Date(investigation.to).toISOString())}. 변화 탐색은 선택한 기록 전체를 비교 기준 기간과 견줍니다.</p>{/if}

  {#if channelState === "loading"}
    <StatusNotice message="저장된 신호 목록을 불러오고 있습니다." />
  {:else if channelState === "failed"}
    <StatusNotice kind="failure" title="신호 목록을 불러오지 못했습니다" message={channelError}
      actionLabel="다시 불러오기" onAction={() => void loadChannels()} />
  {:else if channelState === "empty"}
    <StatusNotice title="이 설비에 저장된 신호가 없습니다"
      message="데이터 연결과 수신 상태를 먼저 확인하세요."
      actionLabel="데이터 연결 확인하기" actionHref={systemUrl("connections")} />
  {:else if channels}
    <div class="controls">
      <label for="departure-channel">신호
        <select id="departure-channel" value={selectedChannel}
          onchange={(event) => changeChannel(event.currentTarget.value)}>
          {#each channels.ids as id (id)}<option value={id}>{signalName(channels.names, id)}</option>{/each}
        </select>
      </label>
      <label for="departure-baseline">비교 기준 구간
        <select id="departure-baseline" value={baseline}
          onchange={(event) => changeBaseline(event.currentTarget.value as Baseline)}>
          {#each bases as option (option.value)}
            <option value={option.value}>{option.label}</option>
          {/each}
        </select>
      </label>
    </div>
    {#if channels.truncated}
      <StatusNotice kind="uncertain" message="신호가 많아 일부만 고를 수 있습니다." />
    {/if}
    {#if analysisState === "loading"}
      <StatusNotice message="고른 신호에서 달라진 구간을 찾고 있습니다." />
    {:else if analysisState === "failed"}
      <StatusNotice kind="failure" title="달라진 구간을 확인하지 못했습니다" message={error}
        actionLabel="같은 조건으로 다시 불러오기" onAction={() => void analyze()} />
      {#if selectedRecord||focus}<button type="button" class="ui-button" onclick={()=>{selectedRecord="";focus=null;rememberSelection();void analyze();}}>이 신호의 다른 기록 보기</button>{/if}
    {:else if analysisState === "unavailable"}
      <StatusNotice kind="uncertain" title="비교할 저장 기록이 없습니다"
        message="저장 기록을 신호 화면에서 확인하세요."
        actionLabel="신호 보기"
        actionHref={assetTabUrl(assetId, "signals")} />
    {:else if result}
      {#if result.context}<SourceIdentity id={result.context.sourceId} pointId={result.context.pointId} interpretationId={result.context.interpretationId} among={result.records.map(row=>row.sourceId)}/>{/if}
      {#if result.records.length > 1}<label>분석할 기록 <select value={selectedRecord} onchange={(event) => {selectedRecord=event.currentTarget.value;focus=null;rememberSelection();void analyze();}}>
        {#each result.records as record (record.key)}<option value={record.key}>{readableSourceId(record.sourceId)} · {record.pointId ?? "위치 미지정"} · {date(record.record.from)} ~ {date(record.record.to)} · {record.meaningLabel ?? "측정 항목 미지정"}{record.unit?" · "+record.unit:""}</option>{/each}
      </select></label>{/if}
      {#if result.scored.state === "short-baseline"}
        <StatusNotice kind="uncertain" title="기준 구간의 기록이 부족합니다"
          message="이 신호는 고른 기준 구간의 기록이 적어 달라진 정도를 계산할 수 없습니다." />
      {:else if result.scored.state === "constant"}
        <StatusNotice kind="uncertain" title="기준 구간의 값이 변하지 않았습니다"
          message="기준 기간과 이후 기록에서 같은 값이 유지됩니다." />
      {:else}
        {@const first = result.intervals[0]}
        {@const unit = result.unit ?? channels?.names.get(result.selectedChannel)?.unit ?? null}
        {@const links = first ? intervalLinks(result, first.start, first.end) : null}
        <AnalysisMessage
          subject={signalName(channels?.names, result.selectedChannel)}
          basis={date(result.baseline.from) + " ~ " + date(result.baseline.to) + " · " + usualRange(result, unit)}
          message={{
            headline: result.scored.state === "level-change" ? "일정하던 측정값이 달라진 구간이 " + result.intervalCount + "개 있습니다." : result.intervalCount ? "비교 기준 범위를 크게 벗어난 구간이 " + result.intervalCount + "개 있습니다."
              : "선택한 신호에서 비교 기준 범위를 크게 벗어난 구간을 찾지 못했습니다.",
            meaning: first ? "가장 크게 벗어난 구간은 " + date(first.start) + " ~ " + date(first.end) + "입니다. "
              + elapsedText(result.bucketSeconds) + " 평균으로 가장 " + (first.direction === "down" ? "낮을" : "높을") + " 때 "
              + short(first.value) + (unit ? " " + unit : "") + "였습니다." : "선택한 기준 기간과 집계 간격에서 비교했습니다.",
            certainty: "선택한 신호의 구간별 평균을 화면에 표시한 기준 기간과 비교했습니다.",
            next: links ? [
              ...(links.signal ? [{label:"가장 크게 벗어난 구간의 신호 보기",href:links.signal}] : []),
              ...(links.compare ? [{label:"이 구간을 기준 기간과 비교",href:links.compare}] : []),
            ] : [],
          }} />
        {#if result.intervalCount === 0}
          <p class="context">고른 기록과 기준 구간에서는 기준을 넘는 차이를 찾지 못했습니다.</p>
        {:else}
          <ol class="intervals">
            {#each result.intervals as interval, i (interval.start + interval.end + i)}
              {@const links = intervalLinks(result, interval.start, interval.end)}
              {@const unit = result.unit ?? channels?.names.get(result.selectedChannel)?.unit ?? null}
              {@const down = interval.direction !== "up"}
              <li>
                <strong>{date(interval.start)} ~ {date(interval.end)}</strong>
                <span>{usualRange(result, unit)}보다 {down ? "낮음" : "높음"}
                  · {elapsedText(result.bucketSeconds)} 평균으로 가장 {down ? "낮을" : "높을"} 때 {short(interval.value)}{unit ? " " + unit : ""}</span>
                <span class="next">{#if links.compare}<a href={links.compare}>기준 구간과 비교 →</a>{/if}
                  {#if links.signal}<a href={links.signal}>신호에서 이 구간 보기 →</a>{/if}</span>
              </li>
            {/each}
          </ol>
          <p class="context">가장 크게 벗어난 구간부터 최대 50개를 보여 줍니다.</p>
        {/if}
        {#if chart}
          {#if chart.firstExceedance}
            <div class="onset" aria-label="첫 기준 초과 확인">
              <strong>첫 기준 초과 확인</strong>
              <span>{date(chart.firstExceedance.at)} (KST)</span>
              <button type="button" class="ui-button" onclick={showFirstExceedance}>시간별 값 보기 →</button>
            </div>
          {/if}
          <p class="axis-note">세로축: 기준 변동 폭의 몇 배인지 · 최고 {num(Number(chart.peak.toFixed(1)))}배
            <span class="dash">· 점선: 크게 벗어났다고 보는 기준 {result.threshold}배</span></p>
          <svg viewBox={"0 0 " + chart.width + " " + chart.height} preserveAspectRatio="none" role="img"
            aria-label={"시간 순서대로 기준에서 벗어난 정도. " + date(chart.first) + "부터 " + date(chart.last) + "까지. 기록이 없는 구간은 잇지 않습니다. 정확한 값은 아래 표에 있습니다."}>
            <rect x={chart.baseline.x} y="0" width={chart.baseline.width} height={chart.height} class="baseline" />
            {#each chart.intervals as band, i (i)}
              <rect x={band.x} y="0" width={band.width} height={chart.height} class="found" />
            {/each}
            <line x1="0" x2={chart.width} y1={chart.thresholdY} y2={chart.thresholdY} class="threshold" />
            <path d={chart.path} class="line" />
            {#if chart.firstExceedance}
              <line x1={chart.firstExceedance.x} x2={chart.firstExceedance.x} y1="0" y2={chart.height} class="onset-line">
                <title>첫 기준 초과 확인 · {date(chart.firstExceedance.at)} (KST)</title>
              </line>
              <circle cx={chart.firstExceedance.x} cy={chart.firstExceedance.y} r="4" class="onset-dot" />
            {/if}
            <path d={"M0 0 V" + chart.height + " H" + chart.width} class="axis" />
          </svg>
          <XAxis lo={Date.parse(chart.first)} hi={Math.max(Date.parse(chart.last), Date.parse(chart.first) + 1)} scale={{kind: "clock"}} />
          <p class="legend"><span class="key baseline"></span>기준 구간
            {#if chart.intervals.length}<span class="key found"></span>크게 벗어난 구간{/if}</p>
          {#if chart.firstExceedance}<p class="context">세로 점선은 표시된 집계 구간에서 처음 기준 초과를 확인한 시각입니다.</p>{/if}
          <details bind:this={scoreTable}>
            <summary>시간별 벗어난 정도 표 ({result.score.length}개)</summary>
            <div class="table-scroll">
              <table>
                <caption>기준 구간 대비 벗어난 정도</caption>
                <thead><tr><th scope="col">구간 시각</th><th scope="col">벗어난 정도</th></tr></thead>
                <tbody>
                  {#each result.score as point, i (point.at + i)}
                    <tr tabindex={point.at === chart.firstExceedance?.at ? -1 : undefined} data-onset={point.at === chart.firstExceedance?.at}><td>{date(point.at)}</td><td>{point.distance.toFixed(2)}</td></tr>
                  {/each}
                </tbody>
              </table>
            </div>
          </details>
        {/if}
      {/if}
      <details>
        <summary>기술 상세</summary>
        <p class="context">신호 {signalName(channels?.names, result.selectedChannel)} · 단위 {result.unit ?? channels?.names.get(result.selectedChannel)?.unit ?? "미확인"}
          · 기준 구간 {date(result.baseline.from)} ~ {date(result.baseline.to)}
          · 기준값 {result.threshold} · 구간 폭 약 {result.bucketSeconds}초</p>
        <p class="context">벗어난 정도 = 기준 중앙값과의 차이 ÷ 기준 구간 변동 폭(MAD 기반).
          이 결과에는 데이터 출처·측정 위치 정보가 들어 있지 않습니다.
          <a href={assetTabUrl(assetId, "signals", null, null, selectedChannel)}>신호 탭에서 출처와 품질 확인 →</a></p>
      </details>
    {/if}
  {/if}
</section>

<style>
  .departures { min-width: 0; }
  .context { color: var(--color-ink-muted); overflow-wrap: anywhere; }
  .controls { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: var(--space-4); }
  label { display: grid; gap: var(--space-1); font-weight: 650; font-size: var(--font-small); }
  select { min-width: 0; width: 100%; padding: var(--space-3); color: var(--color-ink);
    background: var(--color-surface); border: 1px solid var(--color-border);
    border-radius: var(--radius-control); }
  .intervals { padding-inline-start: var(--space-5); }
  .intervals li { padding-block: var(--space-3); border-bottom: 1px solid var(--color-border); }
  .intervals span { display: block; color: var(--color-ink-muted); overflow-wrap: anywhere; }
  .intervals .next { display: flex; flex-wrap: wrap; gap: var(--space-1) var(--space-4); margin-top: var(--space-1); }
  svg { width: 100%; height: 200px; display: block; margin-top: var(--space-2); }
  svg path, svg line { vector-effect: non-scaling-stroke; }
  .axis { fill: none; stroke: var(--color-border); stroke-width: 2; }
  .line { fill: none; stroke: var(--color-action); stroke-width: 1.5; }
  .threshold { stroke: var(--color-failure-ink); stroke-dasharray: 5 4; }
  .baseline { fill: var(--color-border); opacity: 0.45; }
  .found { fill: var(--color-failure-ink); opacity: 0.14; }
  .onset { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2) var(--space-3); margin-top: var(--space-4); padding: var(--space-3); border-left: 3px solid var(--color-caution-ink); background: var(--color-uncertain-surface); font-size: var(--font-small); }
  .onset-line { stroke: var(--color-caution-ink); stroke-width: 2; stroke-dasharray: 3 3; }
  .onset-dot { fill: var(--color-caution-ink); stroke: var(--color-surface); stroke-width: 2; }
  tr[data-onset="true"]:focus { outline: 2px solid var(--color-focus); outline-offset: -2px; }
  .axis-note, .legend { color: var(--color-ink-muted); font-size: var(--font-small); margin: var(--space-2) 0 0; }
  .axis-note { margin-top: var(--space-4); }
  .dash { color: var(--color-failure-ink); }
  .legend { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-1) var(--space-2); }
  .key { display: inline-block; width: 14px; height: 10px; border-radius: 2px; }
  .key.baseline { background: var(--color-border); }
  .key.found { background: var(--color-failure-ink); opacity: 0.3; margin-inline-start: var(--space-2); }
  summary { color: var(--color-action); font-weight: 650; cursor: pointer; padding-block: var(--space-2); }
  .table-scroll { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; margin-top: var(--space-2); font-size: var(--font-small); }
  th, td { padding: var(--space-2); border-bottom: 1px solid var(--color-border); text-align: left; }
  caption { padding-block: var(--space-2); color: var(--color-ink-muted); text-align: left; }
</style>
