<script lang="ts">
  import { onMount } from "svelte";
  import { readChannels, type ChannelList } from "../history";
  import {
    NoStoredEvidenceError, departureChart, readDepartures,
    type Baseline, type Departures,
  } from "../departures";
  import StatusNotice from "./StatusNotice.svelte";
  import {num} from "../format";
  import CautionNote from "./CautionNote.svelte";
  import {assetTabUrl, systemUrl} from "../routes";

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
    history.replaceState(history.state, "", url);
  }
  function changeChannel(channel: string) {
    if (!channels?.ids.includes(channel)) return;
    selectedChannel = channel;
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
      channelState = "ready";
      if (!response.ids.includes(selectedChannel)) selectedChannel = response.ids[0];
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
      const evidence = await readDepartures(assetId, selectedChannel, baseline, request.signal);
      if (request.signal.aborted) return;
      result = evidence;
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
  onMount(() => {
    void loadChannels();
    return () => { channelsRequest?.abort(); resultRequest?.abort(); };
  });
</script>

<section class="ui-panel departures" aria-labelledby="departures-title">
  <h2 id="departures-title">기준 구간 이탈</h2>
  <p class="context">모델 없이, 고른 신호가 기록 초반(기준 구간)과 비교해 언제 크게 달라졌는지 찾습니다.</p>

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
          {#each channels.ids as id (id)}<option value={id}>{id}</option>{/each}
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
      <StatusNotice message="고른 신호의 기준 구간 이탈을 불러오고 있습니다." />
    {:else if analysisState === "failed"}
      <StatusNotice kind="failure" title="기준 이탈 결과를 불러오지 못했습니다" message={error}
        actionLabel="같은 조건으로 다시 불러오기" onAction={() => void analyze()} />
    {:else if analysisState === "unavailable"}
      <StatusNotice kind="uncertain" title="비교할 저장 기록이 없습니다"
        message="이상이 없다는 뜻은 아닙니다. 신호의 저장 기록을 확인하세요."
        actionLabel="신호 보기"
        actionHref={assetTabUrl(assetId, "signals")} />
    {:else if result}
      {#if result.scored.state === "short-baseline"}
        <StatusNotice kind="uncertain" title="기준 구간의 기록이 부족합니다"
          message="이 신호는 고른 기준 구간의 기록이 적어 달라진 정도를 계산할 수 없습니다. 이상이 없다는 뜻은 아닙니다." />
      {:else if result.scored.state === "constant"}
        <StatusNotice kind="uncertain" title="기준 구간의 값이 변하지 않았습니다"
          message="기준 구간의 변동 폭이 0이라 달라진 정도를 계산할 수 없습니다." />
      {:else}
        <p class="summary">기준에서 크게 벗어난 구간 <strong>{result.intervalCount}개</strong></p>
        {#if result.intervalCount === 0}
          <p class="context">고른 기록과 기준 구간에서는 기준을 넘는 차이를 찾지 못했습니다.</p>
        {:else}
          <ol class="intervals">
            {#each result.intervals as interval, i (interval.start + interval.end + i)}
              <li>
                <strong>{date(interval.start)} ~ {date(interval.end)}</strong>
                <span>{interval.direction === "up" ? "기준보다 높음" : "기준보다 낮음"}
                  · 기준 중앙값 {num(interval.median)} → 가장 많이 벗어난 시점 {num(interval.value)}
                  {result.unit ?? "(단위 미확인)"}
                  · 기준 변동 폭의 {num(Number(interval.distance.toFixed(1)))}배</span>
              </li>
            {/each}
          </ol>
          <p class="context">가장 크게 벗어난 구간부터 최대 50개를 보여 줍니다.</p>
        {/if}
        {#if chart}
          <p class="axis-note">세로축: 기준 변동 폭의 몇 배인지 · 최고 {num(Number(chart.max.toFixed(1)))}배
            <span class="dash">· 점선: 크게 벗어났다고 보는 기준 {result.threshold}배</span></p>
          <svg viewBox={"0 0 " + chart.width + " " + chart.height} preserveAspectRatio="none" role="img"
            aria-label={"시간 순서대로 기준에서 벗어난 정도. " + date(chart.first) + "부터 " + date(chart.last) + "까지. 기록이 없는 구간은 잇지 않습니다. 정확한 값은 아래 표에 있습니다."}>
            <rect x={chart.baseline.x} y="0" width={chart.baseline.width} height={chart.height} class="baseline" />
            {#each chart.intervals as band, i (i)}
              <rect x={band.x} y="0" width={band.width} height={chart.height} class="found" />
            {/each}
            <line x1="0" x2={chart.width} y1={chart.thresholdY} y2={chart.thresholdY} class="threshold" />
            <path d={chart.path} class="line" />
            <path d={"M0 0 V" + chart.height + " H" + chart.width} class="axis" />
          </svg>
          <p class="axis-time"><span>{date(chart.first)}</span><span>→ {date(chart.last)}</span></p>
          <p class="legend"><span class="key baseline"></span>기준 구간
            {#if chart.intervals.length}<span class="key found"></span>크게 벗어난 구간{/if}</p>
          <details>
            <summary>시간별 벗어난 정도 표 ({result.score.length}개)</summary>
            <div class="table-scroll">
              <table>
                <caption>기준 구간 대비 벗어난 정도</caption>
                <thead><tr><th scope="col">구간 시각</th><th scope="col">벗어난 정도</th></tr></thead>
                <tbody>
                  {#each result.score as point, i (point.at + i)}
                    <tr><td>{date(point.at)}</td><td>{point.distance.toFixed(2)}</td></tr>
                  {/each}
                </tbody>
              </table>
            </div>
          </details>
        {/if}
        <CautionNote message="기준 구간은 고른 기록의 일부이며 정상 상태로 확인된 구간이 아닙니다. 벗어난 정도는 모델 점수나 고장 가능성이 아닙니다." />
      {/if}
      <details>
        <summary>기술 상세</summary>
        <p class="context">신호 {result.selectedChannel} · 단위 {result.unit ?? "미확인"}
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
  .summary { font-size: var(--font-section); }
  .intervals { padding-inline-start: var(--space-5); }
  .intervals li { padding-block: var(--space-3); border-bottom: 1px solid var(--color-border); }
  .intervals span { display: block; color: var(--color-ink-muted); overflow-wrap: anywhere; }
  svg { width: 100%; height: 200px; display: block; margin-top: var(--space-2); }
  svg path, svg line { vector-effect: non-scaling-stroke; }
  .axis { fill: none; stroke: var(--color-border); stroke-width: 2; }
  .line { fill: none; stroke: var(--color-action); stroke-width: 1.5; }
  .threshold { stroke: var(--color-failure-ink); stroke-dasharray: 5 4; }
  .baseline { fill: var(--color-border); opacity: 0.45; }
  .found { fill: var(--color-failure-ink); opacity: 0.14; }
  .axis-note, .axis-time, .legend { color: var(--color-ink-muted); font-size: var(--font-small); margin: var(--space-2) 0 0; }
  .axis-note { margin-top: var(--space-4); }
  .dash { color: var(--color-failure-ink); }
  .axis-time { display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--space-1) var(--space-3); }
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
