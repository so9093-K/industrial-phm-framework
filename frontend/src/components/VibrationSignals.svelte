<script lang="ts">
  import {exposeAnalysis} from "../analysis-readout.svelte";
  import {onMount,untrack} from "svelte";
  import {preferredFeature} from "../acquisition-profile";
  import {measure} from "../chart-axis";
  import ValueAxis from "./ValueAxis.svelte";
  import XAxis from "./XAxis.svelte";
  import {elapsedText, measurementScale, measurementLabel} from "../time-axis";
  import {loadAcquisitionOptions, type AcquisitionOptions} from "../acquisition-outlook";
  import {readAcquisitionTrend, trendChart, type AcquisitionTrend} from "../acquisition-trend";
  import StatusNotice from "./StatusNotice.svelte";
  import {plainLabel} from "../change-story";
  import {measurementLinks} from "../measurement-links";

  /** A vibration asset's measurements: one feature of each stored waveform, in acquisition order.
   * The raw waveform of one measurement opens from the anomaly tab. */
  let {assetId,selectedPosition=null,onPosition}: {assetId: string;selectedPosition?:number|null;onPosition?:(at:number)=>void} = $props();
  let options: AcquisitionOptions | null = $state(null);
  let trend: AcquisitionTrend | null = $state(null);
  let listState: "loading" | "ready" | "empty" | "failed" = $state("loading");
  let trendState: "loading" | "ready" | "failed" = $state("loading");
  let feature = $state(new URLSearchParams(location.search).get("vibration_feature") ?? "");
  // One measurement picked on the chart (or handed over from another screen) stays chosen across features.
  const handed = Number(new URLSearchParams(location.search).get("vibration_at"));
  let chosen: number | null = $state(Number.isSafeInteger(handed) && handed > 0 ? handed : null);
  $effect(()=>{
    const at=selectedPosition,data=trend;
    if(at===null||!data?.points.some(point=>point.ordinal===at))return;
    untrack(()=>{if(chosen!==at)choose(at);});
  });
  let request: AbortController | null = null;
  const chart = $derived.by(() => { const current: AcquisitionTrend | null = trend; return current ? trendChart(current) : null; });
  const latest = $derived.by(() => { const current: AcquisitionTrend | null = trend; return current?.points.at(-1) ?? null; });
  const chosenPoint = $derived.by(() => {
    const current: AcquisitionTrend | null = trend, ordinal: number | null = chosen;
    return current && ordinal !== null ? current.points.find((point) => point.ordinal === ordinal) ?? null : null;
  });
  const chosenMark = $derived(chart && chosen !== null ? chart.marks.find((mark) => mark.ordinal === chosen) ?? null : null);
  function pick(event: MouseEvent) {
    if (!chart?.marks.length) return;
    const box = (event.currentTarget as Element).getBoundingClientRect();
    const x = (event.clientX - box.left) / Math.max(box.width, 1) * chart.width;
    choose(chart.marks.reduce((best, mark) => Math.abs(mark.x - x) < Math.abs(best.x - x) ? mark : best).ordinal);
  }
  function choose(ordinal: number) {
    chosen = ordinal;
    onPosition?.(ordinal);
    const url = new URL(location.href);
    url.searchParams.set("vibration_at", String(ordinal));
    history.replaceState(history.state, "", url);
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
      if (!pending.signal.aborted) {
        trend = value; trendState = "ready";
        if(chosen===null){const at=selectedPosition??value.points.at(-1)?.ordinal;if(at!=null&&options&&at>=options.first&&at<=options.last)choose(at);}
        const current=new URL(location.href);
        if(value.bindingId)current.searchParams.set("acquisition_binding",value.bindingId);
        history.replaceState(history.state,"",current);
      }
    } catch { if (!pending.signal.aborted) trendState = "failed"; }
  }
  onMount(() => {
    const pending = new AbortController();
    void loadAcquisitionOptions(assetId, pending.signal).then((value) => {
      if (pending.signal.aborted) return;
      if (!value || !value.features.length) { listState = "empty"; return; }
      options = value;
      if (!value.features.some((item) => item.id === feature))
        feature = preferredFeature(value.features)!.id;
      listState = "ready";
      void load();
    }).catch(() => { if (!pending.signal.aborted) listState = "failed"; });
    return () => { pending.abort(); request?.abort(); };
  });

  exposeAnalysis(() => {
    if (trendState !== "ready" || !trend?.points.length) return null;
    const point = chosenPoint ?? latest;
    return {
      "진동 특징 추이": trend.label,
      "조회 범위": `${trend.points[0].ordinal}–${trend.points.at(-1)?.ordinal}번째 측정`,
      ...(point ? {[chosenPoint ? "선택한 진동 측정" : "마지막 진동 측정"]: measurementLabel(point.ordinal, trend.periodSeconds) + " · " + measure(point.value, trend.unit)} : {}),
    };
  });
</script>

<section class="ui-panel" aria-labelledby="vibration-signals-title">
  <h2 class="visually-hidden" id="vibration-signals-title">진동 측정</h2>
  {#if listState === "loading"}
    <StatusNotice message="진동 측정 기록을 확인하고 있습니다." />
  {:else if listState === "failed"}
    <StatusNotice kind="failure" title="진동 측정 기록을 불러오지 못했습니다" message="잠시 후 다시 열어 주세요." />
  {:else if listState === "empty" || !options}
    <StatusNotice kind="uncertain" message="아직 분석된 진동 측정이 없습니다. 측정이 들어오고 분석되면 여기에 보입니다." />
  {:else}
    <div class="analysis-workspace signal-workspace"><div class="signal-toolbar" aria-label="특징 선택과 이어서 보기">

    <label class="field">진동 신호
      <select value={feature} onchange={(event) => { feature = event.currentTarget.value; void load(); }}>
        {#each options.features as item (item.id)}<option value={item.id}>{item.label}</option>{/each}
      </select>
    </label>
    <p class="context">{options.first}~{options.last}번째 측정 · 분석 {options.count}회{options.recordedPeriod === null ? "" : " · 기록된 측정 간격 " + elapsedText(options.recordedPeriod)}</p>
    </div>
    <div class="analysis-body">
    {#if trendState === "loading"}
      <StatusNotice message="고른 특징의 기록을 불러오고 있습니다." />
    {:else if trendState === "failed" || !trend}
      <StatusNotice kind="uncertain" message="고른 특징의 기록을 불러오지 못했습니다. 다른 특징을 고르거나 다시 열어 주세요." />
    {:else}
      <h3 class="series-title">{plainLabel(trend.label,feature)}</h3>
      {#if chart}
        {@const period = trend.periodSeconds}
        {@const axisNote = chart.first + "~" + chart.last + "번째 측정" + (period ? " · 기록 시작 후 경과 시간 · 측정 간격 " + elapsedText(period) : "")}
        <div class="signal-reading" class:has-selection={chosen!==null}><div>
        <figure class="chart">
          <p class="axis-note">최고 {measure(chart.high, trend.unit)} · 최저 {measure(chart.low, trend.unit)}{trend.sampled ? " · 측정이 많아 고르게 " + trend.points.length + "개를 그림" : ""}</p>
          <ValueAxis ticks={chart.ticks} height={chart.height} unit={trend.unit}>
          <svg viewBox={"0 0 " + chart.width + " " + chart.height} preserveAspectRatio="none" role="img"
            aria-label={trend.label + " · " + chart.first + "번째부터 " + chart.last + "번째 측정까지"}>
            {#each chart.ticks as tick (tick.value)}<line x1="0" x2={chart.width} y1={tick.y} y2={tick.y} class="grid" />{/each}
            <path d={chart.line} class="line" />
            {#each chart.marks as mark (mark.ordinal)}
              <circle cx={mark.x} cy={mark.y} r="3" class="point">
                <title>{measurementLabel(mark.ordinal, period)} · {measure(mark.value, trend.unit)}</title>
              </circle>
            {/each}
            {#if chosenMark}<line x1={chosenMark.x} x2={chosenMark.x} y1="0" y2={chart.height} class="cursor" />
              <line x1={chosenMark.x} x2={chosenMark.x} y1={chosenMark.y} y2={chosenMark.y} class="dot" />{/if}
            <path d={"M0 0 V" + chart.height + " H" + chart.width} class="axis" />
            <rect x="0" y="0" width={chart.width} height={chart.height} class="hit" onclick={pick} role="presentation" />
          </svg>
          {#snippet footer()}<XAxis lo={chart.first} hi={chart.last} scale={measurementScale(period)} note={axisNote} />{/snippet}
          </ValueAxis>
        </figure>
        <label class="scrub">측정 고르기
          <input type="range" min="0" max={chart.marks.length - 1}
            value={Math.max(0, chart.marks.findIndex((mark) => mark.ordinal === chosen))}
            oninput={(event) => choose(chart.marks[Number(event.currentTarget.value)].ordinal)} />
        </label>
        </div>
        {#if chosen !== null && options}
          <aside class="reading-inspector"><section class="pick" aria-label="선택한 측정">
            <h3 title={measurementLabel(chosen,period)}>{chosen}번째 측정</h3>
            <p class="reading-value">{chosenPoint ? measure(chosenPoint.value, trend.unit) : "값은 원본에서 확인"}</p>
            {#if latest && latest.ordinal !== chosen}<p class="context">마지막 저장 · {latest.ordinal}번째 · {measure(latest.value,trend.unit)}</p>{/if}
            <p class="pick-links">
              {#each measurementLinks(assetId, chosen, {first: options.first, last: options.last, feature, bindingId: trend.bindingId}, "trend") as item (item.key)}
                <a href={item.href}>{item.label} →</a>
              {/each}
            </p>
          </section></aside>
        {/if}
        </div>
      {/if}
    {/if}
    </div></div>
  {/if}
</section>

<style>
  .signal-workspace{grid-template-columns:minmax(0,1fr);gap:var(--space-3)}
  .signal-toolbar{grid-column:1;grid-row:1;display:flex;align-items:center;flex-wrap:wrap;gap:var(--space-3) var(--space-5)}
  .signal-toolbar .field{min-width:240px;margin:0}
  .signal-toolbar>.context{font-size:var(--font-small);margin:0}

  .context { color: var(--color-ink-muted); overflow-wrap: anywhere; }
  .field { display: grid; gap: var(--space-2); font-weight: 650; font-size: var(--font-small); margin-block: 0 var(--space-3); }
  .series-title { margin: 0; font-size: var(--font-section); }
  select { width: 100%; min-width: 0; padding: var(--space-3); border: 1px solid var(--color-border);
    border-radius: var(--radius-control); background: var(--color-surface); color: var(--color-ink); }
  .chart { margin: var(--space-3) 0 0; min-width: 0; }
  .chart svg { display: block; width: 100%; height: 220px;  }
  .chart path { vector-effect: non-scaling-stroke; }
  .chart .axis { fill: none; stroke: var(--color-border); stroke-width: 2; }
  .chart .line { fill: none; stroke: var(--color-action); stroke-width: 1.75; }
  .point { fill: var(--color-action); }
  .axis-note { color: var(--color-ink-muted); font-size: var(--font-small); margin: 0; }
  .grid{stroke:var(--color-border);stroke-width:1;opacity:.7;vector-effect:non-scaling-stroke}
  .hit { fill: transparent; cursor: crosshair; }
  .cursor { stroke: var(--color-focus); stroke-width: 2; stroke-dasharray: 5 4; vector-effect: non-scaling-stroke; }
  .dot { stroke: var(--color-focus); stroke-width: 10; stroke-linecap: round; vector-effect: non-scaling-stroke; }
  .scrub { display: grid; gap: var(--space-1); font-size: var(--font-small); margin-top: var(--space-3); }
  .scrub input { width: 100%; }
  .pick { display:grid; gap:var(--space-2); }
  .pick h3 { margin: 0; font-size: var(--font-body); }
  .pick p { margin: 0; overflow-wrap: anywhere; }
  .pick-links { display:grid; gap:var(--space-3); font-size:var(--font-small); }

  .signal-reading{display:grid;grid-template-columns:minmax(0,1fr);gap:var(--space-5);align-items:start}.signal-reading.has-selection{grid-template-columns:minmax(0,1fr) 260px}.signal-reading>div{min-width:0}
  .reading-inspector{border-left:1px solid var(--color-border);padding-left:var(--space-4);min-width:0}.reading-value{font-size:var(--font-result);font-weight:700}
  @media(max-width:1000px){.signal-reading.has-selection{grid-template-columns:minmax(0,1fr)}.reading-inspector{border-left:0;border-top:1px solid var(--color-border);padding:var(--space-3) 0 0}}
</style>
