<script lang="ts">
  import {yTicks} from "../chart-axis";
  import {tracePath} from "../asset-overview";
  import {SERIES_COLORS, type FleetChange, type FleetGroup, type FleetSeries} from "../fleet-observation";
  import {measurementScale} from "../time-axis";
  import {nearestPosition} from "../plot-selection";
  import ValueAxis from "./ValueAxis.svelte";
  import XAxis from "./XAxis.svelte";
  import PlotCursor from "./PlotCursor.svelte";
  /** 관제 화면 한 칸의 그래프: 같은 단위의 묶음 신호를 한 눈금에 겹치고, 찾은 변화 구간을 그 위에 칠한다.
   * 가로축 오른쪽 끝이 지금(또는 재생 위치)이다. */
  let {group, series, lo, hi, changes, live = false, picked = $bindable(null), cursor = $bindable(null)}: {
    group: FleetGroup; series: FleetSeries[]; lo: number; hi: number; changes: FleetChange[]; live?: boolean;
    picked?: number | null; cursor?: number | null} = $props();
  const W = 600, H = 190;
  let hover: number | null = $state(null);
  const values = $derived(series.flatMap(row => row.points.map(point => point.value)));
  const low = $derived(values.length ? Math.min(...values) : 0), high = $derived(values.length ? Math.max(...values) : 1);
  const pad = $derived(high > low ? (high - low) * 0.12 : Math.max(Math.abs(low) * 0.02, 0.5));
  const span = $derived(Math.max(hi - lo, group.axis === "time" ? 1000 : 1));
  const x = (n: number) => (n - lo) / span * W;
  const y = (n: number) => H - 6 - (n - low + pad) / (high - low + 2 * pad) * (H - 12);
  const ticks = $derived(values.length ? yTicks(low - pad, high + pad, 6, H - 6) : []);
  const positions = $derived(series.find(row => row.key === group.focus)?.points.map(point => point.x) ?? series[0]?.points.map(point => point.x) ?? []);
  const scale = $derived(group.axis === "acquisition" ? measurementScale(group.periodSeconds) : {kind: "clock" as const});
  const shown = $derived(changes.filter(change => change.from <= hi && change.to >= lo));
  $effect(() => { cursor = hover ?? picked; });
  function move(event: PointerEvent) {
    if (event.buttons) return;
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    hover = nearestPosition(positions, lo + Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)) * span);
  }
  const at = $derived(hover ?? picked);
  const last = $derived(series.map((row, index) => ({row, index, point: row.points.at(-1)})).filter(item => item.point));
</script>

{#if values.length}
  <ValueAxis {ticks} height={H} unit={group.unit}>
    <div class="plot" role="presentation" onpointermove={move} onpointerleave={() => hover = null}>
      <PlotCursor {positions} value={picked} {lo} hi={lo + span} label={group.label + "에서 조사할 시점 선택"} onSelect={value => picked = value}>
        <svg viewBox={"0 0 " + W + " " + H} preserveAspectRatio="none" role="img"
          aria-label={series.map(row => row.label).join(" · ") + " · 실측 추이" + (shown.length ? "와 찾은 변화 " + shown.length + "곳" : "")}>
          {#each ticks as tick (tick.value)}<line x1="0" x2={W} y1={tick.y} y2={tick.y} class="grid"/>{/each}
          {#each shown as change (change.key + change.from)}
            {@const start = Math.max(0, x(change.from))}
            <rect class="change" x={start} width={Math.max(2, Math.min(W, x(change.to)) - start)} height={H}/>
            {#if change.from >= lo}<line class="onset" x1={start} x2={start} y1="0" y2={H}/>{/if}
          {/each}
          {#each series as row, index (row.key)}
            <path d={tracePath(row.points.map(point => ({x: x(point.x), y: y(point.value), join: point.join})))} stroke={SERIES_COLORS[index % SERIES_COLORS.length]}/>
          {/each}
          {#if at !== null}<line class="cursor" x1={x(at)} x2={x(at)} y1="0" y2={H}/>{/if}
        </svg>
      </PlotCursor>
      {#each last as item (item.row.key)}
        <span class="dot" class:live style:left={x(item.point!.x) / W * 100 + "%"} style:top={y(item.point!.value) / H * 100 + "%"}
          style:--dot={SERIES_COLORS[item.index % SERIES_COLORS.length]}></span>
      {/each}
    </div>
    {#snippet footer()}<XAxis lo={lo} hi={lo + span} {scale}/>{/snippet}
  </ValueAxis>
{:else}<div class="empty">{live ? "재생 위치까지 끝난 측정 구간이 아직 없습니다" : "표시할 측정이 없습니다"}</div>{/if}

<style>
  .plot{position:relative}
  svg{display:block;width:100%;height:190px;overflow:hidden}
  .grid{stroke:var(--color-border);stroke-width:1}
  .change{fill:var(--color-caution-ink);opacity:.12}
  .onset{stroke:var(--color-caution-ink);stroke-width:1.5;opacity:.7}
  path{fill:none;stroke-width:1.75;stroke-linejoin:round}
  line,path{vector-effect:non-scaling-stroke}
  .cursor{stroke:var(--color-ink);stroke-dasharray:3 3;stroke-width:1}
  .dot{position:absolute;width:8px;height:8px;margin:-4px 0 0 -4px;border-radius:50%;background:var(--dot);box-shadow:0 0 0 2px var(--color-surface);pointer-events:none}
  .dot.live::after{content:"";position:absolute;inset:-4px;border-radius:50%;border:2px solid var(--dot);animation:pulse 1.4s ease-out infinite}
  @keyframes pulse{from{transform:scale(.6);opacity:.9}to{transform:scale(1.8);opacity:0}}
  @media (prefers-reduced-motion:reduce){.dot.live::after{animation:none}}
  .empty{display:grid;place-items:center;height:190px;border-bottom:1px solid var(--color-border);font-size:var(--font-small);color:var(--color-ink-muted)}
</style>
