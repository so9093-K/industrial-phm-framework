<script lang="ts">
  import {onMount} from "svelte";
  import type {ModelBinding} from "../model-evidence";
  import {readScoreTrend, thresholdRatios, type RatioLine} from "../model-trend";
  import StatusNotice from "./StatusNotice.svelte";

  /** The models of one measurement stream on one axis: each score divided by that model's own
   * threshold, so whether the models agree, and since when, is one look. A row opens that model
   * below; a point in the graph opens that measurement. */
  type Props = {bindings: ModelBinding[]; names: Map<string, string>; selected: string;
    place: (position: number) => string; onChoose: (bindingId: string) => void; onPick: (position: number) => void};
  let {bindings, names, selected, place, onChoose, onPick}: Props = $props();
  // Fixed categorical order (validated for colour-vision deficiency); a model keeps its colour.
  const COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"];
  const shown = $derived(bindings.slice(0, COLORS.length));
  let lines: (RatioLine | null)[] = $state([]);
  let loadState: "loading" | "ready" | "failed" = $state("loading");
  let hover: number | null = $state(null);
  // Drawn in real pixels so text stays readable on a phone; end labels only where there is room.
  let width = $state(720);
  const W = $derived(Math.max(300, Math.round(width)));
  const labelled = $derived(W >= 520);
  const H = 210, LEFT = 40, TOP = 14, BOTTOM = 178;
  const RIGHT = $derived(W - (labelled ? 124 : 12));

  const scale = $derived.by(() => {
    const all = lines.flatMap((line) => line?.points ?? []);
    const first = all.length ? Math.min(...all.map((p) => p.position)) : 0;
    const last = all.length ? Math.max(...all.map((p) => p.position)) : 1;
    const high = Math.max(1.25, ...all.map((p) => p.ratio));
    const span = Math.max(1, last - first);
    return {first, last, high, positions: [...new Set(all.map((p) => p.position))].sort((a, b) => a - b),
      x: (position: number) => LEFT + ((position - first) / span) * (RIGHT - LEFT),
      y: (ratio: number) => BOTTOM - (Math.max(0, ratio) / high) * (BOTTOM - TOP)};
  });
  // Consecutive positions are joined; a skipped or missing step leaves a gap.
  function path(line: RatioLine): string {
    let d = "", previous: number | null = null;
    const index = new Map(scale.positions.map((at, i) => [at, i]));
    for (const point of line.points) {
      const joined = previous !== null && index.get(point.position)! - index.get(previous)! === 1;
      d += (joined ? "L" : "M") + scale.x(point.position).toFixed(1) + " " + scale.y(point.ratio).toFixed(1) + " ";
      previous = point.position;
    }
    return d;
  }
  // End labels in ink, nudged apart so two lines that end together stay readable.
  const ends = $derived.by(() => {
    const rows = shown.flatMap((binding, i) => {
      const latest = lines[i]?.latest;
      return latest ? [{id: binding.bindingId, name: names.get(binding.bindingId) ?? "", y: scale.y(latest.ratio)}] : [];
    }).sort((a, b) => a.y - b.y);
    for (let i = 1; i < rows.length; i++) rows[i].y = Math.max(rows[i].y, rows[i - 1].y + 13);
    return rows;
  });
  const ratio = (value: number) => value.toLocaleString("ko-KR", {maximumFractionDigits: value < 10 ? 2 : 1});
  function at(line: RatioLine | null, position: number) {
    return line?.points.find((point) => point.position === position) ?? null;
  }
  function summary(line: RatioLine | null): string {
    if (!line) return "점수 기록을 읽지 못했습니다";
    if (!line.points.length) return "기준과 함께 저장된 점수가 없습니다";
    const parts = ["기준 초과 " + line.exceeded + "회 / 분석 " + line.analyzed + "회"];
    if (line.sustainedFrom !== null) parts.push(place(line.sustainedFrom) + "부터 계속 초과");
    if (line.latest) parts.push(place(line.latest.position) + "에서 기준의 " + ratio(line.latest.ratio) + "배");
    return parts.join(" · ");
  }
  function locate(event: PointerEvent) {
    const box = (event.currentTarget as HTMLElement).getBoundingClientRect();
    const x = ((event.clientX - box.left) / box.width) * W;
    if (!scale.positions.length || x < LEFT - 8 || x > RIGHT + 8) { hover = null; return; }
    hover = scale.positions.reduce((best, at) => Math.abs(scale.x(at) - x) < Math.abs(scale.x(best) - x) ? at : best);
  }
  // Arrow keys walk the measurements; Enter opens the one in focus.
  function step(event: KeyboardEvent) {
    const positions = scale.positions;
    if (!positions.length) return;
    const index = hover === null ? positions.length - 1 : positions.indexOf(hover);
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      hover = positions[Math.min(positions.length - 1, Math.max(0, index + (event.key === "ArrowLeft" ? -1 : 1)))];
    } else if ((event.key === "Enter" || event.key === " ") && hover !== null) {
      event.preventDefault();
      onPick(hover);
    }
  }
  onMount(() => {
    const request = new AbortController();
    void Promise.all(shown.map((binding) => readScoreTrend(binding, request.signal)
      .then(thresholdRatios).catch(() => null))).then((values) => {
      if (request.signal.aborted) return;
      lines = values;
      loadState = values.some((line) => line?.points.length) ? "ready" : "failed";
    });
    return () => request.abort();
  });
</script>

<section class="overlay" aria-labelledby="model-overlay-title">
  <h3 id="model-overlay-title">모델별 점수 비교</h3>
  <p class="context">각 모델의 점수를 그 모델의 기준으로 나눈 값입니다. 1을 넘으면 그 모델의 기준 초과입니다.</p>
  {#if loadState === "loading"}
    <StatusNotice message="모델별 점수 기록을 불러오고 있습니다." />
  {:else}
    {#if loadState === "ready"}
      <p class="readout" aria-live="polite">
        {#if hover !== null}
          <strong>{place(hover)}</strong>
          {#each shown as binding, i (binding.bindingId)}
            {@const point = at(lines[i], hover)}
            <span>{names.get(binding.bindingId)} {point ? "기준의 " + ratio(point.ratio) + "배" : "점수 없음"}</span>
          {/each}
        {:else}
          그래프 위에 올리거나 화살표 키로 측정별 값을 보고, 누르면 그 측정의 상세를 엽니다.
        {/if}
      </p>
      <div class="plot" bind:clientWidth={width} role="slider" tabindex="0" aria-label="모델별 기준 대비 점수 · 측정 선택"
        aria-valuemin={scale.first} aria-valuemax={scale.last} aria-valuenow={hover ?? scale.last}
        aria-valuetext={place(hover ?? scale.last)}
        onpointermove={locate} onpointerleave={() => hover = null} onkeydown={step}
        onclick={() => { if (hover !== null) onPick(hover); }}>
      <svg viewBox={"0 0 " + W + " " + H} role="img"
        aria-label={"모델별 기준 대비 점수 · " + place(scale.first) + "부터 " + place(scale.last) + "까지"}>
        <path d={"M" + LEFT + " " + TOP + " V" + BOTTOM + " H" + RIGHT} class="axis" />
        <line x1={LEFT} x2={RIGHT} y1={scale.y(1)} y2={scale.y(1)} class="threshold" />
        <text x={LEFT - 6} y={scale.y(1) + 4} text-anchor="end" class="label">1</text>
        <text x={LEFT - 6} y={TOP + 4} text-anchor="end" class="label">{ratio(scale.high)}</text>
        <text x={LEFT - 6} y={BOTTOM + 4} text-anchor="end" class="label">0</text>
        <text x={LEFT + 4} y={scale.y(1) - 5} class="label">각 모델 기준</text>
        {#each shown as binding, i (binding.bindingId)}
          {#if lines[i]?.points.length}
            <path d={path(lines[i]!)} class="line" class:chosen={binding.bindingId === selected} style={"stroke:" + COLORS[i]} />
          {/if}
        {/each}
        {#if hover !== null}
          <line x1={scale.x(hover)} x2={scale.x(hover)} y1={TOP} y2={BOTTOM} class="cross" />
          {#each shown as binding, i (binding.bindingId)}
            {@const point = at(lines[i], hover)}
            {#if point}<circle cx={scale.x(hover)} cy={scale.y(point.ratio)} r="5" style={"fill:" + COLORS[i]} class="dot" />{/if}
          {/each}
        {/if}
        {#each labelled ? ends : [] as end (end.id)}
          <text x={RIGHT + 8} y={end.y + 4} class="end">{end.name}</text>
        {/each}
        <text x={LEFT} y={H - 8} class="label">{place(scale.first)}</text>
        <text x={RIGHT} y={H - 8} text-anchor="end" class="label">{place(scale.last)}</text>
      </svg>
      </div>
    {:else}
      <StatusNotice kind="uncertain" message="모델별 점수를 함께 그리지 못했습니다. 아래에서 모델을 하나씩 볼 수 있습니다." />
    {/if}
    <ul class="models" aria-label="모델 선택">
      {#each shown as binding, i (binding.bindingId)}
        <li>
          <button type="button" aria-pressed={binding.bindingId === selected} onclick={() => onChoose(binding.bindingId)}>
            <span class="swatch" style={"background:" + COLORS[i]} aria-hidden="true"></span>
            <strong>{names.get(binding.bindingId)}</strong>
            <span class="facts">{summary(lines[i] ?? null)}</span>
          </button>
        </li>
      {/each}
    </ul>
    {#if bindings.length > shown.length}
      <p class="context">모델이 많아 앞의 {shown.length}개만 함께 그렸습니다. 나머지는 위의 목록에서 고릅니다.</p>
    {/if}
  {/if}
</section>

<style>
  .overlay { display: grid; gap: var(--space-2); margin-block: var(--space-4); min-width: 0; }
  h3 { margin: 0; font-size: var(--font-section); }
  p { margin: 0; overflow-wrap: anywhere; }
  .context { color: var(--color-ink-muted); font-size: var(--font-small); }
  .readout { min-height: 1.6em; font-size: var(--font-small); color: var(--color-ink-muted); display: flex; flex-wrap: wrap; gap: var(--space-1) var(--space-4); }
  .readout strong { color: var(--color-ink); }
  .plot { cursor: crosshair; touch-action: pan-y; border-radius: var(--radius-control); }
  .plot:focus-visible { outline: 3px solid var(--color-focus); outline-offset: 2px; }
  svg { display: block; width: 100%; height: auto; max-height: 260px; }
  .axis { fill: none; stroke: var(--color-border); }
  .threshold { stroke: var(--color-ink-muted); stroke-dasharray: 5 4; }
  .line { fill: none; stroke-width: 2; stroke-linejoin: round; opacity: 0.85; }
  .line.chosen { stroke-width: 2.75; opacity: 1; }
  .cross { stroke: var(--color-ink-muted); stroke-width: 1; }
  .dot { stroke: var(--color-surface); stroke-width: 2; }
  .label { font-size: 11px; fill: var(--color-ink-muted); }
  .end { font-size: 12px; fill: var(--color-ink); }
  .models { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-2); }
  .models button {
    width: 100%; display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-1) var(--space-3); text-align: left;
    padding: var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-control);
    background: var(--color-surface); color: var(--color-ink); font: inherit; cursor: pointer; min-height: 44px;
  }
  .models button[aria-pressed="true"] { border-color: var(--color-action); background: var(--color-surface-selected); }
  .swatch { width: 14px; height: 4px; border-radius: 2px; flex: none; }
  .facts { color: var(--color-ink-muted); font-size: var(--font-small); overflow-wrap: anywhere; }
</style>
