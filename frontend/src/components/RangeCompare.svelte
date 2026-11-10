<script lang="ts">
  import {num} from "../format";
  import XAxis from "./XAxis.svelte";
  import {niceTicks} from "../chart-axis";
  import type {Histogram} from "../comparison";

  /** Period A and B on one value axis. Above, how each period's values spread over the same equal
   * bins, as a share of its own measurements, so two groups of values show where a median would
   * sit between them. Below, the 5–95% range as a line, the middle half (25–75%) as a box and the
   * median as a mark. Counts and quantiles are the stored ones; nothing is estimated here. */
  type Props = {a: number[] | null; b: number[] | null; histogram?: Histogram | null; unit: string | null; label: string};
  let {a, b, histogram = null, unit, label}: Props = $props();
  const rows = $derived([{name: "기간 A", q: a, kind: "a"}, {name: "기간 B", q: b, kind: "b"}]
    .filter((row): row is {name: string; q: number[]; kind: string} => row.q !== null && row.q.length === 5));
  const HEIGHT = 120;
  const shares = $derived.by(() => {
    if (!histogram) return [];
    return ([["a", histogram.a], ["b", histogram.b]] as const).flatMap(([kind, counts]) => {
      const total = counts?.reduce((sum, count) => sum + count, 0) ?? 0;
      return counts && total ? [{kind, values: counts.map((count) => count / total)}] : [];
    });
  });
  const scale = $derived.by(() => {
    const values = [...rows.flatMap((row) => [row.q[0], row.q[4]]), ...(shares.length && histogram ? [histogram.low, histogram.high] : [])];
    const low = Math.min(...values), high = Math.max(...values);
    const pad = low === high ? Math.max(Math.abs(low) * 0.05, 1) : (high - low) * (shares.length ? 0.02 : 0.05);
    return {low: low - pad, high: high + pad, x: (value: number) => ((value - (low - pad)) / ((high + pad) - (low - pad))) * 800};
  });
  const bins = $derived.by(() => {
    if (!histogram || !shares.length) return [];
    const count = shares[0].values.length, width = (histogram.high - histogram.low) / count;
    return Array.from({length: count}, (_, index) => ({index, low: histogram.low + index * width, high: histogram.low + (index + 1) * width}));
  });
  const top = $derived(Math.max(...shares.flatMap((side) => side.values), 0));
  const ticks = $derived(niceTicks(0, top * 100, 3).filter((tick) => tick > 0));
  const ceiling = $derived(Math.max(top * 100, ticks.at(-1) ?? 0) || 1);
  const y = (share: number) => HEIGHT - (share * 100 / ceiling) * (HEIGHT - 6);
  function outline(values: number[]): string {
    const path = values.map((share, index) => {
      const x0 = scale.x(bins[index].low), x1 = scale.x(bins[index].high);
      return (index ? "L" : "M" + x0 + " " + HEIGHT + " L") + x0 + " " + y(share) + " L" + x1 + " " + y(share);
    }).join(" ");
    return path + " L" + scale.x(bins.at(-1)!.high) + " " + HEIGHT + " Z";
  }
  const suffix = $derived(unit ? " " + unit : "");
  const percentOf = (side: {values: number[]} | undefined, index: number) =>
    side ? (side.values[index] * 100).toLocaleString("ko-KR", {maximumFractionDigits: 1}) + "%" : "없음";
</script>

{#if rows.length || shares.length}
  <figure class="ranges">
    {#if shares.length}
      <div class="share-axis" aria-hidden="true" style={"height:" + HEIGHT + "px"}>
        <span class="name">측정 비율</span>
        {#each ticks as tick (tick)}<span class="tick" style={"top:" + y(tick / 100) + "px"}>{tick}%</span>{/each}
      </div>
      <svg class="shape" viewBox={"0 0 800 " + HEIGHT} style={"height:" + HEIGHT + "px"} preserveAspectRatio="none" role="img"
        aria-label={label + " 값 분포 · 같은 폭 " + bins.length + "개 구간에 든 측정 비율. 기간 A는 회색 면, 기간 B는 진한 선."}>
        {#each ticks as tick (tick)}<line x1="0" x2="800" y1={y(tick / 100)} y2={y(tick / 100)} class="grid" />{/each}
        {#each shares as side (side.kind)}<path d={outline(side.values)} class={"area " + side.kind} />{/each}
        <line x1="0" x2="800" y1={HEIGHT} y2={HEIGHT} class="base" />
        {#each bins as bin (bin.index)}
          <rect x={scale.x(bin.low)} width={Math.max(1, scale.x(bin.high) - scale.x(bin.low))} y="0" height={HEIGHT} class="hit">
            <title>{num(bin.low)}~{num(bin.high)}{suffix} · 기간 A {percentOf(shares.find((side) => side.kind === "a"), bin.index)} · 기간 B {percentOf(shares.find((side) => side.kind === "b"), bin.index)}</title>
          </rect>
        {/each}
      </svg>
    {/if}
    {#if rows.length}
      <div class="row-labels" aria-hidden="true">{#each rows as row (row.kind)}<span>{row.name}</span>{/each}</div>
      <svg class="boxes" viewBox={"0 0 800 " + rows.length * 40} style={"height:" + rows.length * 44 + "px"} preserveAspectRatio="none" role="img"
        aria-label={label + " · 기간별 5~95% 범위와 가운데 50%, 중앙값. " + rows.map((row) => row.name + " 중앙값 " + num(row.q[2]) + suffix).join(", ")}>
        {#each niceTicks(scale.low, scale.high) as tick (tick)}<line x1={scale.x(tick)} x2={scale.x(tick)} y1="0" y2={rows.length * 40} class="grid" />{/each}
        {#each rows as row, i (row.kind)}
          <line x1={scale.x(row.q[0])} x2={scale.x(row.q[4])} y1={i * 40 + 20} y2={i * 40 + 20} class={"whisker " + row.kind} />
          <rect x={scale.x(row.q[1])} y={i * 40 + 8} width={Math.max(2, scale.x(row.q[3]) - scale.x(row.q[1]))} height="24" class={"box " + row.kind} />
          <line x1={scale.x(row.q[2])} x2={scale.x(row.q[2])} y1={i * 40 + 5} y2={i * 40 + 35} class="median" />
        {/each}
      </svg>
    {/if}
    <span></span>
    <XAxis lo={scale.low} hi={scale.high} scale={{kind:"value"}} note={"가로축 · " + label + (unit ? " · " + unit : "")} />
    <figcaption>
      {#each rows as row (row.kind)}
        <span><i class={"key " + row.kind}></i>{row.name} · 중앙값 {num(row.q[2])}{suffix} · 가운데 50% {num(row.q[1])}~{num(row.q[3])}</span>
      {/each}
      {#if shares.length}<span>위 그림 · 두 기간의 값 전체를 같은 폭 {bins.length}개 구간으로 나눠, 각 기간 측정 중 몇 %가 그 구간에 있었는지 그렸습니다. 구간에 마우스를 올리면 비율이 보입니다.</span>{/if}
    </figcaption>
  </figure>
{/if}

<style>
  .ranges { margin: var(--space-3) 0; min-width: 0; display:grid;grid-template-columns:auto minmax(0,1fr);column-gap:var(--space-2);row-gap:var(--space-1); }
  .row-labels{display:grid;grid-auto-rows:44px;align-items:center;font-size:var(--font-small);font-weight:650}
  .share-axis{position:relative;min-width:3.5rem;font-size:12px;color:var(--color-ink-muted);font-variant-numeric:tabular-nums}
  .share-axis .name{position:absolute;left:0;bottom:0;font-size:var(--font-small);font-weight:650;color:var(--color-ink)}
  .share-axis .tick{position:absolute;right:0;transform:translateY(-50%);line-height:1;white-space:nowrap}
  .grid{stroke:var(--color-border);stroke-width:1}
  svg { display: block; width: 100%; min-width: 0; }
  svg line, svg rect, svg path { vector-effect: non-scaling-stroke; }
  .base { stroke: var(--color-ink-muted); stroke-width: 1; }
  /* A, the reference, is a filled grey shape; B is an accent line over it, so the two read apart
     by form as well as colour where they overlap. */
  .area { stroke-linejoin: round; }
  .area.a { fill: var(--color-ink-muted); fill-opacity: 0.22; stroke: var(--color-ink-muted); stroke-opacity: 0.5; stroke-width: 1; }
  .area.b { fill: none; stroke: var(--color-action); stroke-width: 2.5; }
  .hit { fill: transparent; }
  .hit:hover { fill: var(--color-ink); fill-opacity: 0.06; }
  .whisker { stroke-width: 2; }
  .whisker.a, .box.a { stroke: var(--color-ink-muted); }
  .whisker.b, .box.b { stroke: var(--color-action); }
  .box.a { fill: var(--color-ink-muted); fill-opacity: 0.22; }
  .box.b { fill: var(--color-surface); stroke-width: 2.5; }
  .median { stroke: var(--color-ink); stroke-width: 2; }
  figcaption { grid-column:1/-1;display: grid; gap: var(--space-1); margin-top: var(--space-2); color: var(--color-ink-muted); font-size: var(--font-small); }
  .key { display: inline-block; width: 14px; height: 10px; border-radius: 2px; margin-inline-end: var(--space-1); vertical-align: middle; }
  .key.a { background: color-mix(in srgb, var(--color-ink-muted) 22%, var(--color-surface)); border: 1px solid var(--color-ink-muted); }
  .key.b { background: var(--color-surface); border: 2.5px solid var(--color-action); }
</style>
