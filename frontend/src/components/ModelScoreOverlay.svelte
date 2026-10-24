<script lang="ts">
  import {elapsedText, xTicks, measurementScale} from "../time-axis";
  import {onMount} from "svelte";
  import type {ModelBinding} from "../model-evidence";
  import {exceedanceText, measurementTime, overlayModels, readScoreTrend, thresholdRatios, type RatioLine} from "../model-trend";
  import StatusNotice from "./StatusNotice.svelte";

  /** The models of one measurement stream on one axis: each score divided by that model's own
   * threshold, so whether the models agree, and since when, is one look. Every model has a row
   * that opens it below; a point in the graph opens that measurement. */
  type Props = {bindings: ModelBinding[]; names: Map<string, string>; selected: string;
    place: (position: number) => string; onChoose: (bindingId: string) => void; onPick: (position: number) => void;
    period?: number | null};
  let {bindings, names, selected, place, onChoose, onPick, period = null}: Props = $props();
  // Fixed categorical order (validated for colour-vision deficiency). Up to four lines share the
  // graph and the chosen model is always one of them: the first three keep their colour, the
  // fourth is the chosen model when it is further down the list.
  const COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"];
  const shown = $derived(overlayModels(bindings, selected, COLORS.length));
  let lines: Map<string, RatioLine | null> = $state(new Map());
  const line = (binding: ModelBinding) => lines.get(binding.bindingId) ?? null;
  const colour = (binding: ModelBinding) => COLORS[shown.findIndex((item) => item.bindingId === binding.bindingId)] ?? null;
  let loadState: "loading" | "ready" | "failed" = $state("loading");
  // Where the chosen model's state starts: its run still going on, else its latest crossing.
  const first = $derived(lines.get(selected)?.story.anchor ?? null);
  const told = $derived.by(() => { const read = lines.get(selected); return read ? exceedanceText(read.story, place) : null; });
  let hover: number | null = $state(null);
  // Drawn in real pixels so text stays readable on a phone; end labels only where there is room.
  let width = $state(720);
  const W = $derived(Math.max(300, Math.round(width)));
  const labelled = $derived(W >= 520);
  const H = 210, LEFT = 64, TOP = 14, BOTTOM = 178;
  const RIGHT = $derived(W - (labelled ? 124 : 12));

  const scale = $derived.by(() => {
    const all = shown.flatMap((binding) => line(binding)?.points ?? []);
    const first = all.length ? Math.min(...all.map((p) => p.position)) : 0;
    const last = all.length ? Math.max(...all.map((p) => p.position)) : 1;
    const high = Math.max(1.25, ...all.map((p) => p.ratio));
    const span = Math.max(1, last - first);
    return {first, last, high, positions: [...new Set(all.map((p) => p.position))].sort((a, b) => a - b),
      x: (position: number) => LEFT + ((position - first) / span) * (RIGHT - LEFT),
      y: (ratio: number) => BOTTOM - (Math.max(0, ratio) / high) * (BOTTOM - TOP)};
  });
  // Consecutive positions are joined; a skipped or missing step leaves a gap.
  function path(drawn: RatioLine): string {
    let d = "", previous: number | null = null;
    const index = new Map(scale.positions.map((at, i) => [at, i]));
    for (const point of drawn.points) {
      const joined = previous !== null && index.get(point.position)! - index.get(previous)! === 1;
      d += (joined ? "L" : "M") + scale.x(point.position).toFixed(1) + " " + scale.y(point.ratio).toFixed(1) + " ";
      previous = point.position;
    }
    return d;
  }
  // End labels in ink, nudged apart so two lines that end together stay readable.
  const ends = $derived.by(() => {
    const rows = shown.flatMap((binding) => {
      const latest = line(binding)?.latest;
      return latest ? [{id: binding.bindingId, name: names.get(binding.bindingId) ?? "", y: scale.y(latest.ratio)}] : [];
    }).sort((a, b) => a.y - b.y);
    for (let i = 1; i < rows.length; i++) rows[i].y = Math.max(rows[i].y, rows[i - 1].y + 13);
    return rows;
  });
  const ratio = (value: number) => value.toLocaleString("ko-KR", {maximumFractionDigits: value < 10 ? 2 : 1});
  function at(drawn: RatioLine | null, position: number) {
    return drawn?.points.find((point) => point.position === position) ?? null;
  }
  function summary(read: RatioLine | null): string {
    if (!read) return "점수 기록을 읽지 못했습니다";
    if (!read.points.length) return "기준과 함께 저장된 점수가 없습니다";
    const parts = ["기준 초과 " + read.exceeded + "회 / 분석 " + read.analyzed + "회"];
    const told = exceedanceText(read.story, place);
    if (told) parts.push(told.headline);
    if (read.latest) parts.push(place(read.latest.position) + "에서 기준의 " + ratio(read.latest.ratio) + "배");
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
    void Promise.all(bindings.map((binding) => readScoreTrend(binding, request.signal)
      .then(thresholdRatios).catch(() => null))).then((values) => {
      if (request.signal.aborted) return;
      lines = new Map(bindings.map((binding, i) => [binding.bindingId, values[i]]));
      loadState = values.some((read) => read?.points.length) ? "ready" : "failed";
    });
    return () => request.abort();
  });
</script>

<section class="overlay" aria-labelledby="model-overlay-title">
  <h3 id="model-overlay-title">모델별 점수 비교</h3>
  <p class="context">각 모델의 점수를 그 모델의 기준으로 나눈 값입니다. 1을 넘으면 그 모델의 기준 초과입니다.</p>
  <p class="context">같은 배수가 같은 위험 수준을 뜻하지는 않습니다. 아래 모델을 고르면 해당 모델의 점수 추이를 따로 확인할 수 있습니다.</p>
  {#if loadState === "loading"}
    <StatusNotice message="모델별 점수 기록을 불러오고 있습니다." />
  {:else}
    {#if loadState === "ready"}

      <p class="readout" aria-live="polite">
        {#if hover !== null}
          <strong>{place(hover)}</strong>
          {#each shown as binding (binding.bindingId)}
            {@const point = at(line(binding), hover)}
            <span>{names.get(binding.bindingId)} {point ? "기준의 " + ratio(point.ratio) + "배" : "점수 없음"}</span>
          {/each}
        {:else}
          그래프 위에 올리거나 화살표 키로 측정별 값을 보고, 누르면 그 측정의 상세를 엽니다.
        {/if}
      </p>
    {#if period}<p class="context">가로축 · 기록 시작 후 경과 시간 · 기록된 측정 간격 {elapsedText(period)}</p>{/if}
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
        {#if BOTTOM-scale.y(1)>14}<text x={LEFT - 6} y={BOTTOM + 4} text-anchor="end" class="label">0</text>{/if}
        <text x={LEFT + 4} y={scale.y(1) - 5} class="label">각 모델 기준</text>
        {#each shown as binding (binding.bindingId)}
          {@const drawn = line(binding)}
          {#if drawn?.points.length}
            <path d={path(drawn)} class="line" class:chosen={binding.bindingId === selected} style={"stroke:" + colour(binding)} />
          {/if}
        {/each}
        {#if first}
          <line x1={scale.x(first.pointer.position)} x2={scale.x(first.pointer.position)} y1={TOP} y2={BOTTOM} class="onset-line">
            <title>{names.get(selected)} · {told?.headline ?? place(first.pointer.position)}{first.eventStart && measurementTime(first, period) ? " · " + measurementTime(first, period) : ""}</title>
          </line>
          <circle cx={scale.x(first.pointer.position)} cy={scale.y(first.score / first.threshold)} r="5" class="onset-dot" />
        {/if}
        {#if hover !== null}
          <line x1={scale.x(hover)} x2={scale.x(hover)} y1={TOP} y2={BOTTOM} class="cross" />
          {#each shown as binding (binding.bindingId)}
            {@const point = at(line(binding), hover)}
            {#if point}<circle cx={scale.x(hover)} cy={scale.y(point.ratio)} r="5" style={"fill:" + colour(binding)} class="dot" />{/if}
          {/each}
        {/if}
        {#each labelled ? ends : [] as end (end.id)}
          <text x={RIGHT + 8} y={end.y + 4} class="end">{end.name}</text>
        {/each}
      {#if period}
        {#each xTicks(scale.first, scale.last, measurementScale(period), 3) as tick (tick.value)}
          <text x={scale.x(tick.value)} y={H - 8} text-anchor={tick.x < 0.1 ? "start" : tick.x > 0.9 ? "end" : "middle"} class="label">{tick.label}</text>
        {/each}
      {:else}
        <text x={LEFT} y={H - 8} class="label">{place(scale.first)}</text>
        <text x={RIGHT} y={H - 8} text-anchor="end" class="label">{place(scale.last)}</text>
      {/if}
      </svg>
      </div>
    {:else}
      <StatusNotice kind="uncertain" message="모델별 점수를 함께 그리지 못했습니다. 아래에서 모델을 하나씩 볼 수 있습니다." />
    {/if}
    <ul class="models" aria-label="모델 선택">
      {#each bindings as binding (binding.bindingId)}
        {@const drawn = colour(binding)}
        <li>
          <button type="button" aria-pressed={binding.bindingId === selected} onclick={() => onChoose(binding.bindingId)}>
            <span class="swatch" class:off={drawn === null} style={drawn ? "background:" + drawn : ""} aria-hidden="true"></span>
            <strong>{names.get(binding.bindingId)}</strong>
            <span class="facts">{summary(line(binding))}</span>
          </button>
        </li>
      {/each}
    </ul>
    {#if bindings.length > shown.length}
      <p class="context">그래프에는 고른 모델을 포함해 {shown.length}개까지 그립니다. 다른 모델을 고르면 그 모델의 선을 그립니다.</p>
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
  .onset-line { stroke: var(--color-caution-ink); stroke-width: 2; stroke-dasharray: 3 3; }
  .onset-dot { fill: var(--color-caution-ink); stroke: var(--color-surface); stroke-width: 2; }
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
  .swatch.off { box-shadow: inset 0 0 0 1px var(--color-border); }
  .facts { color: var(--color-ink-muted); font-size: var(--font-small); overflow-wrap: anywhere; }
</style>
