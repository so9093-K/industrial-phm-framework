<script lang="ts">
  import {onMount} from "svelte";
  import StatusNotice from "./StatusNotice.svelte";
  import {
    groupHistory, pointsForChart, readChannels, readTrend,
    type ChannelList, type HistoryTrend, type RangePreset, type TimeAnchor,
  } from "../history";

  type LoadState = "idle" | "loading" | "ready" | "empty" | "failed";
  type Props = {assetId: string};
  let {assetId}: Props = $props();

  let channelState: LoadState = $state("loading");
  let trendState: LoadState = $state("idle");
  let channels: ChannelList | null = $state(null);
  let trend: HistoryTrend | null = $state(null);
  let error = $state("");
  let selectedChannel = $state(new URLSearchParams(location.search).get("monitor_channel") ?? "");
  let range: RangePreset = $state("1h");
  let anchor: TimeAnchor = $state("latest");
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
  <h2 id="explorer-title">선택 설비의 저장 신호</h2>
  <p class="context">대상 설비: <strong>{assetId}</strong> · 저장된 측정만 표시하며 실시간 수신을 뜻하지 않습니다.</p>
  {#if channelState === "loading"}
    <StatusNotice message="저장된 신호 목록을 확인하고 있습니다." />
  {:else if channelState === "failed"}
    <StatusNotice kind="failure" title="신호 목록 조회 실패" message={error}
      actionLabel="다시 조회" onAction={() => void loadChannels()} />
  {:else if channelState === "empty"}
    <StatusNotice title="저장된 신호가 없습니다"
      message="이 설비에서 확인된 저장 신호가 없습니다. 등록 여부와 실제 수신·저장 근거를 확인하세요."
      actionLabel="데이터 연결 확인" actionHref="/web/#connect" />
  {:else if channels}
    <div class="controls">
      <label for="history-channel">측정 신호
        <select id="history-channel" value={selectedChannel}
          onchange={(event) => changeChannel(event.currentTarget.value)}>
          {#each channels.ids as id (id)}
            <option value={id}>{id}</option>
          {/each}
        </select>
      </label>
      <label for="history-range">조회 기간
        <select id="history-range" value={range}
          onchange={(event) => { range = event.currentTarget.value as RangePreset; void loadTrend(); }}>
          <option value="15m">15분</option><option value="1h">1시간</option>
          <option value="24h">24시간</option><option value="7d">7일</option>
        </select>
      </label>
      <label for="history-anchor">기간 기준
        <select id="history-anchor" value={anchor}
          onchange={(event) => { anchor = event.currentTarget.value as TimeAnchor; void loadTrend(); }}>
          <option value="latest">마지막 저장 기록</option>
          <option value="now">현재 조회 시각</option>
        </select>
      </label>
    </div>
    {#if channels.truncated}
      <StatusNotice kind="uncertain" message="서버 제한으로 신호 목록이 일부만 표시됩니다." />
    {/if}
    {#if trendState === "loading"}
      <StatusNotice message="선택한 신호의 원본 이력과 품질을 조회하고 있습니다." />
    {:else if trendState === "failed"}
      <StatusNotice kind="failure" title="저장 이력 조회 실패" message={error}
        actionLabel="이력 다시 조회" onAction={() => void loadTrend()} />
    {:else if trendState === "empty"}
      <StatusNotice title="이 기간에 표시할 측정이 없습니다"
        message="선택한 기준과 기간에 저장된 측정이 없습니다. 다른 기간이나 신호를 선택하세요." />
    {:else if trend}
      <p class="context">
        기준: {anchor === "latest" ? "마지막 저장 시각" : "조회 시각"}
        · {recorded(trend.startAt)} ~ {recorded(trend.endAt)}
        · 조회 평가: {recorded(trend.assessedAt)}
      </p>
      <p class="explain">
        점은 유효한 저장 측정의 시간 버킷 평균입니다. 결측·품질 오류를 보간하지 않으며,
        서로 다른 소스·측정 지점·측정 의미는 비교 가능한 하나의 선으로 묶지 않습니다.
      </p>
      {#if groups.length === 0}
        <StatusNotice kind="uncertain" message="선택 구간에 시간 버킷은 없지만 별도의 최근 저장값이 있을 수 있습니다." />
      {/if}
      {#each groups as group (group.key)}
        <section class="series" aria-label={"관측 시계열 " + group.sourceId}>
          <h3>{selectedChannel} · {group.sourceId}</h3>
          <p class="context">
            측정 지점 {group.pointId} · 측정 의미 {group.observedProperty ?? "미확인"}
            · 단위 {group.unit ?? "미확인"}
          </p>
          {@const points = pointsForChart(group, trend.startAt, trend.endAt)}
          {#if points.length}
            <svg viewBox="0 0 650 145" role="img"
              aria-label="연속선 없이 유효한 측정 버킷 평균만 표시한 점 그래프. 표시되지 않은 구간은 공백입니다.">
              <path d="M28 14 V120 H628" class="axis" />
              {#each points as point (point.bucket.bucketStart)}
                <circle cx={point.x} cy={point.y} r="4" class="dot">
                  <title>{recorded(point.bucket.bucketStart)} · 평균 {point.bucket.mean}
                    {group.unit ?? "단위 미확인"} · 유효 {point.bucket.usableCount}건</title>
                </circle>
              {/each}
            </svg>
          {:else}
            <p class="context">그릴 수 있는 유효한 평균값이 없습니다. 결측을 0으로 바꾸지 않습니다.</p>
          {/if}
          <details>
            <summary>시간별 평균·결측·원본 품질 확인 ({group.buckets.length}개 버킷)</summary>
            {#if group.buckets.length > 120}
              <p class="context">표에는 최근 120개 버킷만 표시합니다.</p>
            {/if}
            <div class="table-scroll">
              <table>
                <caption>서버 버킷 집계 · 개별 측정값이 아님</caption>
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
          <h3>마지막 저장값 (실시간 값 아님)</h3>
          <ul>
            {#each trend.latest as item (item.sourceId + item.pointId + item.channelId)}
              <li>{item.sourceId} / {item.pointId}
                · {recorded(item.eventAt)} · {item.usable ? (item.value ?? "값 없음") : "화면 표시 제외"}
                · 원본 품질: {item.quality}</li>
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
  svg { display: block; width: 100%; max-height: 185px; overflow: visible; }
  .axis { fill: none; stroke: var(--color-border); stroke-width: 2; }
  .dot { fill: var(--color-action); }
  details { margin-top: var(--space-3); }
  summary { cursor: pointer; color: var(--color-action); font-weight: 650; }
  .table-scroll { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-size: var(--font-small); margin-top: var(--space-3); }
  caption { text-align: left; color: var(--color-ink-muted); padding-block: var(--space-2); }
  th, td { border-bottom: 1px solid var(--color-border); padding: var(--space-2); text-align: left; }
  .latest { margin-top: var(--space-6); }
  .latest li { margin-block: var(--space-2); overflow-wrap: anywhere; }
</style>
