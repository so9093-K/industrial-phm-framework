<script lang="ts">
  import {xTicks, measurementScale, measurementLabel} from "../time-axis";
  import {onMount} from "svelte";
  import {movePosition} from "../plot-selection";
  import {num} from "../format";
  import {measure, yTicks} from "../chart-axis";
  import {isTimeWindow, type ModelBinding, type StepPointer} from "../model-evidence";
  import {drawTrend, exceedanceLane, exceedanceStory, exceedanceText, measurementTime, priorityIntervals, readScoreTrend, trendSummary, type Interval, type ScoreTrend, type TrendPoint} from "../model-trend";
  import {scoreRaisers} from "../score-raisers";
  import type {ReasonRow} from "../score-reason";
  import StatusNotice from "./StatusNotice.svelte";
  import ModelOperation from "./ModelOperation.svelte";

  /** Every stored score of this model in input order, its threshold and the intervals the
   * model marked as over it. Choosing a point or an interval opens that measurement. */
  type Props = {binding: ModelBinding; selected: number | null; place: (position: number) => string;
    onSelect: (step: StepPointer) => void; onLoaded?: (steps: StepPointer[], intervals: Interval[]) => void;
    period?: number | null; pinned?: boolean;
    /** The signal that raised the selected result most, drawn under the scores. */
    signal?: ReasonRow | null};
  let {binding, selected, place, onSelect, onLoaded, period = null, pinned = false, signal = null}: Props = $props();
  let trend: ScoreTrend | null = $state(null);
  let loadState: "loading" | "ready" | "failed" = $state("loading");
  let focus: Interval | null = $state(null);
  let chartWidth = $state(640);
  let hovered: TrendPoint | null = $state(null);
  const W = $derived(Math.max(300,chartWidth));
  const RIGHT = $derived(W-12);
  // PC 화면에서 점수의 오르내림이 읽히도록 그림 영역을 넉넉히 둔다.
  const H = 300, LEFT = 52, TOP = 14, BOTTOM = 244, LANE = 254, LANE_HEIGHT = 12;
  const visible = $derived.by((): TrendPoint[] => {
    const read: ScoreTrend | null = trend;
    if (!read) return [];
    if (!focus) return read.points;
    const spacing = read.points.length > 1 ? read.points[1].pointer.position-read.points[0].pointer.position : 1;
    const margin = Math.max(focus.end-focus.start,spacing*5);
    return read.points.filter(point=>point.pointer.position>=focus!.start-margin && point.pointer.position<=focus!.end+margin/2);
  });
  const drawn = $derived(drawTrend(visible,Math.max(20,Math.floor(chartWidth/4))));
  const lane = $derived(exceedanceLane(visible,Math.max(20,Math.floor(chartWidth/6))));

  const scored = $derived.by((): TrendPoint[] => {
    return visible.filter((point) => point.score !== null);
  });
  const summary = $derived.by(() => {
    const current: ScoreTrend | null = trend;
    return current ? trendSummary(current) : null;
  });
  const threshold = $derived(scored.find((point) => point.threshold !== null)?.threshold ?? null);
  // What to read first: a run still going on, else a latest one-off crossing, else "below now".
  const story = $derived.by(() => { const current: ScoreTrend | null = trend; return current && !current.truncated ? exceedanceStory(current) : null; });
  const told = $derived(story ? exceedanceText(story, position=>isTimeWindow(binding.stepKind)?place(position):measurementLabel(position), "마지막 분석") : null);
  const first = $derived(story?.anchor ?? null);
  const priorities = $derived.by(() => { const read: ScoreTrend | null = trend; return priorityIntervals(read?.intervals ?? []); });
  /** The signals that raised the scores of one exceedance interval, its results' parts added up. */
  function raisedIn(interval: Interval, limit: number): string {
    const inside = (trend?.points ?? []).filter((point) => point.pointer.position >= interval.start && point.pointer.position <= interval.end);
    return scoreRaisers(inside.map((point) => point.contributions), limit).map((item) => item.signal).join(" · ");
  }
  const scale = $derived.by(() => {
    const values = scored.map((point) => point.score as number);
    if (threshold !== null) values.push(threshold);
    const low = Math.min(0, ...values), high = Math.max(...values, low + 1e-9);
    const first = visible[0]?.pointer.position ?? 0, last = visible.at(-1)?.pointer.position ?? 1;
    const span = Math.max(1, last - first);
    return {x: (position: number) => LEFT + ((position - first) / span) * (RIGHT - LEFT),
      y: (value: number) => BOTTOM - ((value - low) / (high - low)) * (BOTTOM - TOP), low, high, first, last};
  });
  // Lines join consecutive analyzed steps only; a skipped step leaves a gap.
  const path = $derived.by(() => {
    let d = "", drawing = false;
    for (const point of drawn) {
      if (point.score === null) { drawing = false; continue; }
      d += (drawing ? "L" : "M") + scale.x(point.pointer.position).toFixed(1) + " " + scale.y(point.score).toFixed(1) + " ";
      drawing = true;
    }
    return d;
  });
  const overPath = $derived.by(() => {
    let d = "";
    for (let i=1;i<drawn.length;i++) {
      const a=drawn[i-1], b=drawn[i];
      if(a.score===null||b.score===null||(!a.exceeds&&!b.exceeds))continue;
      d += "M"+scale.x(a.pointer.position)+" "+scale.y(a.score)+"L"+scale.x(b.pointer.position)+" "+scale.y(b.score)+" ";
    }
    return d;
  });
  const ticks = $derived.by(() => {
    const count = chartWidth<480 ? 3 : 5;
    return isTimeWindow(binding.stepKind)
      ? xTicks(scale.first/1000,scale.last/1000,{kind:"clock"},count).map(tick=>({...tick,value:tick.value*1000}))
      : xTicks(scale.first,scale.last,measurementScale(period),count);
  });
  const chosen = $derived(scored.find(point=>point.pointer.position===selected) ?? null);
  const inspected = $derived(hovered ?? chosen);
  const inspectedRaised = $derived(inspected?.exceeds ? scoreRaisers(inspected.contributions, 1)[0]?.signal ?? "" : "");
  // 점수를 가장 많이 올린 신호의 값: 판정한 구간만 잇고, 판정하지 않은 구간은 끊는다.
  const SH = 120, ST = 8, SB = 104;
  const signalDrawn = $derived.by((): TrendPoint[] => {
    if (!signal) return [];
    const feature = signal.feature;
    return drawTrend(visible.map((point) => {
      const value = point.score === null ? null : point.features?.[feature];
      return {...point, score: typeof value === "number" && Number.isFinite(value) ? value : null};
    }), Math.max(20, Math.floor(chartWidth / 4)));
  });
  const signalScale = $derived.by(() => {
    const values = signalDrawn.flatMap((point) => point.score === null ? [] : [point.score]);
    if (signal?.learned) values.push(signal.learned.low, signal.learned.high);
    if (!values.length) return null;
    const low = Math.min(...values), high = Math.max(...values, low + 1e-9), pad = (high - low) * 0.06;
    return {low: low - pad, high: high + pad, y: (value: number) => SB - ((value - (low - pad)) / (high - low + 2 * pad)) * (SB - ST)};
  });
  const signalPath = $derived.by(() => {
    if (!signalScale) return "";
    let d = "", drawing = false;
    for (const point of signalDrawn) {
      if (point.score === null) { drawing = false; continue; }
      d += (drawing ? "L" : "M") + scale.x(point.pointer.position).toFixed(1) + " " + signalScale.y(point.score).toFixed(1) + " ";
      drawing = true;
    }
    return d;
  });
  const signalChosen = $derived.by(() => {
    const value = signal && chosen ? chosen.features?.[signal.feature] : null;
    return typeof value === "number" && Number.isFinite(value) ? value : null;
  });
  const clipId = $derived("score-clip-"+binding.bindingId);
  function pointAt(event: PointerEvent | MouseEvent): TrendPoint | null {
    const rect = (event.currentTarget as SVGRectElement).ownerSVGElement!.getBoundingClientRect();
    const x = (event.clientX-rect.left)/rect.width*W;
    const position = scale.first + Math.max(0,Math.min(1,(x-LEFT)/(RIGHT-LEFT)))*(scale.last-scale.first);
    return scored.length ? scored.reduce((a,b)=>Math.abs(a.pointer.position-position)<=Math.abs(b.pointer.position-position)?a:b) : null;
  }
  function inspectInterval(interval: Interval) { focus=interval; hovered=null; choose(interval.start); }

  $effect(() => {
    if (focus && selected !== null && (selected < scale.first || selected > scale.last)) { focus = null; hovered = null; }
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
  <h3 class="visually-hidden" id={"trend-" + binding.bindingId}>점수 추이</h3>
  {#if loadState === "loading"}
    <StatusNotice message="이 모델의 점수 기록을 불러오고 있습니다." />
  {:else if loadState === "failed" || !trend}
    <StatusNotice kind="uncertain" message="점수 추이를 불러오지 못했습니다. 아래에서 측정을 골라 점수를 볼 수 있습니다." />
  {:else if !scored.length}
    <p class="context">아직 그릴 점수가 없습니다{summary?.skipped ? " · 분석에서 제외된 측정 " + summary.skipped + "회" : ""}.</p>
  {:else}
    {#if first && told}
      <div class="onset" aria-label="기준 초과 상태">
        <p class="result-statement">{told.headline}</p>
        <div class="onset-actions">
          {#if first.eventStart && measurementTime(first, period)}<span>{measurementTime(first, period)}</span>{/if}
          <button type="button" class="ui-button" onclick={() => {if (first) onSelect(first.pointer);}}>{story?.state === "ongoing" ? "구간 시작 보기 →" : "측정 보기 →"}</button>
        </div>
      </div>
    {:else if summary && !summary.exceeded && !trend.truncated}
      <p class="result-statement">분석한 {summary.analyzed}회 모두 모델 기준 이하였습니다.</p>
    {/if}
    {#if trend.truncated}<StatusNotice kind="uncertain" message="점수 기록을 일부만 읽었습니다. 전체 기록의 마지막 상태는 이 그래프로 판단할 수 없습니다."/>{/if}
    <div class="chart" bind:clientWidth={chartWidth}>
    {#if focus}<div class="chart-head"><strong>선택 구간의 점수 추이</strong>
      <button type="button" class="ui-button" onclick={()=>{focus=null;hovered=null;}}>전체 기록 보기</button></div>{/if}
    <ul class="legend" aria-label="모델 점수 범례">
      <li><i class="key score-key"></i>모델 점수</li><li><i class="key over-key"></i>기준 초과</li>
      <li><i class="key threshold-key"></i>모델 기준 {num(threshold)}</li>
      <li title="아래 띠 · 기준을 넘은 측정 비율(진할수록 많음)"><i class="key interval-key"></i>초과 비율</li>
    </ul>
    <div class="score-cursor" role="slider" tabindex="0" aria-label="모델 측정 선택" aria-valuemin={scored[0]?.pointer.position??0} aria-valuemax={scored.at(-1)?.pointer.position??1} aria-valuenow={selected??scored.at(-1)?.pointer.position??0} aria-valuetext={selected===null?"측정 선택":place(selected)} onkeydown={event=>{const at=movePosition(scored.map(p=>p.pointer.position),selected,event.key);if(at!==null){event.preventDefault();choose(at);}}}>
    <svg viewBox={"0 0 " + W + " " + H} role="img"
      aria-label={"모델 점수 추이 · " + place(scale.first) + "부터 " + place(scale.last) + "까지 · 기준 " + num(threshold, "없음")}>
      <defs><clipPath id={clipId}><rect x={LEFT} y={TOP} width={RIGHT-LEFT} height={BOTTOM-TOP} /></clipPath>
        <clipPath id={clipId+"-over"}><rect x={LEFT} y={TOP} width={RIGHT-LEFT} height={Math.max(0,(threshold!==null?scale.y(threshold):TOP)-TOP)} /></clipPath></defs>
      <path d={"M" + LEFT + " " + TOP + " V" + BOTTOM + " H" + RIGHT} class="axis" />
      <!-- Value ticks sit outside the plot so they never cover the threshold label. -->
      {#each yTicks(scale.low, scale.high, TOP, BOTTOM, 5) as tick (tick.value)}
        <line x1={LEFT} x2={RIGHT} y1={tick.y} y2={tick.y} class="grid" />
        <text x={LEFT - 6} y={tick.y + 4} text-anchor="end" class="label">{measure(tick.value, null)}</text>
      {/each}
      {#if threshold !== null}
        <line x1={LEFT} x2={RIGHT} y1={scale.y(threshold)} y2={scale.y(threshold)} class="threshold" />
      {/if}
      <path d={path} class="line" clip-path={"url(#"+clipId+")"} />
      <path d={overPath} class="over-line" clip-path={"url(#"+clipId+"-over)"} />
      {#if first && first.pointer.position>=scale.first && first.pointer.position<=scale.last}
        <line x1={scale.x(first.pointer.position)} x2={scale.x(first.pointer.position)} y1={TOP} y2={BOTTOM} class="onset-line">
          <title>{told?.headline ?? place(first.pointer.position)}{first.eventStart && measurementTime(first, period) ? " · " + measurementTime(first, period) : ""}</title>
        </line>
        <circle cx={scale.x(first.pointer.position)} cy={scale.y(first.score)} r="5" class="onset-dot" />
      {/if}
      {#each scored.length <= 80 ? scored : [] as point (point.pointer.position)}
        <circle cx={scale.x(point.pointer.position)} cy={scale.y(point.score as number)} r={point.pointer.position === selected ? 5 : 2.5}
          class:over={point.exceeds} class:chosen={point.pointer.position === selected}
          onclick={() => choose(point.pointer.position)} role="presentation">
          <title>{place(point.pointer.position)} · 점수 {num(point.score)}</title>
        </circle>
      {/each}
      <!-- Under the plot, how much of each stretch was over the threshold: darker is more. -->
      <text x={LEFT - 6} y={LANE + LANE_HEIGHT - 2} text-anchor="end" class="label">초과</text>
      <rect x={LEFT} y={LANE} width={RIGHT-LEFT} height={LANE_HEIGHT} class="lane" />
      {#each lane as row (row.start)}{#if row.over}
        <rect x={scale.x(row.start)} y={LANE} width={Math.max(2,scale.x(row.end)-scale.x(row.start))} height={LANE_HEIGHT}
          class="lane-over" fill-opacity={0.2+0.8*row.over/row.judged}><title>{place(row.start)} ~ {place(row.end)} · {row.judged}회 중 {row.over}회 기준 초과</title></rect>
      {/if}{/each}
      {#each ticks as tick (tick.value)}
          <text x={scale.x(tick.value)} y={H - 6} text-anchor={tick.x < 0.1 ? "start" : tick.x > 0.9 ? "end" : "middle"} class="label">{tick.label}</text>
      {/each}
      {#if inspected}<circle cx={scale.x(inspected.pointer.position)} cy={scale.y(inspected.score!)} r="4" class="inspection-dot" />{/if}
      <rect x={LEFT} y={TOP} width={RIGHT-LEFT} height={BOTTOM-TOP} fill="transparent" role="presentation"
        onpointermove={event=>hovered=pointAt(event)} onpointerleave={()=>hovered=null}
        onclick={event=>{const point=pointAt(event);if(point)onSelect(point.pointer);}} />
    </svg></div>
    {#if signal && signalScale && signalPath}
      <figure class="signal" aria-labelledby={"signal-" + binding.bindingId}>
        <figcaption id={"signal-" + binding.bindingId}><strong>{signal.name} {signal.statistic}{signal.unit ? " (" + signal.unit + ")" : ""}</strong>
          · 선택한 구간의 점수를 가장 많이 올린 신호{signal.learned ? " · 띠는 기준 기간 범위" : ""}</figcaption>
        <svg class="signal-chart" viewBox={"0 0 " + W + " " + SH} role="img"
          aria-label={signal.name + " " + signal.statistic + " 추이 · " + place(scale.first) + "부터 " + place(scale.last) + "까지"}>
          <path d={"M" + LEFT + " " + ST + " V" + SB + " H" + RIGHT} class="axis" />
          {#if signal.learned}
            <rect x={LEFT} width={RIGHT - LEFT} y={signalScale.y(signal.learned.high)} height={Math.max(1, signalScale.y(signal.learned.low) - signalScale.y(signal.learned.high))} class="band" />
          {/if}
          {#each yTicks(signalScale.low, signalScale.high, ST, SB, 3) as tick (tick.value)}
            <text x={LEFT - 6} y={tick.y + 4} text-anchor="end" class="label">{measure(tick.value, null)}</text>
          {/each}
          <path d={signalPath} class="line" />
          {#if chosen && signalChosen !== null}
            <line x1={scale.x(chosen.pointer.position)} x2={scale.x(chosen.pointer.position)} y1={ST} y2={SB} class="chosen-line" />
            <circle cx={scale.x(chosen.pointer.position)} cy={signalScale.y(signalChosen)} r="5" class="chosen" />
          {/if}
        </svg>
      </figure>
    {/if}
    {#if inspected && (!pinned || inspected.pointer.position !== selected)}<p class="readout">{place(inspected.pointer.position)} · 점수 {num(inspected.score)} · 기준 {num(inspected.threshold)}{inspected.exceeds === null ? "" : inspected.exceeds ? " · 기준 초과" : " · 기준 이하"}{inspectedRaised ? " · 점수를 가장 많이 올린 신호 " + inspectedRaised : ""}</p>{/if}
    <p class="context">그래프에서 측정 선택 · 아래 띠는 기준을 넘은 측정 비율
      {#if drawn.length<visible.length}전체 기록은 최솟값·최댓값을 보존해 간추렸습니다. 아래 구간을 선택하면 확대합니다.{/if}</p>
    </div>
    <p class="context">분석 {summary?.analyzed}회 · 모델 기준 초과 {summary?.exceeded}회 · 기준 초과 구간 {trend.intervals.length}개{summary?.open ? " (진행 중 " + summary.open + "개)" : ""}{summary?.unjudged ? " · 판정하지 않은 운전 수준 " + summary.unjudged.toLocaleString("ko-KR") + "회" : ""}{summary?.skipped ? " · 분석에서 제외 " + summary.skipped + "회" : ""}{trend.truncated ? " · 기록이 많아 앞부분만 읽었습니다" : ""}</p>
    {#if isTimeWindow(binding.stepKind)}<ModelOperation bindingId={binding.bindingId} levels={binding.levels ?? null} />{/if}
    {#if trend.intervals.length}
      <details><summary>기준 초과 구간 조사 · {trend.intervals.length}개</summary>
      {#if told?.earlier}<p class="context">{told.earlier}{#if story?.first && story.first !== first}
        <button type="button" class="link" onclick={() => {if (story?.first) onSelect(story.first.pointer);}}>그 측정 보기</button>{/if}</p>{/if}
      <ul class="priorities" aria-label="우선 살펴볼 모델 구간">
        {#each priorities as row (row.interval.start)}
          {@const raised = raisedIn(row.interval, 2)}
          <li><strong>{row.label}</strong>
            <span>{place(row.interval.start)} ~ {place(row.interval.end)}</span>
            <span>{row.interval.steps}회 · 최고 점수 {num(row.interval.peak, "기록 없음")}</span>
            {#if raised}<span>점수를 올린 신호 {raised}</span>{/if}
            <button type="button" class="ui-button" onclick={() => inspectInterval(row.interval)}>이 구간 분석 →</button></li>
        {/each}
      </ul>
      <h4>전체 기준 초과 구간 {trend.intervals.length}개</h4>
      <ul class="intervals" aria-label="기준 초과 구간">
        {#each trend.intervals as interval (interval.start)}
          {@const raised = raisedIn(interval, 1)}
          <li>{place(interval.start)} ~ {place(interval.end)} · {interval.steps}회 · 최고 {num(interval.peak, "기록 없음")}{raised ? " · " + raised : ""}{interval.open ? " · 진행 중" : ""}
            <button type="button" class="ui-button" onclick={() => choose(interval.start)}>시작 측정 보기</button></li>
        {/each}
      </ul>
      </details>
    {/if}
  {/if}
</section>

<style>
  .score-cursor{outline-offset:3px;border-radius:3px}.score-cursor:focus-visible{outline:2px solid var(--color-action)}
  .trend { display: grid; gap: var(--space-2); margin-block: 0 var(--space-4); min-width: 0; }
  h3 { margin: 0; font-size: var(--font-section); }
  p { margin: 0; overflow-wrap: anywhere; }
  .context { color: var(--color-ink-muted); font-size: var(--font-small); }
  svg { display: block; width: 100%; height: 300px; }
  .signal { margin: var(--space-3) 0 0; display: grid; gap: var(--space-1); }
  .signal figcaption { font-size: var(--font-small); color: var(--color-ink-muted); }
  .signal figcaption strong { color: var(--color-ink); }
  svg.signal-chart { height: 120px; }
  .band { fill: var(--color-reference-line); fill-opacity: 0.14; }
  .chosen-line { stroke: var(--color-ink-muted); stroke-dasharray: 2 3; }
  .axis { fill: none; stroke: var(--color-border); }
  .grid { stroke: var(--color-border); stroke-opacity: 0.5; }
  .lane { fill: var(--color-surface-selected); }
  .lane-over { fill: var(--color-failure-ink); }
  .threshold { stroke: var(--color-failure-ink); stroke-dasharray: 5 4; }
  .line { fill: none; stroke: var(--color-action); stroke-width: 1.5; }
  .over-line { fill: none; stroke: var(--color-failure-ink); stroke-width: 1.5; }
  .chart { min-width: 0; }
  .chart-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--space-2); }
  .legend { list-style: none; padding: 0; margin: var(--space-2) 0; display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-4); font-size: var(--font-small); color: var(--color-ink-muted); }
  .legend li { display: inline-flex; align-items: center; gap: var(--space-1); }
  .key { display: inline-block; width: 18px; height: 0; border-top: 2px solid var(--color-action); }
  .over-key { border-color: var(--color-failure-ink); }.threshold-key { border-color: var(--color-failure-ink); border-top-style: dashed; }
  .interval-key { height: 10px; border: 0; background: linear-gradient(90deg, color-mix(in srgb, var(--color-failure-ink) 25%, transparent), var(--color-failure-ink)); }
  .inspection-dot { fill: var(--color-action); stroke: var(--color-ink); stroke-width: 2; }
  .readout { padding: var(--space-2); background: var(--color-surface-selected); border-radius: var(--radius-control); font-size: var(--font-small); }
  .onset { display: grid; gap: var(--space-1); }
  .onset .result-statement { margin: 0; }
  .onset-actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2) var(--space-3); font-size: var(--font-small); color: var(--color-ink-muted); }
  .link { border: 0; padding: 0; margin-left: var(--space-2); background: none; color: var(--color-action); font: inherit; text-decoration: underline; cursor: pointer; }
  .onset-line { stroke: var(--color-caution-ink); stroke-width: 2; stroke-dasharray: 3 3; vector-effect: non-scaling-stroke; }
  circle.onset-dot { fill: var(--color-caution-ink); stroke: var(--color-surface); stroke-width: 2; }
  circle { fill: var(--color-action); cursor: pointer; }
  circle.over { fill: var(--color-failure-ink); }
  circle.chosen { stroke: var(--color-ink); stroke-width: 2; }
  .label { font-size: 11px; fill: var(--color-ink-muted); }
  .intervals { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-2); }
  .priorities { list-style: none; margin: var(--space-3) 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fit,minmax(210px,1fr)); gap: var(--space-3); }
  .priorities li { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2) var(--space-3); padding-block: var(--space-2); border-bottom: 1px solid var(--color-border); }
  .priorities span { font-size: var(--font-small); color: var(--color-ink-muted); overflow-wrap: anywhere; }
  .priorities button { justify-self: start; }
  summary { cursor: pointer; color: var(--color-action); font-weight: 650; padding-block: var(--space-3); }
  .intervals li { display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-3); align-items: center; overflow-wrap: anywhere; }
</style>
