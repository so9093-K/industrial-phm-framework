<script lang="ts">
  import type {FoundInterval} from "../record-findings";
  import {overviewChart} from "../record-overview";
  import ValueAxis from "./ValueAxis.svelte";
  import XAxis from "./XAxis.svelte";
  /** 확대한 그래프 아래의 기록 전체. 변화가 기록 어디에 있었고, 비슷한 일이 또 있었는지 본다. */
  let {finding, condition = null, height = 96}: {finding: FoundInterval; condition?: string | null; height?: number} = $props();
  const kind = $derived(finding.overviewKind ?? "all");
  const trace = $derived(finding.trace ?? []);
  const chart = $derived(overviewChart(finding.overview ?? [], kind, {
    baseline: finding.baseline,
    change: {from: finding.start, to: finding.end},
    window: trace.length ? {from: trace[0].at, to: new Date(Date.parse(trace.at(-1)!.at) + (finding.bucketSeconds ?? 0) * 1000).toISOString()} : null,
    record: finding.context?.record ?? null,
  }, 1000, height));
  const judgedName = $derived(kind === "level" ? (condition ? condition + " 중의 값" : "같은 운전 수준의 값") : "정지를 뺀 값");
</script>
{#if chart}
  <figure class="strip" aria-label={finding.label + " 기록 전체와 변화의 위치"}>
    <ValueAxis ticks={chart.ticks} {height} unit={finding.unit}>
      <svg viewBox={"0 0 " + chart.width + " " + chart.height} preserveAspectRatio="none" role="img" style:height={height + "px"}
        aria-label={"기록 전체의 구간별 평균. 회색 띠는 초기(기록 처음 30%), 주황 띠는 변화 구간, 테두리는 위 그래프에서 확대한 범위입니다."}>
        {#each chart.ticks as tick (tick.value)}<line x1="0" x2={chart.width} y1={tick.y} y2={tick.y} class="grid" />{/each}
        {#if chart.bands.baseline}<rect x={chart.bands.baseline.x} width={chart.bands.baseline.width} y="0" height={chart.height} class="baseline" />{/if}
        {#each chart.ranges as range, i (i)}<line x1={range.x} x2={range.x} y1={range.low} y2={range.high} class="range" />{/each}
        {#if chart.all}<path d={chart.all} class="all" />{/if}
        <path d={chart.judged} class="judged" />
        {#each chart.dots as dot, i (i)}<line x1={dot.x} x2={dot.x} y1={dot.y} y2={dot.y} class="dot" />{/each}
        <rect x={chart.bands.change.x} width={chart.bands.change.width} y="0" height={chart.height} class="change" />
        {#if chart.bands.window}<rect x={chart.bands.window.x} width={chart.bands.window.width} y="1" height={chart.height - 2} class="window" />{/if}
      </svg>
      {#snippet footer()}<XAxis lo={chart.start} hi={chart.end} scale={{kind: "clock"}} />{/snippet}
    </ValueAxis>
    <figcaption>
      <span><i class="key baseline"></i>초기(기록 처음 30%)</span>
      <span><i class="key change"></i>변화 구간</span>
      {#if chart.bands.window}<span><i class="key window"></i>위 그래프의 범위</span>{/if}
      {#if kind !== "all"}<span><i class="key judged"></i>{judgedName}</span><span><i class="key all"></i>모든 운전 상태의 평균</span>{/if}
    </figcaption>
  </figure>
{/if}
<style>
  .strip { margin: 0; min-width: 0; }
  svg { display: block; width: 100%; }
  svg line, svg path, svg rect { vector-effect: non-scaling-stroke; }
  .grid { stroke: var(--color-border); stroke-width: 1; opacity: .6; }
  .baseline { fill: var(--color-ink-muted); fill-opacity: .1; }
  .range { stroke: var(--color-chart-primary, var(--color-action)); stroke-opacity: .22; stroke-width: 2; }
  .all { fill: none; stroke: var(--color-ink-muted); stroke-width: 1; stroke-opacity: .6; }
  .judged { fill: none; stroke: var(--color-chart-primary, var(--color-action)); stroke-width: 1.5; stroke-linejoin: round; }
  .dot { stroke: var(--color-chart-primary, var(--color-action)); stroke-width: 4; stroke-linecap: round; }
  .change { fill: var(--color-caution-ink); fill-opacity: .35; }
  .window { fill: none; stroke: var(--color-ink); stroke-width: 1.5; stroke-dasharray: 4 3; }
  figcaption { display: flex; flex-wrap: wrap; gap: var(--space-1) var(--space-4); margin-top: var(--space-1); font-size: var(--font-small); color: var(--color-ink-muted); }
  figcaption span { display: inline-flex; align-items: center; gap: var(--space-1); }
  .key { display: inline-block; width: 14px; height: 10px; border-radius: 2px; }
  .key.baseline { background: var(--color-ink-muted); opacity: .25; }
  .key.change { background: var(--color-caution-ink); opacity: .5; }
  .key.window { border: 1.5px dashed var(--color-ink); background: none; }
  .key.judged { height: 0; border-top: 2px solid var(--color-chart-primary, var(--color-action)); border-radius: 0; }
  .key.all { height: 0; border-top: 1px solid var(--color-ink-muted); border-radius: 0; }
</style>
