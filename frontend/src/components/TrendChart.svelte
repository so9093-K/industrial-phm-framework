<script lang="ts">
  import {measure, yTicks} from "../chart-axis";
  import {tracePath} from "../asset-overview";
  import {SERIES_COLORS, type FleetChange, type FleetGroup, type FleetSeries} from "../fleet-observation";
  import {measurementScale} from "../time-axis";
  import {nearestPosition} from "../plot-selection";
  import ValueAxis from "./ValueAxis.svelte";
  import XAxis from "./XAxis.svelte";
  import PlotCursor from "./PlotCursor.svelte";
  /** 추이 그래프의 공통 규칙: 같은 단위의 신호 묶음을 한 눈금에 겹치고, 찾은 변화는 옅은 구간과 시작선으로,
   * 처음 수준은 회색 점선으로 표시한다. 오른쪽 끝은 마지막 측정(모니터링 중이면 모니터링 시점)이다.
   * 포인터를 올린 자리(cursor)는 부모가 값 줄에 읽어 쓴다. 공유 가로축을 위에 따로 그릴 때는 axis=false.
   * 조사 화면은 처음 범위(band: 변화로 판단하지 않는 범위)와 같은 운전 수준의 값(marks)을 더 그린다.
   * spread는 첫 계열의 칸마다 최저~최고: 두 수준을 오가는 값은 평균선만으로는 실제로 없던 값처럼 보인다. */
  let {group, series, lo, hi, changes, reference = null, band = null, marks = [], spread = [], live = false, height = 150, axis = true,
    colors = SERIES_COLORS, guide = null, endLabel = false, selectedRange = false, halves = null, picked = $bindable(null), cursor = $bindable(null), onPick, onHover}: {
    group: FleetGroup; series: FleetSeries[]; lo: number; hi: number; changes: FleetChange[]; reference?: number | null;
    band?: {low: number; high: number} | null; marks?: {x: number; value: number}[]; colors?: string[];
    spread?: {x: number; low: number; high: number; join: boolean}[];
    live?: boolean; height?: number; axis?: boolean; picked?: number | null; cursor?: number | null; onPick?: (at: number) => void; onHover?: (at: number | null) => void;
    /** 같은 시간축의 다른 그래프에서 가리킨 자리(그 세로선을 여기에도 그린다). */
    guide?: number | null;
    endLabel?: boolean;
    selectedRange?: boolean;
    /** 변화 구간 앞 절반·뒤 절반에 움직인 양. 가운데 점선과 각 절반 위의 값으로 빨라지는지 보인다. */
    halves?: {from: number; to: number; change: number}[] | null} = $props();
  const W = 1000;
  let hover: number | null = $state(null);
  const values = $derived(series.flatMap(row => row.points.map(point => point.value)));
  // 처음 범위와 같은 운전 수준의 값도 같은 눈금 안에 들어와야 한다.
  const extra = $derived([...(reference === null ? [] : [reference]), ...(band ? [band.low, band.high] : []), ...marks.map(point => point.value),
    ...spread.flatMap(point => [point.low, point.high])]);
  // 최저~최고 띠: 이어진 칸끼리 한 덩어리로(측정이 끊긴 곳에서는 띠도 끊는다).
  const spreadPath = $derived.by(() => {
    const runs: (typeof spread)[] = [];
    for (const point of spread) if (point.join && runs.length) runs.at(-1)!.push(point); else runs.push([point]);
    return runs.map(run => "M" + run.map(point => x(point.x).toFixed(1) + " " + y(point.high).toFixed(1)).join("L")
      + "L" + [...run].reverse().map(point => x(point.x).toFixed(1) + " " + y(point.low).toFixed(1)).join("L") + "Z").join(" ");
  });
  const low = $derived(values.length ? Math.min(...values, ...extra) : 0);
  const high = $derived(values.length ? Math.max(...values, ...extra) : 1);
  const pad = $derived(high > low ? (high - low) * 0.1 : Math.max(Math.abs(low) * 0.02, 0.5));
  const span = $derived(Math.max(hi - lo, group.axis === "time" ? 1000 : 1));
  const x = (n: number) => (n - lo) / span * W;
  const y = (n: number) => height - 4 - (n - low + pad) / (high - low + 2 * pad) * (height - 8);
  const ticks = $derived(values.length ? yTicks(low - pad, high + pad, 4, height - 4, 3) : []);
  const positions = $derived(series.find(row => row.key === group.focus)?.points.map(point => point.x) ?? series[0]?.points.map(point => point.x) ?? []);
  const scale = $derived(group.axis === "acquisition" ? measurementScale(group.periodSeconds) : {kind: "clock" as const});
  const shown = $derived(changes.filter(change => change.from <= lo + span && change.to >= lo));
  $effect(() => { cursor = hover ?? picked; });
  function move(event: PointerEvent) {
    if (event.buttons) return;
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    hover = nearestPosition(positions, lo + Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)) * span);
    onHover?.(hover);
  }
  function leave() { hover = null; onHover?.(null); }
  const at = $derived(hover ?? guide ?? picked);
  const last = $derived(series.map((row, index) => ({row, index, point: row.points.at(-1)})).filter(item => item.point));
  // 처음 수준 점선은 그 설비의 기록이 있는 곳까지만(공유 축에서 짧은 기록 뒤로 이어지지 않게).
  const end = $derived(Math.max(...series.map(row => row.points.at(-1)?.x ?? lo)));
  const pct = (n: number) => Math.max(0, Math.min(100, x(n) / W * 100));
  // 두 절반이 모두 그래프 폭의 6% 넘게 보일 때만 적는다. 좁으면 값이 서로 겹쳐 읽히지 않는다.
  const paced = $derived(halves && halves.every(half => pct(half.to) - pct(half.from) >= 6) ? halves : null);
</script>

{#if values.length}
  <ValueAxis {ticks} {height} unit={group.unit}>
    <div class="plot" role="presentation" onpointermove={move} onpointerleave={leave}>
      <PlotCursor {positions} value={picked} {lo} hi={lo + span} label={group.label + " 측정 시점 선택"} onSelect={value => { picked = value; onPick?.(value); }}>
        <svg viewBox={"0 0 " + W + " " + height} preserveAspectRatio="none" role="img" style:height={height + "px"}
          aria-label={series.map(row => row.label).join(" · ") + " 실측 추이" + (shown.length ? " · 특이사항 " + shown.length + "곳" : "")}>
          {#each ticks as tick (tick.value)}<line x1="0" x2={W} y1={tick.y} y2={tick.y} class="grid"/>{/each}
          {#each shown as change (change.key + change.from)}
            {@const start = Math.max(0, x(change.from))}
            <rect class="change" class:pinned={selectedRange} x={start} width={Math.max(3, Math.min(W, x(change.to)) - start)} {height}/>
          {/each}
          {#if band}<rect class="band" x="0" width={Math.min(W, x(end))} y={y(band.high)} height={Math.max(1, y(band.low) - y(band.high))}/>{/if}
          {#if reference !== null}<line class="reference" x1="0" x2={Math.min(W, x(end))} y1={y(reference)} y2={y(reference)}/>{/if}
          {#if spread.length}<path class="spread" d={spreadPath} style:fill={colors[0]}/>{/if}
          {#each series as row, index (row.key)}
            <path d={tracePath(row.points.map(point => ({x: x(point.x), y: y(point.value), join: point.join})))} stroke={colors[index % colors.length]}/>
          {/each}
          <!-- 늘어나는 그림에서도 둥근 점이 되도록 길이 0의 선에 둥근 끝을 쓴다. -->
          {#if marks.length}<path class="marks" stroke={colors[0]} d={marks.filter(point => point.x >= lo && point.x <= lo + span).map(point => "M" + x(point.x).toFixed(1) + " " + y(point.value).toFixed(1) + "h0").join(" ")}/>{/if}
          {#each shown as change (change.key + change.from)}{#if change.from >= lo}<line class="onset" x1={x(change.from)} x2={x(change.from)} y1="0" y2={height}/>{/if}{/each}
          {#if paced}<line class="half" x1={x(paced[1].from)} x2={x(paced[1].from)} y1="0" y2={height}/>{/if}
          {#if at !== null}<line class="cursor" x1={x(at)} x2={x(at)} y1="0" y2={height}/>{/if}
        </svg>
      </PlotCursor>
      {#each shown as change (change.key + change.from)}{#if change.from >= lo}<span class="mark" style:left={pct(change.from) + "%"}></span>{/if}{/each}
      <!-- 커지는 변화는 앞 절반 값을 위에, 뒤 절반 값을 아래에 적는다(앞에서 낮고 뒤에서 높은 선을 가리지 않게). 작아지는 변화는 반대. -->
      {#if paced}{#each paced as half, i (half.from)}
        <span class="half-label" style:left={(pct(half.from) + pct(half.to)) / 2 + "%"}>
          {(half.change > 0 ? "+" : "") + measure(half.change, group.unit, 3)}</span>{/each}{/if}
      {#each last as item (item.row.key)}
        <span class="dot" class:live style:left={pct(item.point!.x) + "%"} style:top={y(item.point!.value) / height * 100 + "%"}
          style:--dot={colors[item.index % colors.length]}></span>
        {#if endLabel && !live && item.row.key === group.focus && !hover}
          <span class="end-label" class:at-start={pct(item.point!.x) < 33}
            style:left={pct(item.point!.x) + "%"} style:top={y(item.point!.value) / height * 100 + "%"}
            style:--dot={colors[item.index % colors.length]}>{measure(item.point!.value, group.unit, group.unit === "V" ? 4 : 3)}</span>
        {/if}
      {/each}
    </div>
    {#snippet footer()}{#if axis}<XAxis {lo} hi={lo + span} {scale}/>{/if}{/snippet}
  </ValueAxis>
{:else}<div class="empty" style:height={height + "px"}>{live ? "이 시점까지 끝난 측정 구간이 아직 없습니다" : "표시할 측정이 없습니다"}</div>{/if}

<style>
  .plot{position:relative}
  svg{display:block;width:100%;overflow:hidden}
  .grid{stroke:#e3eaee;stroke-width:1}
  .change{fill:var(--color-change-fill)}
  .change.pinned{stroke:var(--color-change-line);stroke-width:1.5;vector-effect:non-scaling-stroke;fill:color-mix(in srgb,var(--color-change-fill) 86%,var(--color-change-line))}
  .onset{stroke:var(--color-change-line);stroke-width:1.5}
  .reference{stroke:var(--color-reference-line);stroke-width:1;stroke-dasharray:5 4}
  .band{fill:var(--color-reference-line);opacity:.1}
  .spread{stroke:none;opacity:.22}
  .marks{fill:none;stroke-width:6;stroke-linecap:round;opacity:.55}
  path{fill:none;stroke-width:1.6;stroke-linejoin:round}
  line,path{vector-effect:non-scaling-stroke}
  .cursor{stroke:var(--color-ink);stroke-dasharray:3 3;stroke-width:1}
  .half{stroke:var(--color-change-line);stroke-dasharray:2 3;stroke-width:1.5}
  .half-label{position:absolute;top:6px;transform:translateX(-50%);padding:1px 5px;border-radius:3px;background:var(--color-surface);color:var(--color-ink);font-size:12px;font-weight:650;font-variant-numeric:tabular-nums;white-space:nowrap;pointer-events:none}
  .mark{position:absolute;top:-6px;width:0;height:0;margin-left:-5px;border:5px solid transparent;border-top:6px solid var(--color-change-mark);pointer-events:none}
  .dot{position:absolute;width:8px;height:8px;margin:-4px 0 0 -4px;border-radius:50%;background:var(--dot);box-shadow:0 0 0 2px var(--color-surface);pointer-events:none}
  .end-label{position:absolute;transform:translate(calc(-100% - 8px),-100%);padding:1px 4px;border-radius:3px;background:var(--color-surface);color:var(--color-ink);border-bottom:2px solid var(--dot);white-space:nowrap;font-size:12px;font-weight:650;pointer-events:none}
  .end-label.at-start{transform:translate(8px,-100%)}
  .dot.live::after{content:"";position:absolute;inset:-4px;border-radius:50%;border:2px solid var(--dot);animation:pulse 1.4s ease-out infinite}
  @keyframes pulse{from{transform:scale(.6);opacity:.9}to{transform:scale(1.8);opacity:0}}
  @media (prefers-reduced-motion:reduce){.dot.live::after{animation:none}}
  .empty{display:grid;place-items:center;font-size:var(--font-label);color:var(--color-ink-muted);background:repeating-linear-gradient(0deg,transparent 0 24px,#eef2f4 24px 25px)}
</style>
