<script lang="ts">
  import {num} from "../format";
  import XAxis from "./XAxis.svelte";
  import {niceTicks} from "../chart-axis";
  import {newValues, type Histogram} from "../comparison";

  /** Period A and B on one value axis. Above, how each period's values spread over the same equal
   * bins, as a share of its own measurements, so two groups of values show where a median would
   * sit between them. Below, the 5–95% range as a line, the middle half (25–75%) as a box and the
   * median as a mark. Counts and quantiles are the stored ones; nothing is estimated here.
   * names: 모니터링에서 열면 '초기'·'변화 구간', 직접 고른 기간이면 '기간 A'·'기간 B'. */
  type Props = {a: number[] | null; b: number[] | null; histogram?: Histogram | null; unit: string | null; label: string;
    names?: {a: string; b: string}; compact?: boolean};
  let {a, b, histogram = null, unit, label, names = {a: "기간 A", b: "기간 B"}, compact = false}: Props = $props();
  const rows = $derived([{name: names.a, q: a, kind: "a"}, {name: names.b, q: b, kind: "b"}]
    .filter((row): row is {name: string; q: number[]; kind: string} => row.q !== null && row.q.length === 5));
  const HEIGHT = $derived(compact ? 88 : 120);
  const shares = $derived.by(() => {
    if (!histogram) return [];
    return ([["a", histogram.a], ["b", histogram.b]] as const).flatMap(([kind, counts]) => {
      const total = counts?.reduce((sum, count) => sum + count, 0) ?? 0;
      return counts && total ? [{kind, values: counts.map((count) => count / total)}] : [];
    });
  });
  const boxes = $derived(rows.length > 0 && (!compact || !shares.length));
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
  // 범례 대신 두 분포의 꼭대기에 이름을 붙인다. 서로 가까우면 왼쪽 것은 왼쪽으로, 오른쪽 것은 오른쪽으로 비켜 쓴다.
  const peaks = $derived.by(() => {
    const found = shares.flatMap((side) => {
      const index = side.values.indexOf(Math.max(...side.values)), bin = bins[index];
      return bin ? [{kind: side.kind, name: side.kind === "a" ? names.a : names.b,
        at: scale.x((bin.low + bin.high) / 2) / 8, top: y(side.values[index])}] : [];
    });
    return found.map((peak) => {
      const other = found.find((each) => each.kind !== peak.kind);
      const leftward = peak.at > 88 || (peak.at >= 12 && !!other && peak.at < other.at);
      return {...peak, leftward};
    });
  });
  // B의 대부분은 A와 같은 값에 있는데 일부가 A에 거의 없던 값으로 따로 몰렸으면 그 자리를 칠한다(중앙값이 거의
  // 안 움직여 놓치기 쉬운 경우). B 전체가 옮겨 갔으면 두 모양이 이미 보여 주므로 칠하지 않는다.
  const fresh = $derived.by(() => {
    const found = newValues(histogram);
    if (!found || !histogram?.a || !histogram.b) return null;
    const totalA = histogram.a.reduce((sum, count) => sum + count, 0);
    const common = histogram.b.reduce((sum, count, bin) => sum + (histogram.a![bin] / totalA >= 0.01 ? count : 0), 0);
    return common >= 0.5 * found.total ? found : null;
  });
  const suffix = $derived(unit ? " " + unit : "");
  const percentOf = (side: {values: number[]} | undefined, index: number) =>
    side ? (side.values[index] * 100).toLocaleString("ko-KR", {maximumFractionDigits: 1}) + "%" : "없음";
</script>

{#if rows.length || shares.length}
  <figure class="ranges" class:has-fresh={!!fresh}>
    {#if shares.length}
      <div class="share-axis" aria-hidden="true" style={"height:" + HEIGHT + "px"}>
        <span class="name">측정 비율</span>
        {#each ticks as tick (tick)}<span class="tick" style={"top:" + y(tick / 100) + "px"}>{tick}%</span>{/each}
      </div>
      <div class="plot">
      <svg class="shape" viewBox={"0 0 800 " + HEIGHT} style={"height:" + HEIGHT + "px"} preserveAspectRatio="none" role="img"
        aria-label={label + " 값 분포 · 같은 폭 " + bins.length + "개 구간에 든 측정 비율. " + names.a + "는 회색 면, " + names.b + "는 진한 선."}>
        {#if fresh}<rect x={scale.x(fresh.low)} width={Math.max(2, scale.x(fresh.high) - scale.x(fresh.low))} y="0" height={HEIGHT} class="fresh" />{/if}
        {#each ticks as tick (tick)}<line x1="0" x2="800" y1={y(tick / 100)} y2={y(tick / 100)} class="grid" />{/each}
        {#each shares as side (side.kind)}<path d={outline(side.values)} class={"area " + side.kind} />{/each}
        <line x1="0" x2="800" y1={HEIGHT} y2={HEIGHT} class="base" />
        {#each bins as bin (bin.index)}
          <rect x={scale.x(bin.low)} width={Math.max(1, scale.x(bin.high) - scale.x(bin.low))} y="0" height={HEIGHT} class="hit">
            <title>{num(bin.low)}~{num(bin.high)}{suffix} · {names.a} {percentOf(shares.find((side) => side.kind === "a"), bin.index)} · {names.b} {percentOf(shares.find((side) => side.kind === "b"), bin.index)}</title>
          </rect>
        {/each}
      </svg>
      {#each peaks as peak (peak.kind)}
        <span class={"peak " + peak.kind} class:leftward={peak.leftward} style:left={peak.at + "%"} style:top={peak.top + "px"}>{peak.name}</span>
      {/each}
      {#if fresh}<span class="fresh-tag" class:leftward={scale.x(fresh.low) / 8 > 55} style:left={(scale.x(fresh.low) / 8 > 55 ? scale.x(fresh.high) : scale.x(fresh.low)) / 8 + "%"}>{names.a}에 거의 없던 값 · {names.b} {fresh.total}회 중 {fresh.count}회</span>{/if}
      </div>
    {/if}
    {#if boxes}
      <div class="row-labels" aria-hidden="true">{#each rows as row (row.kind)}<span>{row.name}</span>{/each}</div>
      <svg class="boxes" viewBox={"0 0 800 " + rows.length * 40} style={"height:" + rows.length * 44 + "px"} preserveAspectRatio="none" role="img"
        aria-label={label + " · 기간별 값의 90%가 있던 범위와 가운데 절반, 중앙값. " + rows.map((row) => row.name + " 중앙값 " + num(row.q[2]) + suffix).join(", ")}>
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
    {#if boxes&&!compact}<figcaption>상자는 가운데 절반, 선은 90% 범위, 세로선은 중앙값</figcaption>{/if}
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
  figcaption { grid-column:1/-1; margin-top: var(--space-2); color: var(--color-ink-muted); font-size: var(--font-small); }
  .plot { position: relative; min-width: 0; }
  .ranges.has-fresh { margin-top: var(--space-6); }
  .peak { position: absolute; transform: translate(6px, -2px); font-size: var(--font-label); font-weight: 650; white-space: nowrap; pointer-events: none;
    background: var(--color-surface); padding: 0 3px; border-radius: 3px; }
  .peak.leftward { transform: translate(calc(-100% - 6px), -2px); }
  .peak.a { color: var(--color-ink-muted); }
  .peak.b { color: var(--color-action); }
  .fresh { fill: var(--color-caution-ink); fill-opacity: 0.12; }
  .fresh-tag { position: absolute; bottom: 100%; transform: translateY(-2px); font-size: var(--font-label); font-weight: 650; color: var(--color-caution-ink); white-space: nowrap; pointer-events: none; }
  .fresh-tag.leftward { transform: translate(-100%, -2px); }
</style>
