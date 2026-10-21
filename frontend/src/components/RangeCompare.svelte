<script lang="ts">
  import {num} from "../format";
  import XAxis from "./XAxis.svelte";
  import {niceTicks} from "../chart-axis";

  /** Period A and B on one axis: the 5–95% range as a line, the middle half (25–75%) as a
   * box and the median as a mark. Quantiles are the stored ones; nothing is estimated here. */
  type Props = {a: number[] | null; b: number[] | null; unit: string | null; label: string};
  let {a, b, unit, label}: Props = $props();
  const rows = $derived([{name: "기간 A", q: a, kind: "a"}, {name: "기간 B", q: b, kind: "b"}]
    .filter((row): row is {name: string; q: number[]; kind: string} => row.q !== null && row.q.length === 5));
  const scale = $derived.by(() => {
    const values = rows.flatMap((row) => [row.q[0], row.q[4]]);
    const low = Math.min(...values), high = Math.max(...values);
    const pad = low === high ? Math.max(Math.abs(low) * 0.05, 1) : (high - low) * 0.05;
    return {low: low - pad, high: high + pad, x: (value: number) => ((value - (low - pad)) / ((high + pad) - (low - pad))) * 800};
  });
  const suffix = $derived(unit ? " " + unit : "");
</script>

{#if rows.length}
  <figure class="ranges">
    <div class="row-labels" aria-hidden="true">{#each rows as row (row.kind)}<span>{row.name}</span>{/each}</div>
    <div class="plot">
    <svg viewBox={"0 0 800 " + rows.length * 40} style={"height:" + rows.length * 44 + "px"} preserveAspectRatio="none" role="img"
      aria-label={label + " · 기간별 5~95% 범위와 가운데 50%, 중앙값. " + rows.map((row) => row.name + " 중앙값 " + num(row.q[2]) + suffix).join(", ")}>
      {#each niceTicks(scale.low, scale.high) as tick (tick)}<line x1={scale.x(tick)} x2={scale.x(tick)} y1="0" y2={rows.length * 40} class="grid" />{/each}
      {#each rows as row, i (row.kind)}
        <line x1={scale.x(row.q[0])} x2={scale.x(row.q[4])} y1={i * 40 + 20} y2={i * 40 + 20} class={"whisker " + row.kind} />
        <rect x={scale.x(row.q[1])} y={i * 40 + 8} width={Math.max(2, scale.x(row.q[3]) - scale.x(row.q[1]))} height="24" class={"box " + row.kind} />
        <line x1={scale.x(row.q[2])} x2={scale.x(row.q[2])} y1={i * 40 + 5} y2={i * 40 + 35} class="median" />
      {/each}
    </svg>
    <XAxis lo={scale.low} hi={scale.high} scale={{kind:"value"}} note={"가로축 · " + label + " · " + (unit ?? "단위 미확인")} />
    </div>
    <figcaption>
      {#each rows as row (row.kind)}
        <span><i class={"key " + row.kind}></i>{row.name} · 중앙값 {num(row.q[2])}{suffix} · 가운데 50% {num(row.q[1])}~{num(row.q[3])}</span>
      {/each}
    </figcaption>
  </figure>
{/if}

<style>
  .ranges { margin: var(--space-3) 0; min-width: 0; display:grid;grid-template-columns:auto minmax(0,1fr);gap:var(--space-2); }
  .row-labels{display:grid;grid-auto-rows:44px;align-items:center;font-size:var(--font-small);font-weight:650}
  .plot{min-width:0}.grid{stroke:var(--color-border);stroke-width:1}
  svg { display: block; width: 100%; height: 88px; }
  svg line, svg rect { vector-effect: non-scaling-stroke; }
  .whisker { stroke-width: 2; }
  .whisker.a, .box.a { stroke: var(--color-ink-muted); }
  .whisker.b, .box.b { stroke: var(--color-action); }
  .box.a { fill: var(--color-border); }
  .box.b { fill: var(--color-action); fill-opacity: 0.25; }
  .median { stroke: var(--color-ink); stroke-width: 2; }
  figcaption { grid-column:1/-1;display: grid; gap: var(--space-1); margin-top: var(--space-2); color: var(--color-ink-muted); font-size: var(--font-small); }
  .key { display: inline-block; width: 14px; height: 10px; border-radius: 2px; margin-inline-end: var(--space-1); vertical-align: middle; }
  .key.a { background: var(--color-border); border: 1px solid var(--color-ink-muted); }
  .key.b { background: var(--color-action); opacity: 0.6; }
</style>
