<script lang="ts">
  import { onMount } from "svelte";
  import { readChannels, type ChannelList } from "../history";
  import {
    NoStoredEvidenceError, readDepartures, scoreDots,
    type Baseline, type Departures,
  } from "../departures";
  import StatusNotice from "./StatusNotice.svelte";

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
  const dots = $derived(result ? scoreDots(result) : []);

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
  <h2 id="departures-title">모델 없이 기준에서 달라진 구간 찾기</h2>
  <p class="context">설비: <strong>{assetId}</strong> · 기존 저장 기록의 시간 버킷 평균을 비교합니다.</p>
  <p class="context">
    이 비교의 '기준 구간'은 사용자가 고른 기록 부분이지, 정상 운전이나 고장 판정 기준이 아닙니다.
    현재 API는 비교에 사용된 source·measurement point 식별자를 제공하지 않습니다.
    정확한 원본 출처는 저장 신호 탐색에서 별도로 확인하세요.
  </p>

  {#if channelState === "loading"}
    <StatusNotice message="저장된 신호 목록을 확인합니다." />
  {:else if channelState === "failed"}
    <StatusNotice kind="failure" title="신호 목록 조회 실패" message={channelError}
      actionLabel="신호 목록 다시 조회" onAction={() => void loadChannels()} />
  {:else if channelState === "empty"}
    <StatusNotice title="이 설비에 저장된 신호가 없습니다"
      message="데이터 등록·수신·저장 근거를 먼저 확인하세요."
      actionLabel="연결 확인" actionHref="/web/#connect" />
  {:else if channels}
    <div class="controls">
      <label for="departure-channel">측정 신호
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
    <p class="context"><a href={"/web-next/?view=signals&monitor_asset=" + encodeURIComponent(assetId)
      + "&monitor_channel=" + encodeURIComponent(selectedChannel)}>선택 신호의 저장값·원본 출처·품질 확인 →</a></p>
    {#if channels.truncated}
      <StatusNotice kind="uncertain" message="서버 제한으로 일부 신호만 선택할 수 있습니다." />
    {/if}
    {#if analysisState === "loading"}
      <StatusNotice message="선택한 신호의 기준 구간 이탈을 계산한 서버 결과를 확인합니다." />
    {:else if analysisState === "failed"}
      <StatusNotice kind="failure" title="기준 이탈 분석 조회 실패" message={error}
        actionLabel="같은 조건으로 재조회" onAction={() => void analyze()} />
    {:else if analysisState === "unavailable"}
      <StatusNotice kind="uncertain" title="저장된 비교 근거가 없습니다"
        message="이 결과는 '이상이 없음'을 뜻하지 않습니다. 저장 기록과 신호를 확인하세요."
        actionLabel="저장 신호 확인"
        actionHref={"/web-next/?view=signals&monitor_asset=" + encodeURIComponent(assetId)} />
    {:else if result}
      <p class="context">계산 기준: {date(result.baseline.from)} ~ {date(result.baseline.to)}
        · 임계값 {result.threshold} · 비교된 버킷 폭 약 {result.bucketSeconds}초</p>
      <p class="context">선택한 신호: <strong>{result.selectedChannel}</strong>
        · 단위 {result.unit ?? "미확인"}</p>

      {#if result.scored.state === "short-baseline"}
        <StatusNotice kind="uncertain" title="비교 기록이 부족합니다"
          message="이 신호는 선택한 기준 구간의 기록이 부족해 이탈 정도를 평가할 수 없습니다. 이상 없음으로 판단하지 않습니다." />
      {:else if result.scored.state === "constant"}
        <StatusNotice kind="uncertain" title="기준 구간 값의 변화가 없습니다"
          message="이 신호의 기준 구간 변동 폭이 0이어서 이탈 점수를 계산하지 못했습니다." />
      {:else}
        <p class="summary">기준에서 크게 벗어난 구간 <strong>{result.intervalCount}개</strong></p>
        {#if result.intervalCount === 0}
          <StatusNotice message="선택한 기록·기준 구간에서 서버 임계값 이상의 차이를 찾지 못했습니다. 정상 설비 또는 고장 확률 0%의 뜻이 아닙니다." />
        {:else}
          <p class="context">가장 크게 벗어난 구간부터 최대 50개를 보여줍니다.</p>
          <ol class="intervals">
            {#each result.intervals as interval, i (interval.start + interval.end + i)}
              <li>
                <strong>{date(interval.start)} ~ {date(interval.end)}</strong>
                <span>{interval.direction === "up" ? "기준 중앙값보다 높음" : "기준 중앙값보다 낮음"}
                  · 기준 중앙값 {interval.median} → 관측 버킷 평균 {interval.value}
                  {result.unit ?? "(단위 미확인)"}
                  · 기준 변동 폭 대비 거리 {interval.distance.toFixed(2)}</span>
              </li>
            {/each}
          </ol>
        {/if}
        <p class="context">이탈 거리 = 기준 중앙값과의 차이 ÷ 기준 구간 변동 폭(MAD 기반). 모델 점수, 고장 가능성 또는 설비 안전 등급이 아닙니다.</p>
        {#if dots.length}
          <svg viewBox="0 0 650 150" role="img"
            aria-label="기준에서 벗어난 상대적 정도를 시간순 점으로 표시. 점 사이 빈 구간은 보간하지 않습니다. 정확한 값은 아래 표를 참조하세요.">
            <path d="M36 18 V121 H626" class="axis" />
            {#each dots as dot (dot.at)}
              <circle cx={dot.x} cy={dot.y} r="3.5" class="dot">
                <title>{date(dot.at)} · 기준 이탈 거리 {dot.distance.toFixed(2)}</title>
              </circle>
            {/each}
          </svg>
          <details>
            <summary>시간별 이탈 점수 표 ({result.score.length}개)</summary>
            <div class="table-scroll">
              <table>
                <caption>모델 점수가 아닌 선택한 기준 구간 대비 상대적인 이탈 정도</caption>
                <thead><tr><th scope="col">버킷 시각</th><th scope="col">상대 거리</th></tr></thead>
                <tbody>
                  {#each result.score as point, i (point.at + i)}
                    <tr><td>{date(point.at)}</td><td>{point.distance.toFixed(2)}</td></tr>
                  {/each}
                </tbody>
              </table>
            </div>
          </details>
        {/if}
      {/if}
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
  svg { width: 100%; height: auto; display: block; margin-block: var(--space-4); }
  .axis { fill: none; stroke: var(--color-border); stroke-width: 2; }
  .dot { fill: var(--color-action); }
  summary { color: var(--color-action); font-weight: 650; cursor: pointer; }
  .table-scroll { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; margin-top: var(--space-2); font-size: var(--font-small); }
  th, td { padding: var(--space-2); border-bottom: 1px solid var(--color-border); text-align: left; }
  caption { padding-block: var(--space-2); color: var(--color-ink-muted); text-align: left; }
</style>
