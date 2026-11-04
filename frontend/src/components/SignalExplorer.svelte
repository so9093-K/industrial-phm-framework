<script lang="ts">
  import {onMount, tick} from "svelte";
  import {readSourceNames, sourceLabel} from "../operations-status";
  import {measure} from "../chart-axis";
  import ValueAxis from "./ValueAxis.svelte";
  import XAxis from "./XAxis.svelte";
  import StatusNotice from "./StatusNotice.svelte";
  import {assetTabUrl, systemUrl} from "../routes";
  import {num, propertyLabel} from "../format";
  import {
    groupHistory, latestUnit, readChannels, recordEnd, readTrend, signalChart, signalName, RANGE_PRESETS,
    type ChannelList, type HistoryGroup, type HistoryTrend, type RangePreset, type SignalChart, type TimeAnchor,
  } from "../history";
  import {
    atFinest, covers, EDGE_MS, focusFrom, focusGroups, focusParams, type SourceFocus, periodParams, periodsBefore, pickFrom, previousSpan, snapInside, snapSpan, summarize, zoomWindow, MAX_SPAN_MS,
    type Span,
  } from "../signal-selection";
  import { defaultChannel } from "../monitor-attention";
  // The source's own quality code, said in words; an unknown code stays as recorded.
  const QUALITY: Record<string, string> = {good: "양호", bad: "불량", uncertain: "불확실", unknown: "기록 없음"};

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
  // A window chosen on the chart (zoom) replaces the preset; anything unreadable shows all.
  function chosenWindow(): Span | null {
    if (chosenRange !== "window") return null;
    const from = Date.parse(params.get("monitor_from") ?? ""), to = Date.parse(params.get("monitor_to") ?? "");
    return Number.isFinite(from) && Number.isFinite(to) && to - from >= 1000 && to - from <= MAX_SPAN_MS ? {from, to} : null;
  }
  const initialZoom = chosenWindow();
  let zoom: Span | null = $state(initialZoom);
  // Without a chosen window the whole stored record shows, so a 4-hour file fills the chart.
  let range: RangePreset | "window" = $state(initialZoom ? "window" : RANGE_PRESETS.find((item) => item === chosenRange) ?? "all");
  // A picked moment or span stays while the signal changes, so the same time can be read on another signal.
  let picked: Span | null = $state(null);
  let drag: {key: string; from: number; to: number; x: number} | null = $state(null);
  // One card per source chart; a pick scrolls to the card under the chart that was clicked.
  const cards: Record<string, HTMLElement | null> = {};
  // A moment or span handed over from another screen (a scatter point, a departure) is picked once the chart loads.
  let pending = pickFrom(params.get("monitor_pick"));
  let anchor: TimeAnchor = $state(chosenAnchor === "now" ? "now" : "latest");
  let channelAbort: AbortController | null = null;
  let trendAbort: AbortController | null = null;
  // A source (and point) handed over from another screen, e.g. a scatter point's own record.
  let focus: SourceFocus | null = $state(focusFrom(params));
  const groups = $derived.by(() => {
    const current: HistoryTrend | null = trend;
    return focusGroups(current ? groupHistory(current) : [], focus);
  });

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
      if (!result.ids.includes(selectedChannel)) selectedChannel = await defaultChannel(assetId, result.ids, request.signal);
      if (request.signal.aborted) return;
      channelState = "ready";
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
    if (range === "window" && zoom) {
      url.searchParams.set("monitor_from", new Date(zoom.from).toISOString());
      url.searchParams.set("monitor_to", new Date(zoom.to).toISOString());
    } else {url.searchParams.delete("monitor_from"); url.searchParams.delete("monitor_to");}
    url.searchParams.delete("monitor_source"); url.searchParams.delete("monitor_point");
    for (const [key, value] of Object.entries(focus ? focusParams(focus) : {})) url.searchParams.set(key, value);
    url.searchParams.delete("monitor_pick");
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
      const chosen = range === "window" && zoom
        ? {from: new Date(zoom.from).toISOString(), to: new Date(zoom.to).toISOString()} : null;
      const result = await readTrend(assetId, selectedChannel, chosen ?? (range === "window" ? "all" : range), anchor,
        request.signal, focus?.source ?? null);
      if (request.signal.aborted) return;
      trend = result;
      trendState = result.buckets.length || result.latest.length ? "ready" : "empty";
      const read = {from: Date.parse(result.startAt), to: Date.parse(result.endAt)};
      const step = result.bucketSeconds ? result.bucketSeconds * 1000 : null;
      if (pending) {
        picked = snapSpan(pending.from, pending.to, read.from, read.to, step);
        pending = null;
      } else if (picked && (picked.to <= read.from || picked.from >= read.to)) {
        // A pick wholly outside the new range (e.g. after switching to the last 15 minutes) is dropped.
        picked = null;
      } else if (picked && covers(read, picked)) {
        // A new window has its own buckets; the shown span stays exactly the buckets summed.
        picked = snapInside(picked, read.from, read.to, step);
      }
    } catch (cause: unknown) {
      if (request.signal.aborted) return;
      trendState = "failed";
      error = cause instanceof Error ? cause.message : "선택한 신호 이력을 읽지 못했습니다.";
    }
  }

  // The read window and its bucket grid: buckets start at the window start and share one width.
  const grid = $derived.by(() => {
    const current: HistoryTrend | null = trend;
    if (!current) return null;
    const from = Date.parse(current.startAt), to = Date.parse(current.endAt);
    const step = current.bucketSeconds ? current.bucketSeconds * 1000 : null;
    return {from, to, step, slots: step ? Math.max(1, Math.round((to - from) / step)) : 0};
  });
  // One bucket picked by a tap reads as a moment; a dragged span reads as a period.
  const single = $derived.by(() => {
    const span: Span | null = picked, step = grid?.step ?? null;
    return span !== null && step !== null && span.to - span.from <= step * 1.001;
  });
  function timeAt(event: PointerEvent, chart: SignalChart): number {
    const box = (event.currentTarget as Element).getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (event.clientX - box.left) / Math.max(box.width, 1)));
    return chart.start + ratio * (chart.end - chart.start);
  }
  function press(event: PointerEvent, key: string, chart: SignalChart) {
    if (event.button !== 0) return;
    (event.currentTarget as Element).setPointerCapture(event.pointerId);
    const at = timeAt(event, chart);
    drag = {key, from: at, to: at, x: event.clientX};
  }
  function slide(event: PointerEvent, chart: SignalChart) {
    if (drag) drag = {...drag, to: timeAt(event, chart)};
  }
  async function release(event: PointerEvent, chart: SignalChart) {
    const current = drag;
    drag = null;
    if (!current || !grid) return;
    if (Math.abs(event.clientX - current.x) > 6) {
      picked = snapSpan(current.from, timeAt(event, chart), grid.from, grid.to, grid.step);
    } else {
      // A tap picks the nearest drawn bucket, so the card always has a value to show.
      const at = timeAt(event, chart);
      const nearest = chart.marks.reduce((best, mark) =>
        Math.abs(Date.parse(mark.bucket.bucketStart) - at) < Math.abs(Date.parse(best.bucket.bucketStart) - at) ? mark : best);
      const start = Date.parse(nearest.bucket.bucketStart);
      picked = snapSpan(start, start, grid.from, grid.to, grid.step);
    }
    await tick();
    cards[current.key]?.scrollIntoView({block: "nearest"});
  }
  function scrub(slot: number) {
    if (!grid?.step) return;
    const start = grid.from + slot * grid.step;
    picked = snapSpan(start, start, grid.from, grid.to, grid.step);
  }
  function zoomTo(span: Span) {
    const window = zoomWindow(span);
    if (!window) return;
    zoom = window; range = "window";
    rememberChannel(); void loadTrend();
  }
  function unzoom() {
    zoom = null; range = "all";
    rememberChannel(); void loadTrend();
  }
  function shade(chart: SignalChart, span: Span): {x: number; width: number} | null {
    const from = Math.max(span.from, chart.start), to = Math.min(span.to, chart.end);
    if (to <= from) return null;
    const x = (at: number) => ((at - chart.start) / (chart.end - chart.start)) * chart.width;
    return {x: x(from), width: Math.max(x(to) - x(from), 2)};
  }
  function linkTo(href: string, extra: Record<string, string>): string {
    const url = new URL(href, location.origin);
    for (const [key, value] of Object.entries(extra)) url.searchParams.set(key, value);
    return url.pathname + url.search;
  }
  const spanText = (span: Span) => span.to - span.from < 1000 ? recorded(new Date(span.from).toISOString())
    : recorded(new Date(span.from).toISOString()) + " ~ " + recorded(new Date(span.to).toISOString());
  const finest = $derived.by(() => { const current: HistoryTrend | null = trend; return current ? atFinest(current.buckets) : false; });
  function change(now: number | null, before: number | null, unit: string | null): string {
    if (now === null || before === null) return "";
    const diff = now - before;
    return (diff > 0 ? "+" : diff < 0 ? "−" : "") + measure(Math.abs(diff), unit);
  }

  onMount(() => {
    void loadChannels();
    return () => {
      channelAbort?.abort();
      trendAbort?.abort();
    };
  });
</script>

{#snippet pick(group: HistoryGroup, span: Span, unit: string | null)}
  {@const now = summarize(group, span)}
  {@const before = grid && covers(grid, previousSpan(span)) ? summarize(group, previousSpan(span)) : null}
  {@const periods = periodsBefore(span)}
  <section class="pick" bind:this={cards[group.key]} aria-label={(single ? "선택한 시점" : "선택한 구간") + " · " + sourceLabel(sources, group.sourceId)}>
    <div class="pick-head"><h4>{single ? "선택한 시점" : "선택한 구간"}</h4><span>{spanText(span)}</span></div>
    {#if !now || now.mean === null}
      <p>고른 {single ? "시점" : "구간"}에 쓸 수 있는 측정이 없습니다. 빈 곳을 0으로 채우지 않습니다.</p>
    {:else}
      <p class="pick-value">평균 <strong>{measure(now.mean, unit)}</strong>
        {#if now.minimum !== null && now.maximum !== null}<span> · 최소~최대 {measure(now.minimum, unit)} ~ {measure(now.maximum, unit)}</span>{/if}</p>
      {#if before?.mean != null}
        <p>바로 앞 같은 길이 기간 평균 {measure(before.mean, unit)} · 차이 <strong>{change(now.mean, before.mean, unit)}</strong></p>
      {:else if grid && !covers(grid, previousSpan(span))}
        <p class="context">바로 앞 같은 길이 기간은 지금 그래프 범위 밖입니다. 두 기간 비교에서 확인하세요.</p>
      {:else}
        <p class="context">바로 앞 같은 길이 기간에는 쓸 수 있는 측정이 없습니다.</p>
      {/if}
    {/if}
    {#if grid && !covers(grid, span)}<p class="context">고른 {single ? "시점" : "구간"}의 일부가 지금 그래프 범위 밖이라 범위 안의 측정만 합했습니다.</p>{/if}
    {#if now}<p class="context">유효 측정 {now.usable} · 결측 {now.missing} · 품질 불량 {now.nonGood} · 값 충돌 {now.conflict}</p>{/if}
    <div class="pick-actions">
      {#if periods}
        <a class="ui-button ui-button-primary" href={linkTo(assetTabUrl(assetId, "change", "compare", "history", selectedChannel), periodParams(periods))}>바로 앞 기간과 비교하기 →</a>
        {#if (channels?.ids.length ?? 0) > 1}
          <a class="ui-button" href={linkTo(assetTabUrl(assetId, "change", "relation", "history"), {...periodParams(periods), relation_x: selectedChannel})}>다른 신호와 관계 보기 →</a>
        {/if}
      {:else}
        <span class="context">31일 이하로 고르면 바로 앞 기간과 비교할 수 있습니다.</span>
      {/if}
      {#if zoomWindow(span) && !finest}<button type="button" class="ui-button" onclick={() => zoomTo(span)}>이 {single ? "시점 주변" : "구간"} 확대</button>{/if}
      <button type="button" class="ui-button quiet" onclick={() => picked = null}>선택 해제</button>
    </div>
  </section>
{/snippet}

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
          onchange={(event) => { range = event.currentTarget.value as RangePreset; zoom = null; rememberChannel(); void loadTrend(); }}>
          {#if range === "window"}<option value="window" disabled>그래프에서 고른 구간</option>{/if}
          <option value="all">저장된 전체 기록</option>
          <option value="15m">최근 15분</option><option value="1h">최근 1시간</option>
          <option value="24h">최근 24시간</option><option value="7d">최근 7일</option>
        </select>
      </label>
      {#if range !== "all" && range !== "window"}<label for="history-anchor">기간 기준
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
        {recorded(trend.startAt)} ~ {recorded(range === "all" ? recordEnd(trend) ?? trend.endAt : trend.endAt)}
        · {range === "all" ? "저장된 전체 기록" : range === "window" ? "그래프에서 고른 구간을 확대" : anchor === "latest" ? "마지막 저장 기록 기준" : "지금 기준"}
      </p>
      {#if focus}
        <p class="zoomed"><span>데이터 출처 {sourceLabel(sources, focus.source)}{focus.point === undefined ? "" : focus.point === null ? " · 측정 위치 지정 없음" : " · 측정 위치 " + focus.point}만 보고 있습니다.</span>
          <button type="button" class="ui-button" onclick={() => { focus = null; rememberChannel(); void loadTrend(); }}>모든 출처 보기</button></p>
      {/if}
      {#if range === "window"}
        <p class="zoomed"><span>고른 구간을 확대해서 보고 있습니다.</span>
          <button type="button" class="ui-button" onclick={unzoom}>전체 기록으로 돌아가기</button></p>
      {/if}
      <p class="explain">
        선은 시간 구간별 평균, 옅은 막대는 그 구간 안의 최소~최대입니다. 빠진 값이나 품질 불량은
        잇거나 채우지 않고, 데이터 출처·측정 위치가 다르면 따로 그립니다.
        그래프를 누르면 그 시점을, 옆으로 끌면 구간을 고릅니다.
      </p>
      {#if groups.length === 0}
        <StatusNotice kind="uncertain" message="고른 기간에 그릴 구간은 없지만 아래에 마지막 저장값이 있을 수 있습니다." />
      {/if}
      {#each groups as group (group.key)}
        {@const chart = signalChart(group, trend.startAt, trend.endAt, trend.bucketSeconds)}
        <section class="series" aria-label={"측정 기록 " + group.sourceId}>
          <h3>{signalName(channels?.names, selectedChannel)}{groups.length > 1 ? " · 데이터 출처 " + sourceLabel(sources, group.sourceId) : ""}</h3>
          <p class="context">
            데이터 출처 {sourceLabel(sources, group.sourceId)}{group.pointId ? " · 측정 위치 " + group.pointId : ""}
            {#if group.observedProperty} · 측정 의미 {propertyLabel(group.observedProperty)}{/if}
            {#if group.unit ?? channels?.names.get(selectedChannel)?.unit} · 단위 {group.unit ?? channels?.names.get(selectedChannel)?.unit}{/if}
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
              {#if picked}{@const band = shade(chart, picked)}{#if band}<rect x={band.x} y="0" width={band.width} height={chart.height} class="picked" />{/if}{/if}
              {#if drag?.key === group.key}{@const band = shade(chart, {from: Math.min(drag.from, drag.to), to: Math.max(drag.from, drag.to)})}{#if band}<rect x={band.x} y="0" width={band.width} height={chart.height} class="dragging" />{/if}{/if}
              <path d={chart.path} class="line" />
              {#if picked && single}
                {@const mark = chart.marks.find((item) => Math.abs(Date.parse(item.bucket.bucketStart) - (picked?.from ?? 0)) < EDGE_MS)}
                {#if mark}<line x1={mark.x} x2={mark.x} y1="0" y2={chart.height} class="cursor" />
                  <line x1={mark.x} x2={mark.x} y1={mark.mean} y2={mark.mean} class="dot" />{/if}
              {/if}
              <path d={"M0 0 V" + chart.height + " H" + chart.width} class="axis" />
              <rect x="0" y="0" width={chart.width} height={chart.height} class="hit" role="presentation"
                onpointerdown={(event) => press(event, group.key, chart)} onpointermove={(event) => slide(event, chart)}
                onpointerup={(event) => void release(event, chart)} onpointercancel={() => drag = null} />
            </svg>
            {#snippet footer()}<XAxis lo={chart.start} hi={chart.end} scale={{kind: "clock"}} />{/snippet}
            </ValueAxis>
            {#if grid?.step && grid.slots > 1}
              <label class="scrub">시점 고르기
                <input type="range" min="0" max={grid.slots - 1}
                  value={picked && grid.step ? Math.min(grid.slots - 1, Math.floor((picked.from - grid.from) / grid.step)) : grid.slots - 1}
                  oninput={(event) => scrub(Number(event.currentTarget.value))} />
              </label>
            {/if}
            {#if picked}{@render pick(group, picked, unit)}{/if}
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
              {@const unit = latestUnit(trend, item)}
              <li>{sourceLabel(sources, item.sourceId)}{item.pointId ? " · 측정 위치 " + item.pointId : ""}
                · {recorded(item.eventAt)} · {item.usable ? num(item.value, "값 없음") + (item.value !== null && unit ? " " + unit : "") : "품질 문제로 표시 안 함"}
                · 원본 품질 {QUALITY[item.quality] ?? item.quality}</li>
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
  .axis-note { color: var(--color-ink-muted); font-size: var(--font-small); margin: var(--space-3) 0 0; }
  .hit { fill: transparent; cursor: crosshair; touch-action: pan-y; }
  .picked { fill: var(--color-focus); fill-opacity: 0.16; }
  .dragging { fill: var(--color-action); fill-opacity: 0.12; }
  .cursor { stroke: var(--color-focus); stroke-width: 2; stroke-dasharray: 5 4; }
  .dot { stroke: var(--color-focus); stroke-width: 10; stroke-linecap: round; }
  .scrub { font-weight: 400; margin-top: var(--space-3); }
  .scrub input { width: 100%; padding: 0; border: 0; }
  .zoomed { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2) var(--space-4); margin: var(--space-3) 0 0; }
  .pick { margin-top: var(--space-4); padding: var(--space-4); border: 1px solid var(--color-border);
    border-left: 4px solid var(--color-focus); border-radius: var(--radius-control); display: grid; gap: var(--space-2); }
  .pick p { margin: 0; overflow-wrap: anywhere; }
  .pick-head { display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--space-1) var(--space-4); align-items: baseline; }
  .pick-head h4 { margin: 0; font-size: var(--font-body); }
  .pick-head span { color: var(--color-ink-muted); font-size: var(--font-small); }
  .pick-value { font-size: var(--font-section); }
  .pick-value span { font-size: var(--font-small); color: var(--color-ink-muted); }
  .pick-actions { display: flex; flex-wrap: wrap; gap: var(--space-2); margin-top: var(--space-2); align-items: center; }
  .quiet { background: transparent; }
  details { margin-top: var(--space-3); }
  summary { cursor: pointer; color: var(--color-action); font-weight: 650; }
  .table-scroll { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-size: var(--font-small); margin-top: var(--space-3); }
  caption { text-align: left; color: var(--color-ink-muted); padding-block: var(--space-2); }
  th, td { border-bottom: 1px solid var(--color-border); padding: var(--space-2); text-align: left; }
  .latest { margin-top: var(--space-6); }
  .latest li { margin-block: var(--space-2); overflow-wrap: anywhere; }
</style>
