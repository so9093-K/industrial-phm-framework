<script lang="ts">
  import ValueAxis from "./ValueAxis.svelte";
  import PlotCursor from "./PlotCursor.svelte";
  import XAxis from "./XAxis.svelte";
  import {niceTicks, yTicks} from "../chart-axis";
  import type {XScale} from "../time-axis";
  import {relationValue} from "../analysis-messages";

  type Period = "a" | "b";
  type Point = {x: number; y: number; at: number; label: string};
  type Selection = {period: Period; index: number};
  let {groups, bounds, xLabel, yLabel, timeScale, picked = null, band = null, onPick}: {
    groups: {period: Period; label: string; points: Point[]}[];
    bounds: {xmin: number; xmax: number; ymin: number; ymax: number};
    xLabel: string; yLabel: string; timeScale: XScale;
    picked?: Selection | null; band?: {low: number; high: number} | null;
    onPick: (period: Period, index: number) => void;
  } = $props();

  type Zoom = Period | "band" | null;
  let zoom = $state<Zoom>(null);
  let width = $state(800);
  let timeWidth = $state(800);
  const height = 280;
  const timeHeight = 40;
  // Rounded tick positions already express the chart's scale. Preserve their decimals on zoom.
  const tickFormat = new Intl.NumberFormat("ko-KR", {maximumSignificantDigits:12});
  const formatTick = (value: number) => tickFormat.format(value);
  const colors = {a: "var(--color-reference-line)", b: "var(--color-action)"};
  const visible = $derived(groups.filter(group => zoom === null || zoom === "band" || group.period === zoom)
    .map(group => ({...group, entries: group.points.map((point, index) => ({point, index}))
      .filter(({point}) => zoom !== "band" || !band || (point.x >= band.low && point.x <= band.high))})));
  const scale = $derived.by(() => {
    const points = zoom === null ? [] : visible.flatMap(group => group.entries.map(({point}) => point));
    const own = points.length ? {
      xmin: zoom === "band" && band ? band.low : Math.min(...points.map(point => point.x)),
      xmax: zoom === "band" && band ? band.high : Math.max(...points.map(point => point.x)),
      ymin: Math.min(...points.map(point => point.y)), ymax: Math.max(...points.map(point => point.y)),
    } : bounds;
    const xp = (own.xmax - own.xmin || Math.abs(own.xmin) * .05 || 1) * .06;
    const yp = (own.ymax - own.ymin || Math.abs(own.ymin) * .05 || 1) * .06;
    return {lo: own.xmin - xp, hi: own.xmax + xp, bottom: own.ymin - yp, top: own.ymax + yp};
  });
  const x = (value: number) => width * (value - scale.lo) / (scale.hi - scale.lo);
  const y = (value: number) => height - height * (value - scale.bottom) / (scale.top - scale.bottom);
  const ticks = $derived(yTicks(scale.bottom, scale.top, 0, height, 5));
  const selected = $derived(groups.find(group => group.period === picked?.period));
  const point = $derived(picked ? selected?.points[picked.index] : null);
  const navigated = $derived(visible.find(group => group.period === picked?.period && group.entries.length)
    ?? visible.find(group => group.period === "b" && group.entries.length) ?? visible.find(group => group.entries.length));
  const index = $derived(navigated?.entries.findIndex(item => picked?.period === navigated?.period && item.index === picked?.index) ?? -1);
  const pointVisible = $derived(picked !== null && index >= 0);

  const ordered = $derived(visible.flatMap(group => group.entries.map(({point, index}) => ({point, period: group.period, index})))
    .sort((left, right) => left.point.at - right.point.at));
  const times = $derived([...new Set(ordered.map(item => item.point.at))]);
  const first = $derived(times[0] ?? 0);
  const last = $derived(times.at(-1) ?? first);
  const timeX = (at: number) => timeWidth * (at - first) / Math.max(1, last - first);
  function timeDots(key: "x" | "y", period: Period) {
    const min = key === "x" ? scale.lo : scale.bottom, max = key === "x" ? scale.hi : scale.top;
    const start = key === "x" ? 0 : 20;
    return ordered.filter(item => item.period === period).map(({point}) => {
      const level = start + 17 - (point[key] - min) / (max - min) * 14;
      return "M" + timeX(point.at).toFixed(1) + " " + level.toFixed(1) + "h0";
    }).join(" ");
  }

  function chooseZoom(period: Zoom) {
    zoom = period;
    if (period && navigated && !pointVisible) onPick(navigated.period, navigated.entries[0].index);
  }
  function pick(event: MouseEvent) {
    const box = (event.currentTarget as Element).getBoundingClientRect();
    let nearest: Selection | null = null;
    let distance = Infinity;
    for (const group of visible) {
      for (const {index, point} of group.entries) {
        const dx = x(point.x) - (event.clientX - box.left), dy = y(point.y) - (event.clientY - box.top);
        if (dx * dx + dy * dy < distance) {
          distance = dx * dx + dy * dy;
          nearest = {period: group.period, index};
        }
      }
    }
    if (nearest) onPick(nearest.period, nearest.index);
  }
  function pickTime(key: number) {
    const item = ordered.find(row => row.point.at === key && row.period === picked?.period)
      ?? ordered.find(row => row.point.at === key);
    if (item) onPick(item.period, item.index);
  }
</script>

<figure class="relation-plot">
  <header class="plot-toolbar">
    <div class="legend">
      {#each visible as group (group.period)}
        <span><i class:a={group.period === "a"} style:--series={colors[group.period]}></i>{group.label}</span>
      {/each}
      {#if band && zoom === null}<span class="band-key"><i></i>비교한 {xLabel} 범위</span>{/if}
    </div>
    <div class="zoom" role="group" aria-label="관계 그래프 확대">
      <button type="button" aria-pressed={zoom === null} onclick={() => chooseZoom(null)}>전체 비교</button>
      {#if band}<button type="button" aria-pressed={zoom === "band"} onclick={() => chooseZoom("band")}>공통 범위 확대</button>{/if}
      {#each groups as group (group.period)}
        <button type="button" aria-pressed={zoom === group.period} onclick={() => chooseZoom(group.period)}>{group.label} 확대</button>
      {/each}
    </div>
  </header>
  <p class="axis-name">{yLabel}</p>
  <ValueAxis {ticks} {height} unit={null} format={formatTick}>
    <div bind:clientWidth={width}>
      <svg class="scatter" viewBox={"0 0 " + width + " " + height} role="img" aria-label={xLabel + "과 " + yLabel + "의 전후 분포 비교"}>
        {#if band && zoom === null}
          <rect x={x(band.low)} y="0" width={Math.max(2, x(band.high) - x(band.low))} {height} class="band"/>
        {/if}
        {#each ticks as tick (tick.value)}<line x1="0" x2={width} y1={tick.y} y2={tick.y} class="grid"/>{/each}
        {#each niceTicks(scale.lo, scale.hi) as tick (tick)}<line x1={x(tick)} x2={x(tick)} y1="0" y2={height} class="grid"/>{/each}
        {#each visible as group (group.period)}
          {#each group.entries as {point, index} (index)}
            <circle cx={x(point.x)} cy={y(point.y)} r={group.period === "a" ? 3.5 : 3}
              fill={group.period === "a" ? "var(--color-surface)" : colors[group.period]}
              stroke={colors[group.period]} stroke-width={group.period === "a" ? 1.2 : 0} opacity=".72">
              <title>{group.label} · {point.label} · {xLabel} {relationValue(point.x)} · {yLabel} {relationValue(point.y)}</title>
            </circle>
          {/each}
        {/each}
        {#if point && pointVisible}
          <circle cx={x(point.x)} cy={y(point.y)} r="7" class="picked"/>
        {/if}
        <rect x="0" y="0" {width} {height} class="hit" role="presentation" onclick={pick}/>
      </svg>
    </div>
    {#snippet footer()}<XAxis lo={scale.lo} hi={scale.hi} scale={{kind:"value"}} note={xLabel} format={formatTick}/>{/snippet}
  </ValueAxis>
  {#if last > first}
    <div class="time-strip">
      <div class="time-label"><span>{xLabel}</span><span>{yLabel}</span></div>
      <div class="time-plot" bind:clientWidth={timeWidth}>
        <PlotCursor positions={times} value={point?.at ?? null} lo={first} hi={last}
          label="시간축의 측정 선택" formatValue={at => ordered.find(item => item.point.at === at)?.point.label ?? ""}
          onSelect={pickTime}>
        <svg viewBox={"0 0 " + timeWidth + " " + timeHeight} role="img" aria-label="두 신호를 시간순으로 본 측정 추이">
          <line x1="0" x2={timeWidth} y1="20" y2="20" class="grid"/>
          {#each visible as group (group.period)}
            <path class="time-dots" stroke={colors[group.period]} d={timeDots("x", group.period)}/>
            <path class="time-dots" stroke={colors[group.period]} d={timeDots("y", group.period)}/>
          {/each}
          {#if point && point.at >= first && point.at <= last}
            <line x1={timeX(point.at)} x2={timeX(point.at)} y1="0" y2={timeHeight} class="time-picked"/>
          {/if}
        </svg>
        </PlotCursor>
        <XAxis lo={first} hi={last} scale={timeScale}/>
      </div>
    </div>
  {/if}
  <footer class="navigation">
    {#if navigated}
      <label>측정 선택
        <select aria-label="점을 선택할 기간" value={navigated.period} onchange={event => {
          const period = event.currentTarget.value as Period;
          if (zoom !== null && zoom !== "band") zoom = period;
          const first = visible.find(group => group.period === period)?.entries[0];
          if (first) onPick(period, first.index);
        }}>{#each groups as group (group.period)}<option value={group.period}>{group.label}</option>{/each}</select>
      </label>
      <button type="button" aria-label="이전 측정" disabled={index <= 0} onclick={() => onPick(navigated.period, navigated.entries[index - 1].index)}>←</button>
      <button type="button" aria-label="다음 측정" disabled={index >= navigated.entries.length - 1} onclick={() => onPick(navigated.period, navigated.entries[index + 1].index)}>→</button>
      <output>{pointVisible ? point?.label : "그래프에서 시점 선택"}</output>
    {/if}
  </footer>
</figure>

<style>
  .relation-plot { margin:0; min-width:0; }
  .plot-toolbar,.legend,.zoom,.navigation { display:flex; align-items:center; flex-wrap:wrap; gap:8px; }
  .plot-toolbar { justify-content:space-between; margin-bottom:10px; }
  .legend { gap:8px 16px; font-size:var(--font-small); }
  .legend span { display:inline-flex; gap:6px; align-items:center; }
  .legend i { width:8px; height:8px; border-radius:50%; background:var(--series); border:1.5px solid var(--series); }
  .legend i.a { background:var(--color-surface); }
  .legend .band-key i { width:14px; border:0; border-radius:1px; background:var(--color-surface-selected); }
  .zoom button {
    border:0; background:transparent; color:var(--color-ink-muted); border-radius:5px;
    padding:5px 8px; font:inherit; font-size:var(--font-label); cursor:pointer;
  }
  .zoom button[aria-pressed="true"] { background:var(--color-surface-selected); color:var(--color-action); font-weight:650; }
  .axis-name { margin:0 0 8px; font-size:var(--font-label); color:var(--color-ink-muted); }
  svg { display:block; width:100%; overflow:hidden; }
  .scatter { height:280px; }
  .grid { stroke:var(--color-border); stroke-width:1; }
  .band { fill:var(--color-surface-selected); }
  .picked { fill:none; stroke:var(--color-ink); stroke-width:2; }
  .hit { fill:transparent; cursor:crosshair; }
  .time-strip { display:grid; grid-template-columns:minmax(44px,auto) minmax(0,1fr); gap:8px; margin-top:8px; }
  .time-label { display:grid; grid-template-rows:20px 20px; align-items:center; font-size:var(--font-label); color:var(--color-ink-muted); }
  .time-plot { min-width:0; }
  .time-plot svg { height:40px; background:var(--color-surface-selected); border-radius:4px; }
  .time-dots { fill:none; stroke-width:2.25; stroke-linecap:round; }
  .time-picked { stroke:var(--color-ink); stroke-width:1.5; }
  .navigation { margin-top:8px; font-size:var(--font-label); color:var(--color-ink-muted); }
  .navigation label { display:flex; align-items:center; gap:6px; }
  .navigation select,.navigation button {
    min-height:30px; padding:3px 8px; border:1px solid var(--color-control-border); border-radius:5px;
    color:var(--color-ink); background:var(--color-surface); font:inherit;
  }
  .navigation output { margin-left:auto; font-variant-numeric:tabular-nums; }
</style>
