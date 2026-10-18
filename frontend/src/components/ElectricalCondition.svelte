<script lang="ts">
  import {onMount, tick} from "svelte";
  import {systemUrl} from "../routes";
  import {
    EXCLUDED_TEXT, METRICS, STATE_TEXT, firstChecks, insights, kstTime, measured, readCondition, segments,
    type Condition, type ConditionPeriod, type ConditionSource, type Metric, type PeriodSummary, type TimelinePoint,
  } from "../electrical-condition";
  import CautionNote from "./CautionNote.svelte";
  import StatusNotice from "./StatusNotice.svelte";

  /** 3-phase load, unbalance and the reference-pattern score of a recent period against an
   * earlier one. A failed or mismatched read clears the earlier result instead of keeping it. */
  type Props = {assetId: string};
  let {assetId}: Props = $props();
  type Analyzed = Extract<Condition, {analyzed: true}>;
  const PERIODS: Record<ConditionPeriod, string> = {"1h": "최근 기록 1시간", "6h": "최근 기록 6시간", "24h": "최근 기록 24시간"};
  // The plot stretches to its box, so every label is page text rather than scaled SVG text.
  const W = 800, H = 200, LEFT = 0, RIGHT = 800, TOP = 6, BOTTOM = 194;
  let period: ConditionPeriod = $state("24h");
  let sources: ConditionSource[] = $state([]);
  let sourceKey = $state("");
  let custom = $state({end: "", referenceStart: "", referenceEnd: ""});
  let condition: Condition | null = $state(null);
  let loadState: "loading" | "ready" | "failed" = $state("loading");
  let error = $state("");
  let metric: Metric = $state("currentMean");
  let selectedAt: string | null = $state(null);
  let detail: HTMLElement | null = $state(null);
  let request: AbortController | null = null;
  const keyOf = (source: ConditionSource) => JSON.stringify([source.sourceId, source.pointId]);

  const analyzed = $derived.by((): Analyzed | null => {
    const current: Condition | null = condition;
    return current && current.analyzed ? current : null;
  });
  const runs = $derived.by((): TimelinePoint[][] => {
    const current: Analyzed | null = analyzed;
    return current ? segments(current.timeline, metric) : [];
  });
  const threshold = $derived.by((): number | null => {
    const current: Analyzed | null = analyzed;
    return metric === "patternScore" && current?.pattern.scored ? current.pattern.threshold : null;
  });
  const scale = $derived.by(() => {
    const current: Analyzed | null = analyzed;
    const values = runs.flat().map((point) => point[metric] as number);
    if (threshold !== null) values.push(threshold);
    const high = values.length ? Math.max(...values) : 1, low = values.length ? Math.min(...values) : 0;
    const pad = Math.max((high - low) * 0.1, 0.01);
    const min = Math.max(0, low - pad), max = high + pad;
    // The plot spans the observations themselves; a few minutes of a 24-hour window fill it.
    const first = current?.timeline[0]?.at, last = current?.timeline[current.timeline.length - 1]?.at;
    const start = first ? Date.parse(first) : 0, end = last && Date.parse(last) > start ? Date.parse(last) : start + 1;
    return {high, low, start, end,
      x: (at: string) => LEFT + ((Date.parse(at) - start) / Math.max(1, end - start)) * (RIGHT - LEFT),
      y: (value: number) => BOTTOM - ((value - min) / (max - min || 1)) * (BOTTOM - TOP)};
  });
  const selectedIndex = $derived(analyzed && selectedAt ? analyzed.timeline.findIndex((point) => point.at === selectedAt) : -1);
  const selected = $derived(analyzed && selectedIndex >= 0 ? analyzed.timeline[selectedIndex] : null);
  const path = (run: TimelinePoint[]) =>
    run.map((point, index) => (index ? "L" : "M") + scale.x(point.at).toFixed(1) + " " + scale.y(point[metric] as number).toFixed(1)).join(" ");

  async function analyze() {
    request?.abort();
    const pending = new AbortController(); request = pending;
    const source = sources.find((item) => keyOf(item) === sourceKey) ?? null;
    loadState = "loading"; condition = null; selectedAt = null; error = "";
    try {
      const value = await readCondition(assetId, period, source, custom, pending.signal);
      if (pending.signal.aborted) return;
      // Keep the chosen source by identity even when a new one changes the list order.
      sources = value.sources;
      if (!value.sources.some((item) => keyOf(item) === sourceKey)) sourceKey = "";
      condition = value; loadState = "ready";
      if (value.analyzed && value.target.currentMean === null) metric = "voltageUnbalance";
    } catch (failure) {
      if (pending.signal.aborted) return;
      condition = null; loadState = "failed";
      error = failure instanceof Error ? failure.message : "분석할 데이터를 읽지 못했습니다.";
    }
  }
  async function choose(at: string, nextMetric: Metric | null = null, focus = true) {
    if (nextMetric) metric = nextMetric;
    selectedAt = at;
    await tick();
    if (focus) detail?.focus({preventScroll: true});
  }
  function scrub(index: number) {
    const point = analyzed?.timeline[index];
    if (point) void choose(point.at, null, false);
  }
  function pick(event: MouseEvent) {
    const current: Analyzed | null = analyzed;
    if (!current?.timeline.length) return;
    const box = (event.currentTarget as SVGElement).getBoundingClientRect();
    const at = scale.start + (((event.clientX - box.left) / box.width * W - LEFT) / (RIGHT - LEFT)) * (scale.end - scale.start);
    const closest = current.timeline.reduce((best, point) =>
      Math.abs(Date.parse(point.at) - at) < Math.abs(Date.parse(best.at) - at) ? point : best);
    void choose(closest.at);
  }
  function excluded(counts: Record<string, number>): string {
    const parts = Object.entries(counts).map(([reason, count]) => (EXCLUDED_TEXT[reason] ?? reason) + " " + count + "개");
    return parts.length ? parts.join(" · ") : "없음";
  }
  onMount(() => { void analyze(); return () => request?.abort(); });
</script>

{#snippet card(title: string, target: number | null, reference: number | null, unit: string)}
  <article class="card"><span>{title}</span><strong>{measured(target, unit)}</strong><small>기준 기간 {measured(reference, unit)}</small></article>
{/snippet}
{#snippet summaryCards(target: PeriodSummary, reference: PeriodSummary)}
  <div class="cards" role="group" aria-label="기준 기간과 비교한 값">
    {@render card("관측 평균 전류", target.currentMean, reference.currentMean, " A")}
    {@render card("전류가 흐른 시간 · 관측 기준", target.currentAboveFloorHours, reference.currentAboveFloorHours, " h")}
    {@render card("전압 불평형 · 최고", target.voltageUnbalanceMax, reference.voltageUnbalanceMax, "%")}
    {@render card("전류 불평형 · 상위 5% 경계", target.currentUnbalanceP95, reference.currentUnbalanceP95, "%")}
  </div>
{/snippet}

<section class="ui-panel condition" aria-labelledby="condition-title">
  <h2 id="condition-title">부하·불평형 변화</h2>
  <p class="context">최근 기간의 3상 전류, 전압·전류 불평형과 기준 패턴과의 차이를 그보다 앞선 기준 기간과 비교합니다.</p>
  <form class="controls" onsubmit={(event) => { event.preventDefault(); void analyze(); }}>
    <label>분석 기간
      <select value={period} onchange={(event) => { period = event.currentTarget.value as ConditionPeriod; void analyze(); }}>
        {#each Object.entries(PERIODS) as [value, label] (value)}<option {value}>{label}</option>{/each}
      </select>
    </label>
    {#if sources.length > 1}
      <label>데이터 출처 · 측정 위치
        <select value={sourceKey} onchange={(event) => { sourceKey = event.currentTarget.value; void analyze(); }}>
          <option value="">데이터 출처 고르기</option>
          {#each sources as source (keyOf(source))}
            <option value={keyOf(source)}>{source.sourceId} · {source.pointId ?? "측정 위치 지정 없음"}</option>
          {/each}
        </select>
      </label>
    {/if}
    <details class="custom">
      <summary>분석·기준 기간 직접 지정</summary>
      <div class="times">
        <label>분석 끝 시각 (KST)<input type="datetime-local" step="1" bind:value={custom.end} /></label>
        <label>기준 기간 시작 (KST)<input type="datetime-local" step="1" bind:value={custom.referenceStart} /></label>
        <label>기준 기간 끝 (KST)<input type="datetime-local" step="1" bind:value={custom.referenceEnd} /></label>
      </div>
      <p class="context">비워 두면 마지막 저장 기록까지와 그 직전 같은 길이의 기간을 비교합니다. 직접 고른 기준 기간은 분석 기간보다 앞서야 합니다.</p>
    </details>
    <button class="ui-button ui-button-primary" type="submit" disabled={loadState === "loading"}>분석하기</button>
  </form>

  {#if loadState === "loading"}
    <StatusNotice message="고른 기간의 3상 측정값을 분석하고 있습니다." />
  {:else if loadState === "failed"}
    <StatusNotice kind="failure" title="부하·불평형을 분석하지 못했습니다" message={error}
      actionLabel="같은 조건으로 다시 분석하기" onAction={() => void analyze()} />
  {:else if condition && !condition.analyzed}
    <StatusNotice kind="uncertain" message={STATE_TEXT[condition.state] ?? "분석할 수 있는 관측이 없습니다."}
      actionLabel={condition.state === "no-history" || condition.state === "unsupported-signals" ? "데이터 연결 확인하기" : undefined}
      actionHref={condition.state === "no-history" || condition.state === "unsupported-signals" ? systemUrl("connections") : undefined} />
  {:else if analyzed}
    <p class="range">분석 기간 {kstTime(analyzed.targetStart)} → {kstTime(analyzed.targetEnd)}
      <span>비교 기준 {kstTime(analyzed.referenceStart)} → {kstTime(analyzed.referenceEnd)}</span></p>
    {@render summaryCards(analyzed.target, analyzed.reference)}

    <section class="block" aria-labelledby="condition-insights">
      <h3 id="condition-insights">기준 기간과 달라진 점</h3>
      <ul>{#each insights(analyzed) as line (line)}<li>{line}</li>{/each}</ul>
    </section>

    <section class="block" aria-labelledby="condition-chart">
      <div class="chart-head">
        <h3 id="condition-chart">어느 시각에 달라졌나</h3>
        <label>그래프 값
          <select bind:value={metric}>
            {#each Object.entries(METRICS) as [value, info] (value)}<option {value}>{info.label}{info.unit ? " ·" + info.unit : ""}</option>{/each}
          </select>
        </label>
      </div>
      {#if !runs.length}
        <p class="context">이 값으로 그릴 관측이 없습니다. 전류가 1A 미만인 관측의 불평형은 계산하지 않습니다.</p>
      {:else}
        <p class="axis-note">최고 {measured(scale.high, METRICS[metric].unit)} · 최저 {measured(scale.low, METRICS[metric].unit)}{#if threshold !== null}<span class="dash"> · 점선: 기준 기간 점수 99% {measured(threshold)}</span>{/if}</p>
        <svg viewBox={"0 0 " + W + " " + H} preserveAspectRatio="none" role="img"
          aria-label={METRICS[metric].label + " · " + kstTime(analyzed.targetStart) + "부터 " + kstTime(analyzed.targetEnd) + "까지. 빠진 값과 시간 공백은 잇지 않습니다."}>
          <path d={"M" + LEFT + " " + TOP + " V" + BOTTOM + " H" + RIGHT} class="axis" />
          {#each runs as run (run[0].at)}<path d={path(run)} class="line" />{/each}
          {#if threshold !== null}
            <line x1={LEFT} x2={RIGHT} y1={scale.y(threshold)} y2={scale.y(threshold)} class="threshold" />
          {/if}
          {#if selected}<line x1={scale.x(selected.at)} x2={scale.x(selected.at)} y1={TOP} y2={BOTTOM} class="chosen" />{/if}
          <rect x={LEFT} y={TOP} width={RIGHT - LEFT} height={BOTTOM - TOP} class="hit" onclick={pick} role="presentation" />
        </svg>
        <p class="axis-time"><span>{kstTime(new Date(scale.start).toISOString())}</span><span>→ {kstTime(new Date(scale.end).toISOString())}</span></p>
        <label class="scrub">시각 고르기
          <input type="range" min="0" max={analyzed.timeline.length - 1} value={Math.max(0, selectedIndex)}
            oninput={(event) => scrub(Number(event.currentTarget.value))} />
        </label>
        <p class="context">그래프를 누르거나 막대를 움직이면 그 시각의 상별 값을 아래에서 봅니다. 시각은 한국 시각입니다.</p>
      {/if}
    </section>

    <section class="block" aria-labelledby="condition-first">
      <h3 id="condition-first">먼저 확인할 시각</h3>
      {#if !(analyzed.pattern.scored && analyzed.pattern.notable.length)}
        <p class="context">{analyzed.pattern.scored ? "기준 점수 범위를 넘은 시각은 없습니다." : "기준 패턴 점수가 없어 벗어남을 평가하지 않았습니다."}
          가장 큰 관측값의 시각을 확인할 수 있습니다.</p>
      {/if}
      <ul class="checks">
        {#each firstChecks(analyzed) as check (check.at + check.label)}
          <li><button type="button" class="ui-button" onclick={() => void choose(check.at, check.metric)}>{check.label} · 확인하기</button>
            {#if check.detail}<span>{check.detail}</span>{/if}</li>
        {/each}
      </ul>
    </section>

    {#if selected}
      <section class="block selected" bind:this={detail} tabindex="-1" aria-labelledby="condition-selected">
        <h3 id="condition-selected">{kstTime(selected.at)} · 측정값</h3>
        <dl>
          {#each Object.entries(METRICS) as [key, info] (key)}
            <div><dt>{info.label}</dt><dd>{measured(selected[key as Metric], info.unit)}</dd></div>
          {/each}
          {#if selected.voltage}<div><dt>전압 R / S / T</dt><dd>{selected.voltage.map((value) => measured(value, " V")).join(" / ")}</dd></div>{/if}
          {#if selected.current}<div><dt>전류 R / S / T</dt><dd>{selected.current.map((value) => measured(value, " A")).join(" / ")}</dd></div>{/if}
        </dl>
        <p class="next">이 시각에 운전 일정이나 부하가 바뀌었는지와 상별 값을 확인하세요. 전압이 평소 범위에서 크게 벗어났다면 원본 값·단위·센서 상태를 먼저 점검하세요.</p>
      </section>
    {/if}

    <details class="tech">
      <summary>기술 상세</summary>
      <dl>
        <div><dt>데이터 출처</dt><dd>{analyzed.sourceId}</dd></div>
        <div><dt>측정 위치</dt><dd>{analyzed.pointId ?? "지정 없음"}</dd></div>
        <div><dt>마지막 관측</dt><dd>{kstTime(analyzed.lastObservedAt)}</dd></div>
        <div><dt>관측 수 · 기준 기간</dt><dd>{measured(analyzed.target.samples)} · {measured(analyzed.reference.samples)}</dd></div>
        <div><dt>전류 관측 시간</dt><dd>{measured(analyzed.target.currentObservedHours, " h")}</dd></div>
        <div><dt>전류가 작아 불평형을 계산하지 않은 관측</dt><dd>{measured(analyzed.target.lowCurrentSamples)}</dd></div>
        <div><dt>제외한 관측</dt><dd>분석 기간 {excluded(analyzed.details.excluded.target)} · 기준 기간 {excluded(analyzed.details.excluded.reference)}</dd></div>
        <div><dt>시각 근거</dt><dd>{analyzed.details.timeEvidence.join(" · ") || "입력의 관측 시각을 그대로 사용 · 장비 시계가 맞는지는 확인하지 않음"}</dd></div>
        <div><dt>센서 품질</dt><dd>{analyzed.details.fileQuality ? "원본 기록에 품질 판정이 없음" : "관측별 원본 상태를 사용"}</dd></div>
        <div><dt>패턴 비교 모델</dt><dd>{analyzed.pattern.scored ? (analyzed.pattern.model ?? "기록 없음") + " · 학습 관측 " + measured(analyzed.pattern.fitSamples) : "기준 데이터 부족으로 실행하지 않음"}</dd></div>
        <div><dt>비교 기준</dt><dd>고른 앞선 기간으로만 학습하고 점수 기준을 계산합니다. 정상 기간으로 확인됐다는 뜻은 아닙니다.</dd></div>
        <div><dt>불평형 계산</dt><dd>세 상 값의 평균에서 가장 먼 값까지의 차이 ÷ 평균 × 100 · 전압 50V 미만, 전류 1A 미만은 제외</dd></div>
        <div><dt>저장 시점</dt><dd>{analyzed.details.snapshotId ?? "기록 없음"}</dd></div>
      </dl>
    </details>
    <CautionNote message="운전 조건이 바뀐 것은 고장이 아닙니다. 기준 기간은 정상으로 확인된 기간이 아니며, 기준 패턴과의 차이도 원인이나 고장을 뜻하지 않습니다." />
  {/if}
</section>

<style>
  .condition { min-width: 0; display: grid; gap: var(--space-4); }
  h2, h3 { margin: 0; }
  h3 { font-size: var(--font-section); overflow-wrap: anywhere; }
  p { margin: 0; overflow-wrap: anywhere; }
  .context { color: var(--color-ink-muted); font-size: var(--font-small); }
  .controls { display: grid; gap: var(--space-3); grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); align-items: end; }
  .controls > details, .controls > button { grid-column: 1 / -1; justify-self: start; }
  .controls > details { justify-self: stretch; }
  label { display: grid; gap: var(--space-2); font-weight: 600; min-width: 0; }
  select, input:not([type="range"]) { min-width: 0; width: 100%; max-width: 100%; padding: var(--space-3); color: var(--color-ink);
    background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-control); }
  summary { cursor: pointer; font-weight: 650; color: var(--color-action); padding-block: var(--space-2); }
  .times { display: grid; gap: var(--space-3); grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); margin-block: var(--space-2); }
  .range { font-weight: 650; display: flex; flex-wrap: wrap; gap: var(--space-1) var(--space-4); }
  .range span { font-weight: 400; color: var(--color-ink-muted); }
  .cards { display: grid; gap: var(--space-3); grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); }
  .card { border: 1px solid var(--color-border); border-radius: var(--radius-control); padding: var(--space-3) var(--space-4);
    display: grid; gap: var(--space-1); min-width: 0; }
  .card span, .card small { color: var(--color-ink-muted); font-size: var(--font-small); overflow-wrap: anywhere; }
  .card strong { font-size: var(--font-section); }
  .block { display: grid; gap: var(--space-2); min-width: 0; }
  .block ul { margin: 0; padding-left: var(--space-5); display: grid; gap: var(--space-1); }
  .chart-head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: end; gap: var(--space-2) var(--space-4); }
  .chart-head label { font-weight: 400; font-size: var(--font-small); }
  svg { width: 100%; height: 200px; display: block; }
  svg :global(path), svg line { vector-effect: non-scaling-stroke; }
  .axis { fill: none; stroke: var(--color-border); }
  .line { fill: none; stroke: var(--color-action); stroke-width: 1.5; }
  .threshold { stroke: var(--color-failure-ink); stroke-dasharray: 5 4; }
  .chosen { stroke: var(--color-ink); stroke-width: 1.5; }
  .hit { fill: transparent; cursor: crosshair; }
  .axis-note, .axis-time { color: var(--color-ink-muted); font-size: var(--font-small); }
  .dash { color: var(--color-failure-ink); }
  .axis-time { display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--space-1) var(--space-3); }
  .scrub { font-weight: 400; font-size: var(--font-small); }
  .scrub input { width: 100%; }
  .block ul.checks { list-style: none; padding: 0; }
  .checks li { display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-3); align-items: center; overflow-wrap: anywhere; }
  .checks span { color: var(--color-ink-muted); font-size: var(--font-small); }
  .selected { border: 1px solid var(--color-border); border-radius: var(--radius-control); padding: var(--space-3) var(--space-4); }
  .selected:focus { outline: 2px solid var(--color-action); outline-offset: 2px; }
  dl { margin: 0; display: grid; gap: var(--space-2); }
  dl div { display: grid; grid-template-columns: minmax(0, 14rem) minmax(0, 1fr); gap: var(--space-3); }
  dt { color: var(--color-ink-muted); font-size: var(--font-small); overflow-wrap: anywhere; }
  dd { margin: 0; overflow-wrap: anywhere; }
  .next { font-size: var(--font-small); }
  @media (max-width: 640px) { dl div { grid-template-columns: minmax(0, 1fr); gap: 0; } }
</style>
