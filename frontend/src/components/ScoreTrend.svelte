<script lang="ts">
  import {elapsedText, xTicks, measurementScale} from "../time-axis";
  import {onMount} from "svelte";
  import {num} from "../format";
  import type {ModelBinding, StepPointer} from "../model-evidence";
  import {exceedanceStory, exceedanceText, measurementTime, readScoreTrend, trendSummary, type Interval, type ScoreTrend, type TrendPoint} from "../model-trend";
  import StatusNotice from "./StatusNotice.svelte";

  /** Every stored score of this model in input order, its threshold and the intervals the
   * model marked as over it. Choosing a point or an interval opens that measurement. */
  type Props = {binding: ModelBinding; selected: number | null; place: (position: number) => string;
    onSelect: (step: StepPointer) => void; onLoaded?: (steps: StepPointer[], intervals: Interval[]) => void;
    period?: number | null};
  let {binding, selected, place, onSelect, onLoaded, period = null}: Props = $props();
  let trend: ScoreTrend | null = $state(null);
  let loadState: "loading" | "ready" | "failed" = $state("loading");
  const W = 640, H = 170, LEFT = 44, RIGHT = 628, TOP = 14, BOTTOM = 142;

  const scored = $derived.by((): TrendPoint[] => {
    const current: ScoreTrend | null = trend;
    return current ? current.points.filter((point) => point.score !== null) : [];
  });
  const summary = $derived.by(() => {
    const current: ScoreTrend | null = trend;
    return current ? trendSummary(current) : null;
  });
  const threshold = $derived(scored.find((point) => point.threshold !== null)?.threshold ?? null);
  // What to read first: a run still going on, else a latest one-off crossing, else "below now".
  const story = $derived.by(() => { const current: ScoreTrend | null = trend; return current ? exceedanceStory(current) : null; });
  const told = $derived(story ? exceedanceText(story, place) : null);
  const first = $derived(story?.anchor ?? null);
  const scale = $derived.by(() => {
    const values = scored.map((point) => point.score as number);
    if (threshold !== null) values.push(threshold);
    const low = Math.min(0, ...values), high = Math.max(...values, low + 1e-9);
    const first = trend?.points[0]?.pointer.position ?? 0, last = trend?.points.at(-1)?.pointer.position ?? 1;
    const span = Math.max(1, last - first);
    return {x: (position: number) => LEFT + ((position - first) / span) * (RIGHT - LEFT),
      y: (value: number) => BOTTOM - ((value - low) / (high - low)) * (BOTTOM - TOP), low, high, first, last};
  });
  // Lines join consecutive analyzed steps only; a skipped step leaves a gap.
  const path = $derived.by(() => {
    if (!trend) return "";
    let d = "", drawing = false;
    for (const point of trend.points) {
      if (point.score === null) { drawing = false; continue; }
      d += (drawing ? "L" : "M") + scale.x(point.pointer.position).toFixed(1) + " " + scale.y(point.score).toFixed(1) + " ";
      drawing = true;
    }
    return d;
  });

  function choose(position: number) {
    const point = trend?.points.find((item) => item.pointer.position === position);
    if (point) onSelect(point.pointer);
  }
  onMount(() => {
    const request = new AbortController();
    void readScoreTrend(binding, request.signal).then((value) => {
      if (!request.signal.aborted) { trend = value; loadState = "ready"; onLoaded?.(value.points.map(point=>point.pointer), value.intervals); }
    }).catch(() => { if (!request.signal.aborted) loadState = "failed"; });
    return () => request.abort();
  });
</script>

<section class="trend" aria-labelledby={"trend-" + binding.bindingId}>
  <h3 id={"trend-" + binding.bindingId}>점수 추이</h3>
  {#if loadState === "loading"}
    <StatusNotice message="이 모델의 점수 기록을 불러오고 있습니다." />
  {:else if loadState === "failed" || !trend}
    <StatusNotice kind="uncertain" message="점수 추이를 불러오지 못했습니다. 아래에서 측정을 골라 점수를 볼 수 있습니다." />
  {:else if !scored.length}
    <p class="context">아직 그릴 점수가 없습니다{summary?.skipped ? " · 분석에서 제외된 측정 " + summary.skipped + "회" : ""}.</p>
  {:else}
    <p class="context">분석 {summary?.analyzed}회 · 모델 기준 초과 {summary?.exceeded}회 · 기준 초과 구간 {trend.intervals.length}개{summary?.open ? " (진행 중 " + summary.open + "개)" : ""}{summary?.skipped ? " · 분석에서 제외 " + summary.skipped + "회" : ""}{trend.truncated ? " · 기록이 많아 앞부분만 읽었습니다" : ""}</p>
    {#if first && told}
      <div class="onset" aria-label="기준 초과 상태">
        <strong>{told.headline}</strong>
        {#if first.eventStart && measurementTime(first, period)}<span>{measurementTime(first, period)}</span>{/if}
        <button type="button" class="ui-button" onclick={() => {if (first) onSelect(first.pointer);}}>{story?.state === "ongoing" ? "구간 시작 보기 →" : "측정 보기 →"}</button>
        {#if told.earlier}<span class="earlier">{told.earlier}{#if story?.first && story.first !== first}
          <button type="button" class="link" onclick={() => {if (story?.first) onSelect(story.first.pointer);}}>그 측정 보기</button>{/if}</span>{/if}
      </div>
    {/if}
    {#if period}<p class="context">가로축 · 기록 시작 후 경과 시간 · 기록된 측정 간격 {elapsedText(period)}</p>{/if}
    <svg viewBox={"0 0 " + W + " " + H} role="img"
      aria-label={"모델 점수 추이 · " + place(scale.first) + "부터 " + place(scale.last) + "까지 · 기준 " + num(threshold, "없음")}>
      {#each trend.intervals as interval (interval.start)}
        <rect x={scale.x(interval.start) - 2} y={TOP} width={Math.max(4, scale.x(interval.end) - scale.x(interval.start) + 4)} height={BOTTOM - TOP} class="band" />
      {/each}
      <path d={"M" + LEFT + " " + TOP + " V" + BOTTOM + " H" + RIGHT} class="axis" />
      {#if threshold !== null}
        <line x1={LEFT} x2={RIGHT} y1={scale.y(threshold)} y2={scale.y(threshold)} class="threshold" />
        <text x={LEFT + 4} y={scale.y(threshold) - 4} class="label">모델 기준 {num(threshold)}</text>
      {/if}
      <path d={path} class="line" />
      {#if first}
        <line x1={scale.x(first.pointer.position)} x2={scale.x(first.pointer.position)} y1={TOP} y2={BOTTOM} class="onset-line">
          <title>{told?.headline ?? place(first.pointer.position)}{first.eventStart && measurementTime(first, period) ? " · " + measurementTime(first, period) : ""}</title>
        </line>
        <circle cx={scale.x(first.pointer.position)} cy={scale.y(first.score)} r="5" class="onset-dot" />
      {/if}
      {#each scored as point (point.pointer.position)}
        <circle cx={scale.x(point.pointer.position)} cy={scale.y(point.score as number)} r={point.pointer.position === selected ? 5 : 2.5}
          class:over={point.exceeds} class:chosen={point.pointer.position === selected}
          onclick={() => choose(point.pointer.position)} role="presentation">
          <title>{place(point.pointer.position)} · 점수 {num(point.score)}</title>
        </circle>
      {/each}
      {#if period}
        {#each xTicks(scale.first, scale.last, measurementScale(period), 3) as tick (tick.value)}
          <text x={scale.x(tick.value)} y={H - 6} text-anchor={tick.x < 0.1 ? "start" : tick.x > 0.9 ? "end" : "middle"} class="label">{tick.label}</text>
        {/each}
      {:else}
        <text x={LEFT} y={H - 6} class="label">{place(scale.first)}</text>
        <text x={RIGHT} y={H - 6} text-anchor="end" class="label">{place(scale.last)}</text>
      {/if}
      <text x={LEFT + 4} y={TOP + 10} class="label">최고 {num(scale.high)}</text>
    </svg>
    <p class="context">점을 누르면 그 측정의 점수와 원본을 아래에서 봅니다. 음영은 모델이 기준을 넘었다고 표시한 구간입니다.{first ? (story?.state === "ongoing" ? " 세로 점선은 지금 이어지는 기준 초과가 시작된 측정입니다." : " 세로 점선은 위에 적은 측정입니다.") : ""}</p>
    {#if trend.intervals.length}
      <ul class="intervals" aria-label="기준 초과 구간">
        {#each trend.intervals as interval (interval.start)}
          <li>{place(interval.start)} ~ {place(interval.end)} · {interval.steps}회 · 최고 {num(interval.peak, "기록 없음")}{interval.open ? " · 진행 중" : ""}
            <button type="button" class="ui-button" onclick={() => choose(interval.start)}>시작 측정 보기</button></li>
        {/each}
      </ul>
    {/if}
  {/if}
</section>

<style>
  .trend { display: grid; gap: var(--space-2); margin-block: var(--space-4); min-width: 0; }
  h3 { margin: 0; font-size: var(--font-section); }
  p { margin: 0; overflow-wrap: anywhere; }
  .context { color: var(--color-ink-muted); font-size: var(--font-small); }
  svg { width: 100%; height: auto; max-height: 240px; }
  .axis { fill: none; stroke: var(--color-border); }
  .band { fill: var(--color-uncertain-surface); }
  .threshold { stroke: var(--color-failure-ink); stroke-dasharray: 5 4; }
  .line { fill: none; stroke: var(--color-action); stroke-width: 1.5; }
  .onset { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2) var(--space-3); padding: var(--space-3); border-left: 3px solid var(--color-caution-ink); background: var(--color-uncertain-surface); font-size: var(--font-small); }
  .earlier { flex-basis: 100%; color: var(--color-ink-muted); }
  .link { border: 0; padding: 0; margin-left: var(--space-2); background: none; color: var(--color-action); font: inherit; text-decoration: underline; cursor: pointer; }
  .onset-line { stroke: var(--color-caution-ink); stroke-width: 2; stroke-dasharray: 3 3; vector-effect: non-scaling-stroke; }
  circle.onset-dot { fill: var(--color-caution-ink); stroke: var(--color-surface); stroke-width: 2; }
  circle { fill: var(--color-action); cursor: pointer; }
  circle.over { fill: var(--color-failure-ink); }
  circle.chosen { stroke: var(--color-ink); stroke-width: 2; }
  .label { font-size: 11px; fill: var(--color-ink-muted); }
  .intervals { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-2); }
  .intervals li { display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-3); align-items: center; overflow-wrap: anywhere; }
</style>
