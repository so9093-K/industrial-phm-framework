<script lang="ts">
  import {onMount} from "svelte";
  import {num} from "../format";
  import {assetTabUrl} from "../routes";
  import {loadAcquisitionOptions, type AcquisitionOptions} from "../acquisition-outlook";
  import {readAcquisitionTrend, trendChart, type AcquisitionTrend} from "../acquisition-trend";
  import StatusNotice from "./StatusNotice.svelte";

  /** A vibration asset's measurements: one feature of each stored waveform, in acquisition order.
   * The raw waveform of one measurement opens from the anomaly tab. */
  let {assetId}: {assetId: string} = $props();
  let options: AcquisitionOptions | null = $state(null);
  let trend: AcquisitionTrend | null = $state(null);
  let listState: "loading" | "ready" | "empty" | "failed" = $state("loading");
  let trendState: "loading" | "ready" | "failed" = $state("loading");
  let feature = $state(new URLSearchParams(location.search).get("vibration_feature") ?? "");
  let request: AbortController | null = null;
  const chart = $derived.by(() => { const current: AcquisitionTrend | null = trend; return current ? trendChart(current) : null; });
  const latest = $derived.by(() => { const current: AcquisitionTrend | null = trend; return current?.points.at(-1) ?? null; });

  function link(tab: "change" | "outlook", key: string): string {
    const url = new URL(assetTabUrl(assetId, tab, tab === "change" ? "compare" : null, "vibration"), location.origin);
    url.searchParams.set(key, feature);
    return url.pathname + url.search;
  }
  async function load() {
    request?.abort();
    const pending = new AbortController(); request = pending;
    trendState = "loading"; trend = null;
    const url = new URL(location.href);
    url.searchParams.set("vibration_feature", feature);
    history.replaceState(history.state, "", url);
    try {
      const value = await readAcquisitionTrend(assetId, feature, pending.signal);
      if (!pending.signal.aborted) { trend = value; trendState = "ready"; }
    } catch { if (!pending.signal.aborted) trendState = "failed"; }
  }
  onMount(() => {
    const pending = new AbortController();
    void loadAcquisitionOptions(assetId, pending.signal).then((value) => {
      if (pending.signal.aborted) return;
      if (!value || !value.features.length) { listState = "empty"; return; }
      options = value;
      if (!value.features.some((item) => item.id === feature))
        feature = (value.features.find((item) => item.id.endsWith("Horizontal_vibration_signals.rms")) ?? value.features[0]).id;
      listState = "ready";
      void load();
    }).catch(() => { if (!pending.signal.aborted) listState = "failed"; });
    return () => { pending.abort(); request?.abort(); };
  });
</script>

<section class="ui-panel" aria-labelledby="vibration-signals-title">
  <h2 id="vibration-signals-title">진동 측정</h2>
  <p class="context">측정마다 저장된 파형에서 뽑은 진동 특징을 측정 순서대로 봅니다.</p>
  {#if listState === "loading"}
    <StatusNotice message="진동 측정 기록을 확인하고 있습니다." />
  {:else if listState === "failed"}
    <StatusNotice kind="failure" title="진동 측정 기록을 불러오지 못했습니다" message="잠시 후 다시 열어 주세요." />
  {:else if listState === "empty" || !options}
    <StatusNotice kind="uncertain" message="아직 분석된 진동 측정이 없습니다. 측정이 들어오고 분석되면 여기에 보입니다." />
  {:else}
    <label class="field">진동 특징
      <select value={feature} onchange={(event) => { feature = event.currentTarget.value; void load(); }}>
        {#each options.features as item (item.id)}<option value={item.id}>{item.label}</option>{/each}
      </select>
    </label>
    <p class="links">이 특징으로 이어서 보기
      <a href={link("change", "acquisition_feature")}>두 기간 비교 →</a>
      <a href={link("outlook", "acq_forecast_feature")}>기준 도달 전망 →</a>
      <a href={assetTabUrl(assetId, "anomaly", "model")}>측정별 원본 파형·모델 점수 →</a></p>
    <p class="context">측정 #{options.first}~#{options.last} · 분석 {options.count}회{options.recordedPeriod === null ? "" : " · 기록된 측정 간격 " + num(options.recordedPeriod) + "초"}</p>
    {#if trendState === "loading"}
      <StatusNotice message="고른 특징의 기록을 불러오고 있습니다." />
    {:else if trendState === "failed" || !trend}
      <StatusNotice kind="uncertain" message="고른 특징의 기록을 불러오지 못했습니다. 다른 특징을 고르거나 다시 열어 주세요." />
    {:else}
      {#if latest}<p class="headline">마지막 측정 #{latest.ordinal} · <strong>{num(latest.value)}</strong></p>{/if}
      {#if chart}
        <figure class="chart">
          <p class="axis-note">최고 {num(chart.high)} · 최저 {num(chart.low)}{trend.sampled ? " · 측정이 많아 고르게 " + trend.points.length + "개를 그림" : ""}</p>
          <svg viewBox={"0 0 " + chart.width + " " + chart.height} preserveAspectRatio="none" role="img"
            aria-label={trend.label + " · 측정 #" + chart.first + "부터 #" + chart.last + "까지"}>
            <path d={chart.line} class="line" />
            <path d={"M0 0 V" + chart.height + " H" + chart.width} class="axis" />
          </svg>
          <p class="axis-time"><span>측정 #{chart.first}</span><span>측정 #{chart.last}</span></p>
        </figure>
      {/if}
    {/if}
  {/if}
</section>

<style>
  .context { color: var(--color-ink-muted); overflow-wrap: anywhere; }
  .field { display: grid; gap: var(--space-2); font-weight: 650; font-size: var(--font-small); max-width: 420px; margin-block: var(--space-4); }
  select { width: 100%; min-width: 0; padding: var(--space-3); border: 1px solid var(--color-border);
    border-radius: var(--radius-control); background: var(--color-surface); color: var(--color-ink); }
  .links { display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-4); align-items: baseline;
    color: var(--color-ink-muted); font-size: var(--font-small); }
  .headline { font-size: var(--font-section); margin: var(--space-4) 0 0; }
  .chart { margin: var(--space-3) 0 0; min-width: 0; }
  .chart svg { display: block; width: 100%; height: 220px; margin-top: var(--space-2); }
  .chart path { vector-effect: non-scaling-stroke; }
  .chart .axis { fill: none; stroke: var(--color-border); stroke-width: 2; }
  .chart .line { fill: none; stroke: var(--color-action); stroke-width: 1.75; }
  .axis-note, .axis-time { color: var(--color-ink-muted); font-size: var(--font-small); margin: 0; }
  .axis-time { display: flex; justify-content: space-between; margin-top: var(--space-1); }
</style>
