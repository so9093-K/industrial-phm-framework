<script lang="ts">
  import XAxis from "./XAxis.svelte";
  import {bandName, bandRange, percent, type Operation} from "../record-findings";
  let {operation}: {operation: Operation} = $props();
  const baseline = $derived(operation.baseline);
  // Running levels in one hue from light (low current) to dark (high current); a stop in grey.
  const RAMP = ["#b3dbe5", "#7cbccd", "#4a9bb3", "#1f7690", "#0b5068"];
  const STOPPED = "#c3ccd2";
  const colors = $derived([STOPPED, ...operation.levels.map((_, index, all) =>
    RAMP[all.length === 1 ? 2 : Math.round(index * (RAMP.length - 1) / (all.length - 1))] ?? RAMP[RAMP.length - 1])]);
  const bands = $derived(operation.levels.length + 1);
  const start = $derived(operation.timeline.length ? Date.parse(operation.timeline[0].at) : 0);
  const end = $derived(operation.timeline.length
    ? Date.parse(operation.timeline[operation.timeline.length - 1].at) + operation.bucketSeconds * 1000 : 1);
  // At most 200 drawn columns; each sums the buckets that start inside it.
  const columns = $derived.by(() => {
    const count = Math.min(200, operation.timeline.length), span = Math.max(1, end - start);
    const merged = new Map<number, number[]>();
    for (const bucket of operation.timeline) {
      const index = Math.min(count - 1, Math.floor((Date.parse(bucket.at) - start) / span * count));
      const sum = merged.get(index) ?? new Array<number>(bands).fill(0);
      bucket.counts.forEach((value, band) => { sum[band] += value; });
      merged.set(index, sum);
    }
    return [...merged].map(([index, counts]) => ({index, from: start + span * index / count,
      to: start + span * (index + 1) / count, counts, total: counts.reduce((a, b) => a + b, 0)}));
  });
  const x = (at: number) => (at - start) / Math.max(1, end - start) * 600;
  const shown = $derived(([["record", "기록 전체"], ["baseline", "처음 30%"], ["after", "이후"]] as const)
    .filter(([key]) => operation.shares[key]));
  let hovered: number | null = $state(null);
  const picked = $derived(columns.find(column => column.index === hovered) ?? null);
  function hover(event: PointerEvent) {
    const box = (event.currentTarget as SVGElement).getBoundingClientRect();
    const count = Math.min(200, operation.timeline.length);
    hovered = Math.floor((event.clientX - box.left) / Math.max(1, box.width) * count);
  }
  const clock = (at: number) => new Date(at).toLocaleString("ko-KR", {timeZone: "Asia/Seoul",
    month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false});
</script>

<section class="operation" aria-labelledby={"operation-" + operation.key}>
  <h3 id={"operation-" + operation.key}>운전 상태 <small>{operation.label} 기준</small></h3>
  <div class="table">
  <table>
    <thead><tr><th scope="col">상태</th><th scope="col">전류</th>{#each shown as [, name] (name)}<th scope="col">{name}</th>{/each}</tr></thead>
    <tbody>
      {#each colors as color, band (band)}
        <tr><th scope="row"><span class="swatch" style={"background:" + color}></span>{bandName(operation, band)}</th>
          <td>{bandRange(operation, band)}</td>
          {#each shown as [key] (key)}<td>{percent(operation.shares[key]![band])}</td>{/each}</tr>
      {/each}
    </tbody>
  </table>
  </div>
  {#if columns.length}
    <figure>
      <div class="plot">
        <svg viewBox="0 0 600 96" preserveAspectRatio="none" role="img" onpointermove={hover} onpointerleave={() => hovered = null}
          aria-label={"시간대별 운전 상태 비율 · " + clock(start) + " ~ " + clock(end)}>
          {#each columns as column (column.index)}
            {@const left = x(column.from)}
            {@const width = Math.max(0.6, x(column.to) - left)}
            {#each column.counts as count, band (band)}
              {@const below = column.counts.slice(0, band).reduce((a, b) => a + b, 0)}
              {#if count}<rect x={left} width={width + 0.4} y={96 - (below + count) / column.total * 96}
                height={count / column.total * 96} fill={colors[band]} />{/if}
            {/each}
          {/each}
          {#if baseline}<line class="cut" x1={x(Date.parse(baseline.to))} x2={x(Date.parse(baseline.to))} y1="0" y2="96" />{/if}
          {#if picked}<rect class="focus" x={x(picked.from)} width={Math.max(1, x(picked.to) - x(picked.from))} y="0" height="96" />{/if}
        </svg>
        {#if picked}
          <div class="tip" style={"left:" + Math.min(78, Math.max(0, x(picked.from) / 6)) + "%"} aria-hidden="true">
            <strong>{clock(picked.from)} ~ {clock(picked.to)}</strong>
            {#each picked.counts as count, band (band)}{#if count}<span><i class="swatch" style={"background:" + colors[band]}></i>{bandName(operation, band)} {percent(count / picked.total)}</span>{/if}{/each}
          </div>
        {/if}
      </div>
      <XAxis lo={start} hi={end} scale={{kind: "clock", zone: "Asia/Seoul"}}
        note={"세로 · 시간대별 운전 상태 비율" + (baseline ? " · 점선 · 기록 처음 30%의 끝" : "")} />
    </figure>
  {/if}
  {#if operation.excluded}<p class="note">설비가 대부분 정지해 있던 시간은 신호 변화 판단에서 뺐습니다.</p>{/if}
  <details class="note"><summary>운전 상태를 나눈 방식</summary>
    <p>{operation.label}이 {bandRange(operation, 0)}이면 정지로 봅니다. 운전 중 값은 이 기록에서 전류가 자주 머문 값을 찾아 나누었고, 각 상태의 전류 값은 그 범위의 중앙값입니다.</p>
  </details>
</section>

<style>
  .operation { display: grid; gap: var(--space-2); margin-bottom: var(--space-3); padding: var(--space-3) var(--space-4); border: 1px solid var(--color-border); border-radius: var(--radius-control); }
  h3 { margin: 0; font-size: var(--font-body); }
  h3 small { font-weight: 400; color: var(--color-ink-muted); font-size: var(--font-small); }
  .table { overflow-x: auto; min-width: 0; }
  table { border-collapse: collapse; font-size: var(--font-small); font-variant-numeric: tabular-nums; width: max-content; }
  th, td { padding: var(--space-1) var(--space-2) var(--space-1) 0; text-align: right; white-space: nowrap; }
  th:first-child, td:nth-child(2) { text-align: left; }
  thead th { color: var(--color-ink-muted); font-weight: 400; }
  tbody th { font-weight: 650; }
  .swatch { display: inline-block; width: 10px; height: 10px; margin-right: var(--space-1); border-radius: 2px; vertical-align: baseline; }
  figure { margin: 0; min-width: 0; }
  .plot { position: relative; }
  svg { display: block; width: 100%; height: 96px; border-radius: 4px; background: var(--color-surface-selected); }
  .cut { stroke: var(--color-ink); stroke-width: 1.5; stroke-dasharray: 4 3; vector-effect: non-scaling-stroke; }
  .focus { fill: none; stroke: var(--color-ink); stroke-width: 1.5; vector-effect: non-scaling-stroke; }
  .tip { position: absolute; top: calc(100% + 4px); z-index: 1; display: grid; gap: 2px; padding: var(--space-2); background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-control); font-size: var(--font-small); pointer-events: none; white-space: nowrap; box-shadow: 0 2px 8px rgb(0 0 0 / 0.12); }
  .tip .swatch { width: 8px; height: 8px; }
  .note { margin: 0; color: var(--color-ink-muted); font-size: var(--font-small); }
  summary { cursor: pointer; }
</style>
