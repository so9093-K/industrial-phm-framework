<script lang="ts">
  import {onMount} from "svelte";
  import {readSourceNames, sourceLabel} from "../operations-status";
  import {measure} from "../chart-axis";
  import ValueAxis from "./ValueAxis.svelte";
  import StatusNotice from "./StatusNotice.svelte";
  import {assetTabUrl, systemUrl} from "../routes";
  import {num, propertyLabel} from "../format";
  import {
    groupHistory, readChannels, readTrend, signalChart, signalName, RANGE_PRESETS,
    type ChannelList, type HistoryTrend, type RangePreset, type TimeAnchor,
  } from "../history";

  type LoadState = "idle" | "loading" | "ready" | "empty" | "failed";
  type Props = {assetId: string};
  let {assetId}: Props = $props();
  let sources: Map<string, string> = $state(new Map());
  $effect(() => { void readSourceNames().then((value) => sources = value); });

  let channelState: LoadState = $state("loading");
  let trendState: LoadState = $state("idle");
  let channels: ChannelList | null = $state(null);
  let trend: HistoryTrend | null = $state(null);
  let error = $state("");
  const params = new URLSearchParams(location.search);
  const chosenRange = params.get("monitor_range");
  const chosenAnchor = params.get("monitor_anchor");
  let selectedChannel = $state(params.get("monitor_channel") ?? "");
  // Without a chosen window the whole stored record shows, so a 4-hour file fills the chart.
  let range: RangePreset = $state(RANGE_PRESETS.find((item) => item === chosenRange) ?? "all");
  let anchor: TimeAnchor = $state(chosenAnchor === "now" ? "now" : "latest");
  let channelAbort: AbortController | null = null;
  let trendAbort: AbortController | null = null;
  const groups = $derived(trend ? groupHistory(trend) : []);

  function recorded(at: string | null): string {
    if (!at) return "관측 시각 없음";
    const d = new Date(at);
    return Number.isNaN(d.getTime()) ? "관측 시각 해석 불가"
      : d.toLocaleString("ko-KR", {timeZone: "Asia/Seoul"});
  }

  async function loadChannels() {
    channelAbort?.abort();
    trendAbort?.abort();
    const request = new AbortController();
    channelAbort = request;
    channels = null;
    trend = null;
    channelState = "loading";
    trendState = "idle";
    error = "";
    try {
      const result = await readChannels(assetId, request.signal);
      if (request.signal.aborted) return;
      channels = result;
      if (!result.ids.length) {
        channelState = "empty";
        return;
      }
      channelState = "ready";
      if (!result.ids.includes(selectedChannel)) selectedChannel = result.ids[0];
      rememberChannel();
      await loadTrend();
    } catch (cause: unknown) {
      if (request.signal.aborted) return;
      channelState = "failed";
      error = cause instanceof Error ? cause.message : "저장 신호 목록을 읽을 수 없습니다.";
    }
  }

  function rememberChannel() {
    const url = new URL(location.href);
    url.searchParams.set("monitor_asset", assetId);
    url.searchParams.set("monitor_channel", selectedChannel);
    url.searchParams.set("monitor_range", range);
    url.searchParams.set("monitor_anchor", anchor);
    history.replaceState(history.state, "", url);
  }

  function changeChannel(value: string) {
    if (!channels?.ids.includes(value)) return;
    selectedChannel = value;
    rememberChannel();
    void loadTrend();
  }

  async function loadTrend() {
    trendAbort?.abort();
    const request = new AbortController();
    trendAbort = request;
    trend = null;
    error = "";
    trendState = "loading";
    try {
      const result = await readTrend(assetId, selectedChannel, range, anchor, request.signal);
      if (request.signal.aborted) return;
      trend = result;
      trendState = result.buckets.length || result.latest.length ? "ready" : "empty";
    } catch (cause: unknown) {
      if (request.signal.aborted) return;
      trendState = "failed";
      error = cause instanceof Error ? cause.message : "선택한 신호 이력을 읽지 못했습니다.";
    }
  }

  onMount(() => {
    void loadChannels();
    return () => {
      channelAbort?.abort();
      trendAbort?.abort();
    };
  });
</script>

<section class="explorer ui-panel" aria-labelledby="explorer-title">
  <h2 id="explorer-title">측정 신호</h2>
  <p class="context">고른 신호의 저장된 측정값과 원본 품질을 시간 순서로 봅니다.</p>
  {#if channelState === "loading"}
    <StatusNotice message="저장된 신호 목록을 불러오고 있습니다." />
  {:else if channelState === "failed"}
    <StatusNotice kind="failure" title="신호 목록을 불러오지 못했습니다" message={error}
      actionLabel="다시 불러오기" onAction={() => void loadChannels()} />
  {:else if channelState === "empty"}
    <StatusNotice title="저장된 신호가 없습니다"
      message="이 설비에 저장된 신호가 없습니다. 데이터 연결과 수신 상태를 확인하세요."
      actionLabel="데이터 연결 확인하기" actionHref={systemUrl("connections")} />
  {:else if channels}
    <div class="controls">
      <label for="history-channel">신호
        <select id="history-channel" value={selectedChannel}
          onchange={(event) => changeChannel(event.currentTarget.value)}>
          {#each channels.ids as id (id)}
            <option value={id}>{signalName(channels.names, id)}</option>
          {/each}
        </select>
      </label>
      <label for="history-range">조회 기간
        <select id="history-range" value={range}
          onchange={(event) => { range = event.currentTarget.value as RangePreset; rememberChannel(); void loadTrend(); }}>
          <option value="all">저장된 전체 기록</option>
          <option value="15m">최근 15분</option><option value="1h">최근 1시간</option>
          <option value="24h">최근 24시간</option><option value="7d">최근 7일</option>
        </select>
      </label>
      {#if range !== "all"}<label for="history-anchor">기간 기준
        <select id="history-anchor" value={anchor}
          onchange={(event) => { anchor = event.currentTarget.value as TimeAnchor; rememberChannel(); void loadTrend(); }}>
          <option value="latest">마지막 저장 기록</option>
          <option value="now">지금</option>
        </select>
      </label>{/if}
    </div>
    <nav class="continue" aria-label="이 신호로 이어서 보기">
      <span>이 신호로 이어서 보기</span>
      <a href={assetTabUrl(assetId, "anomaly", "baseline", null, selectedChannel)}>기준 구간 이탈 →</a>
      <a href={assetTabUrl(assetId, "change", "compare", "history", selectedChannel)}>두 기간 비교 →</a>
      <a href={assetTabUrl(assetId, "outlook", null, "history", selectedChannel)}>기준 도달 전망 →</a>
    </nav>
    {#if channels.truncated}
      <StatusNotice kind="uncertain" message="신호가 많아 일부만 표시합니다." />
    {/if}
    {#if trendState === "loading"}
      <StatusNotice message="고른 신호의 측정 기록과 품질을 불러오고 있습니다." />
    {:else if trendState === "failed"}
      <StatusNotice kind="failure" title="측정 기록을 불러오지 못했습니다" message={error}
        actionLabel="다시 불러오기" onAction={() => void loadTrend()} />
    {:else if trendState === "empty"}
      <StatusNotice title="이 기간에 표시할 측정이 없습니다"
        message="고른 기간에 저장된 측정이 없습니다. 다른 기간이나 신호를 고르세요." />
    {:else if trend}
      <p class="context">
        {recorded(trend.startAt)} ~ {recorded(trend.endAt)}
        · {range === "all" ? "저장된 전체 기록" : anchor === "latest" ? "마지막 저장 기록 기준" : "지금 기준"}
      </p>
      <p class="explain">
        선은 시간 구간별 평균, 옅은 막대는 그 구간 안의 최소~최대입니다. 빠진 값이나 품질 불량은
        잇거나 채우지 않고, 데이터 출처·측정 위치가 다르면 따로 그립니다.
      </p>
      {#if groups.length === 0}
        <StatusNotice kind="uncertain" message="고른 기간에 그릴 구간은 없지만 아래에 마지막 저장값이 있을 수 있습니다." />
      {/if}
      {#each groups as group (group.key)}
        {@const chart = signalChart(group, trend.startAt, trend.endAt, trend.bucketSeconds)}
        <section class="series" aria-label={"측정 기록 " + group.sourceId}>
          <h3>{signalName(channels?.names, selectedChannel)}{groups.length > 1 ? " · 데이터 출처 " + sourceLabel(sources, group.sourceId) : ""}</h3>
          <p class="context">
            데이터 출처 {sourceLabel(sources, group.sourceId)} · 측정 위치 {group.pointId ?? "미등록"}
            {#if group.observedProperty} · 측정 의미 {propertyLabel(group.observedProperty)}{/if}
            · 단위 {group.unit ?? channels?.names.get(selectedChannel)?.unit ?? "기록 없음"}
          </p>
          {#if group.unitEvidence || group.interpretationEvidence}<details><summary>측정 의미의 근거</summary><p class="context">단위 근거 · {group.unitEvidence ?? "기록 없음"}</p><p class="context">해석 근거 · {group.interpretationEvidence ?? "기록 없음"}</p></details>{/if}
          {#if chart}
            {@const unit = group.unit ?? channels?.names.get(selectedChannel)?.unit ?? null}
            <p class="axis-note">최고 {measure(chart.high, unit)} · 최저 {measure(chart.low, unit)}</p>
            <ValueAxis ticks={chart.ticks} height={chart.height} {unit}>
            <svg viewBox={"0 0 " + chart.width + " " + chart.height} preserveAspectRatio="none" role="img"
              aria-label={signalName(channels?.names, selectedChannel) + "의 시간 구간별 평균과 최소~최대. " + recorded(trend.startAt) + "부터 " + recorded(trend.endAt) + "까지. 빈 곳은 기록이 없는 구간입니다."}>
              {#each chart.ticks as tick (tick.value)}<line x1="0" x2={chart.width} y1={tick.y} y2={tick.y} class="grid" />{/each}
              {#each chart.marks as mark (mark.bucket.bucketStart)}
                <line x1={mark.x} x2={mark.x} y1={mark.min} y2={mark.max} class="range" />
                <line x1={mark.x - 3} x2={mark.x + 3} y1={mark.mean} y2={mark.mean} class="mean" />
              {/each}
              <path d={chart.path} class="line" />
              <path d={"M0 0 V" + chart.height + " H" + chart.width} class="axis" />
            </svg>
            {#snippet footer()}<p class="axis-time"><span>{recorded(chart.from)}</span><span>→ {recorded(trend?.endAt ?? null)}</span></p>{/snippet}
            </ValueAxis>
          {:else}
            <p class="context">그릴 수 있는 평균값이 없습니다. 빠진 값을 0으로 채우지 않습니다.</p>
          {/if}
          <details>
            <summary>시간별 평균·결측·원본 품질 확인 ({group.buckets.length}개 구간)</summary>
            {#if group.buckets.length > 120}
              <p class="context">표에는 최근 120개 구간만 표시합니다.</p>
            {/if}
            <div class="table-scroll">
              <table>
                <caption>시간 구간별 집계 · 개별 측정값이 아님</caption>
                <thead><tr><th scope="col">기간 시작 (KST)</th><th scope="col">유효</th>
                  <th scope="col">평균</th><th scope="col">결측</th>
                  <th scope="col">품질 불량</th><th scope="col">충돌</th></tr></thead>
                <tbody>
                  {#each group.buckets.slice(-120) as bucket (bucket.bucketStart)}
                    <tr>
                      <td>{recorded(bucket.bucketStart)}</td><td>{bucket.usableCount}</td>
                      <td>{bucket.mean === null || bucket.usableCount === 0 ? "—" : bucket.mean}</td>
                      <td>{bucket.nullCount}</td><td>{bucket.nonGoodCount}</td><td>{bucket.conflictCount}</td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          </details>
        </section>
      {/each}
      {#if trend.latest.length}
        <section class="latest">
          <h3>마지막 저장값</h3>
          <p class="context">지금 수신 중인 값이 아니라 마지막으로 저장된 값입니다.</p>
          <ul>
            {#each trend.latest as item (JSON.stringify([item.sourceId,item.pointId,item.channelId]))}
              <li>{sourceLabel(sources, item.sourceId)} / {item.pointId ?? "미등록"}
                · {recorded(item.eventAt)} · {item.usable ? num(item.value, "값 없음") : "품질 문제로 표시 안 함"}
                · 원본 품질 {item.quality === "unknown" ? "기록 없음" : item.quality}</li>
            {/each}
          </ul>
        </section>
      {/if}
    {/if}
  {/if}
</section>

<style>
  .explorer { min-width: 0; }
  .context, .explain { color: var(--color-ink-muted); overflow-wrap: anywhere; }
  .explain { margin-block: var(--space-5); }
  .continue { display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-4); margin-block: var(--space-4); align-items: baseline; }
  .continue span { color: var(--color-ink-muted); font-size: var(--font-small); }
  .controls { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: var(--space-3); }
  label { display: grid; gap: var(--space-1); font-weight: 650; font-size: var(--font-small); }
  select {
    min-width: 0;
    width: 100%;
    padding: var(--space-3);
    color: var(--color-ink);
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-control);
  }
  .series { margin-block: var(--space-6); padding-top: var(--space-4); border-top: 1px solid var(--color-border); }
  h3 { font-size: var(--font-body); overflow-wrap: anywhere; }
  svg { display: block; width: 100%; height: 200px; }
  .grid { stroke: var(--color-border); stroke-width: 1; opacity: 0.7; vector-effect: non-scaling-stroke; }
  svg path, svg line { vector-effect: non-scaling-stroke; }
  .axis { fill: none; stroke: var(--color-border); stroke-width: 2; }
  .line { fill: none; stroke: var(--color-action); stroke-width: 1.5; }
  .range { stroke: var(--color-action); stroke-width: 4; opacity: 0.22; }
  .mean { stroke: var(--color-action); stroke-width: 2; }
  .axis-note, .axis-time { color: var(--color-ink-muted); font-size: var(--font-small); margin: var(--space-3) 0 0; }
  .axis-time { display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--space-1) var(--space-3); margin-top: var(--space-1); }
  details { margin-top: var(--space-3); }
  summary { cursor: pointer; color: var(--color-action); font-weight: 650; }
  .table-scroll { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-size: var(--font-small); margin-top: var(--space-3); }
  caption { text-align: left; color: var(--color-ink-muted); padding-block: var(--space-2); }
  th, td { border-bottom: 1px solid var(--color-border); padding: var(--space-2); text-align: left; }
  .latest { margin-top: var(--space-6); }
  .latest li { margin-block: var(--space-2); overflow-wrap: anywhere; }
</style>
