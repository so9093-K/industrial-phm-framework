<script lang="ts">
  import {measure, yTicks} from "../chart-axis";
  import {tracePath} from "../asset-overview";
  import type {XScale} from "../time-axis";
  import {crossedSince, nearestAt, outlookScale, outlookWindow, type OutlookFuture, type OutlookLimits, type OutlookPoint, type OutlookWindow} from "../outlook-view";
  import ValueAxis from "./ValueAxis.svelte";
  import XAxis from "./XAxis.svelte";
  /** 전망 그래프. 관제·조사 화면과 같은 규칙으로 측정(파랑 실선)·처음 수준(회색 점선)·처음 범위(회색 띠)·
   * 조사에서 고른 변화(노란 구간)를 그리고, 그 뒤에 예측(같은 색 점선)과 예측 범위, 관리·종료 기준선,
   * 기준에 닿는 자리를 더한다. 포인터를 올린 자리의 측정값·예측값을 위 줄에서 읽는다. */
  let {history, future, last, baseline = null, change = null, limits, direction = "upper", reach, unit, scale, place, unreliable = false, height = 260}: {
    history: OutlookPoint[]; future: OutlookFuture[]; last: number;
    baseline?: {median: number | null; low: number | null; high: number | null} | null; change?: OutlookWindow | null;
    limits: OutlookLimits; direction?: "upper" | "lower";
    reach: {management: {x: number; sure: boolean; already?: boolean} | null; end: {x: number; sure: boolean; already?: boolean} | null};
    unit: string | null; scale: XScale; place: (x: number) => string; unreliable?: boolean; height?: number} = $props();
  const W = 1000;
  const view = $derived(outlookWindow(history, future, change));
  const shown = $derived(history.filter(point => point.x >= view.from));
  const scaled = $derived(outlookScale([...shown.map(p => p.value), ...future.flatMap(p => [p.estimate, p.lower ?? p.estimate, p.upper ?? p.estimate])], baseline, limits));
  const pad = $derived(Math.max((scaled.high - scaled.low) * .08, Math.abs(scaled.high) * .005, 1e-9));
  const lo = $derived(scaled.low - pad), hi = $derived(scaled.high + pad);
  const x = (n: number) => (n - view.from) / (view.to - view.from) * W;
  const y = (n: number) => height - 4 - (n - lo) / (hi - lo) * (height - 8);
  const ticks = $derived(yTicks(lo, hi, 4, height - 4, 4));
  const pct = (n: number) => Math.max(0, Math.min(100, x(n) / W * 100));
  const measured = $derived(tracePath(shown.map(p => ({x: x(p.x), y: y(p.value), join: true}))));
  const estimate = $derived(tracePath(future.map(p => ({x: x(p.x), y: y(p.estimate), join: true}))));
  const ranged = $derived(future.filter(p => p.lower !== null && p.upper !== null));
  const band = $derived(ranged.length > 1 ? "M" + ranged.map(p => x(p.x).toFixed(1) + " " + y(p.upper!).toFixed(1)).join(" L")
    + " L" + [...ranged].reverse().map(p => x(p.x).toFixed(1) + " " + y(p.lower!).toFixed(1)).join(" L") + " Z" : "");
  const tail = $derived(shown.at(-1));
  const start = $derived(future[0]);
  // 기준선과 닿는 자리. 그래프 밖(세 배 넘게 먼 기준)은 그리지 않고 아래 범례에 값만 적는다.
  // 이미 넘은 기준은 '언제부터 이어서 넘었는지'를 측정에서 찾아 그 자리에 표시한다.
  const marked = (value: number, at: {x: number; sure: boolean; already?: boolean} | null) => {
    if (!at?.already) return at ? {...at, text: (at.sure ? "" : "빠르면 ") + place(at.x)} : null;
    const since = crossedSince(history, value, direction);
    return since !== null ? {x: since, sure: true, text: place(since) + "부터 넘음"} : {x: at.x, sure: true, text: "이미 넘음"};
  };
  const lines = $derived([
    ...(limits.management !== null && !scaled.outside.management ? [{key: "management", name: "관리 기준", value: limits.management, reach: marked(limits.management, reach.management)}] : []),
    ...(limits.end !== null && !scaled.outside.end ? [{key: "end", name: "종료 기준", value: limits.end, reach: marked(limits.end, reach.end)}] : []),
  ]);
  let hover: number | null = $state(null);
  function move(event: PointerEvent) {
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    hover = view.from + Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)) * (view.to - view.from);
  }
  const read = $derived(hover !== null ? nearestAt(shown, future, hover) : tail ? {kind: "measured" as const, point: tail} : null);
</script>

<figure class="outlook-chart" class:unreliable>
  <p class="readout" aria-live="off">{#if read}
    <span>{place(read.point.x)}{hover === null ? " · 마지막 측정" : ""}</span>
    {#if read.kind === "measured"}<b><i class="key measured"></i>{measure(read.point.value, unit, 4)}</b>
    {:else}<b><i class="key estimate"></i>예측 {measure(read.point.estimate, unit, 4)}</b>{#if read.point.lower !== null && read.point.upper !== null}<small>범위 {measure(read.point.lower, unit, 3)} ~ {measure(read.point.upper, unit, 3)}</small>{/if}{/if}
  {/if}</p>
  <ValueAxis {ticks} {height} {unit}>
    <div class="plot" role="presentation" onpointermove={move} onpointerleave={() => hover = null}>
      <svg viewBox={"0 0 " + W + " " + height} preserveAspectRatio="none" role="img" style:height={height + "px"}
        aria-label={"측정과 예측 · " + place(view.from) + "부터 " + place(view.to) + "까지" + lines.map(line => " · " + line.name + " " + measure(line.value, unit)).join("")}>
        {#each ticks as tick (tick.value)}<line x1="0" x2={W} y1={tick.y} y2={tick.y} class="grid"/>{/each}
        {#if change && change.to >= view.from}{@const start = Math.max(0, x(change.from))}
          <rect class="change" x={start} width={Math.max(3, Math.min(W, x(change.to)) - start)} {height}/>{/if}
        {#if baseline?.low != null && baseline.high != null}<rect class="baseline" x="0" width={x(last)} y={y(baseline.high)} height={Math.max(1, y(baseline.low) - y(baseline.high))}/>{/if}
        {#if baseline?.median != null}<line class="reference" x1="0" x2={x(last)} y1={y(baseline.median)} y2={y(baseline.median)}/>{/if}
        {#if band}<path class="band" d={band}/>{/if}
        <line class="now" x1={x(last)} x2={x(last)} y1="0" y2={height}/>
        {#each lines as line (line.key)}<line class={"limit " + line.key} x1="0" x2={W} y1={y(line.value)} y2={y(line.value)}/>{/each}
        <path class="measured" d={measured}/>
        <path class="estimate" d={estimate}/>
        {#if change && change.from >= view.from}<line class="onset" x1={x(change.from)} x2={x(change.from)} y1="0" y2={height}/>{/if}
        {#if hover !== null}<line class="cursor" x1={x(hover)} x2={x(hover)} y1="0" y2={height}/>{/if}
      </svg>
      {#if tail}<span class="dot" style:left={pct(tail.x) + "%"} style:top={y(tail.value) / height * 100 + "%"}></span>{/if}
      {#if start}
        <span class="dot forecast-dot" style:left={pct(start.x) + "%"} style:top={y(start.estimate) / height * 100 + "%"}></span>
        <span class="start-label" class:left={pct(start.x) > 76} style:left={pct(start.x) + "%"}
          style:top={y(start.estimate) / height * 100 + "%"}>첫 예측 {measure(start.estimate, unit, 4)}</span>
      {/if}
      {#each lines as line (line.key)}
        <span class={"limit-label " + line.key} style:top={y(line.value) / height * 100 + "%"}>{line.name} {measure(line.value, unit)}</span>
        {#if line.reach}
          {#if line.reach.x <= view.to}
            <span class={"reach " + line.key} class:maybe={!line.reach.sure} style:left={pct(line.reach.x) + "%"} style:top={y(line.value) / height * 100 + "%"}></span>
            <span class={"reach-label " + line.key} class:left={pct(line.reach.x) > 70} style:left={pct(line.reach.x) + "%"} style:top={y(line.value) / height * 100 + "%"}>{line.reach.text}</span>
          {:else}
            <span class={"reach-label beyond " + line.key} style:top={y(line.value) / height * 100 + "%"}>{line.reach.text} →</span>
          {/if}
        {/if}
      {/each}
    </div>
    {#snippet footer()}<XAxis lo={view.from} hi={view.to} {scale}/>{/snippet}
  </ValueAxis>
  <figcaption class="legend">
    <span><i class="key measured"></i>측정값</span>
    {#if baseline?.median != null}<span><i class="key reference"></i>초기 수준</span>{/if}
    {#if baseline?.low != null}<span><i class="key baseline"></i>초기 범위</span>{/if}
    {#if change}<span><i class="key change"></i>조사한 변화</span>{/if}
    <span><i class="key estimate"></i>예측</span>
    {#if band}<span><i class="key band"></i>예측 범위</span>{/if}
    {#if limits.management !== null && scaled.outside.management}<span>관리 기준 {measure(limits.management, unit)} · 그래프 밖</span>{/if}
    {#if limits.end !== null && scaled.outside.end}<span>종료 기준 {measure(limits.end, unit)} · 그래프 밖</span>{/if}
  </figcaption>
</figure>

<style>
  .outlook-chart{margin:0;min-width:0;display:grid;gap:6px}
  .readout{display:flex;align-items:baseline;gap:10px;margin:0;min-height:1.5em;padding-left:56px;font-size:var(--font-small);color:var(--color-ink-muted);font-variant-numeric:tabular-nums}
  .readout b{display:inline-flex;align-items:center;gap:6px;color:var(--color-ink);font-weight:650}
  .readout small{font-size:var(--font-label)}
  .outlook-chart :global(.plotted){grid-template-columns:56px minmax(0,1fr)}
  .plot{position:relative}
  svg{display:block;width:100%;overflow:hidden}
  line,path{vector-effect:non-scaling-stroke}
  .grid{stroke:#e3eaee;stroke-width:1}
  .change{fill:var(--color-change-fill)}
  .onset{stroke:var(--color-change-line);stroke-width:1.5}
  .baseline{fill:var(--color-reference-line);opacity:.1}
  .reference{stroke:var(--color-reference-line);stroke-width:1;stroke-dasharray:5 4}
  .band{fill:var(--color-series-1);opacity:.12}
  .measured{fill:none;stroke:var(--color-series-1);stroke-width:1.6;stroke-linejoin:round}
  .estimate{fill:none;stroke:var(--color-series-1);stroke-width:1.8;stroke-dasharray:6 4}
  .unreliable .estimate{stroke:var(--color-ink-muted)}.unreliable .band{fill:var(--color-ink-muted);opacity:.08}
  .now{stroke:var(--color-ink-muted);stroke-width:1;opacity:.5}
  .limit{stroke-width:1.5;stroke-dasharray:3 3}.limit.management{stroke:var(--color-caution-ink)}.limit.end{stroke:var(--color-failure-ink)}
  .cursor{stroke:var(--color-ink);stroke-dasharray:3 3;stroke-width:1}
  .dot{position:absolute;width:8px;height:8px;margin:-4px 0 0 -4px;border-radius:50%;background:var(--color-series-1);box-shadow:0 0 0 2px var(--color-surface);pointer-events:none}
  .forecast-dot{background:var(--color-surface);border:2px solid var(--color-series-1);box-sizing:border-box}
  .unreliable .forecast-dot{border-color:var(--color-ink-muted)}
  .start-label{position:absolute;transform:translate(8px,6px);padding:1px 5px;border-radius:3px;background:var(--color-surface);color:var(--color-ink-muted);font-size:var(--font-label);font-weight:650;white-space:nowrap;pointer-events:none}
  .start-label.left{transform:translate(calc(-100% - 8px),6px)}
  .limit-label{position:absolute;right:4px;transform:translateY(-120%);padding:0 4px;border-radius:3px;background:rgb(255 255 255 / .85);font-size:var(--font-label);font-weight:650;pointer-events:none;white-space:nowrap}
  .limit-label.management,.reach-label.management{color:var(--color-caution-ink)}.limit-label.end,.reach-label.end{color:var(--color-failure-ink)}
  .reach{position:absolute;width:10px;height:10px;margin:-5px 0 0 -5px;border-radius:50%;background:currentColor;box-shadow:0 0 0 2px var(--color-surface);pointer-events:none}
  .reach.management{color:var(--color-caution-ink)}.reach.end{color:var(--color-failure-ink)}
  .reach.maybe{background:var(--color-surface);border:2px solid currentColor;box-sizing:border-box}
  .reach-label{position:absolute;transform:translate(8px,6px);padding:0 4px;border-radius:3px;background:rgb(255 255 255 / .85);font-size:var(--font-label);font-weight:650;white-space:nowrap;pointer-events:none;font-variant-numeric:tabular-nums}
  .reach-label.left{transform:translate(calc(-100% - 8px),6px)}
  .reach-label.beyond{right:4px;transform:translateY(6px)}
  .legend{display:flex;flex-wrap:wrap;gap:4px 14px;margin:0;padding-left:56px;font-size:var(--font-label);color:var(--color-ink-muted)}
  .legend span{display:inline-flex;align-items:center;gap:6px}
  .key{display:inline-block;width:16px;height:0;border-top:2px solid}
  .key.measured{border-color:var(--color-series-1)}
  .key.estimate{border-color:var(--color-series-1);border-top-style:dashed}
  .key.reference{border-color:var(--color-reference-line);border-top:1.5px dashed var(--color-reference-line)}
  .key.baseline{height:10px;border:0;background:var(--color-reference-line);opacity:.25}
  .key.change{width:14px;height:12px;border:0;border-left:1.5px solid var(--color-change-line);background:var(--color-change-fill)}
  .key.band{height:10px;border:0;background:var(--color-series-1);opacity:.2}
</style>
