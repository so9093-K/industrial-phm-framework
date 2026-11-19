<script lang="ts">
  import XAxis from "./XAxis.svelte";
  import {measure, niceTicks} from "../chart-axis";
  import {drawTrend, type TrendPoint} from "../model-trend";
  import {measurementScale} from "../time-axis";
  import {bandName} from "../record-findings";
  import {clockText, firstCrossing, focusWindow, spanText, startsZoomed, valueAt, visiblePoints, weekendSpans,
    type Span, type TimelineLane, type TimelineModel, type TimelineOperation, type TimelineOutlook, type TimelinePoint} from "../asset-timeline";

  /** 설비 시간축. 변한 신호들, 운전 상태, 모델 점수를 같은 가로축의 줄로 쌓는다. 한 줄 위에 커서를 올리면
   * 모든 줄의 같은 시점 값이 위 한 줄에 나온다. 무엇이 먼저 변했고 무엇이 함께 변했는지, 그때 어떤 운전 상태였고
   * 모델은 어떻게 반응했는지를 문장 없이 줄을 견줘 읽게 한다. */
  type Props = {
    axis: "time" | "acquisition"; record: Span; episode: Span; ongoing: boolean;
    episodes?: {label: string; selected: boolean; onPick: () => void}[];
    lanes: TimelineLane[]; operation?: TimelineOperation | null; models?: TimelineModel[]; outlook?: TimelineOutlook | null;
    periodSeconds?: number | null; selected?: number | null; onSelect?: (at: number) => void; onFocus?: (key: string) => void;
    compact?: boolean;
  };
  let {axis, record, episode, ongoing, episodes = [], lanes, operation = null, models = [], outlook = null, periodSeconds = null,
    selected = null, onSelect, onFocus, compact = false}: Props = $props();

  const W = 1000;
  let zoomed = $state(false);
  // 시기를 바꾸면 그 시기의 길이에 맞는 보기로 다시 시작한다.
  $effect(() => { zoomed = startsZoomed(record, episode); });
  // 전망이 있으면 가로축이 기록 끝 뒤로 이어진다.
  // 고른 기준선에 닿는 시점이 예측 구간 뒤에 있으면 그 자리까지 축을 늘려 표시가 그래프 안에 들도록 한다.
  const reachSteps = $derived(outlook?.reach && (outlook.reach.state === "expected" || outlook.reach.state === "possible")
    ? (outlook.reach.state === "expected" ? outlook.reach.expected : outlook.reach.earliest) : null);
  const future = $derived(Math.max(outlook?.points.at(-1)?.x ?? record.to, reachSteps !== null ? record.to + reachSteps * 1.05 : record.to));
  const extent = $derived({from: record.from, to: Math.max(record.to, future)});
  const range = $derived(zoomed ? focusWindow(extent, episode) : extent);
  const lo = $derived(range.from), hi = $derived(Math.max(range.to, range.from + 1));
  const X = (at: number) => (at - lo) / (hi - lo) * W;
  const clampX = (at: number) => Math.max(0, Math.min(W, X(at)));
  const weekends = $derived(axis === "time" ? weekendSpans(range) : []);
  const place = (at: number) => axis === "time" ? clockText(at) : Math.round(at) + "번째 측정";
  const episodeText = $derived(axis === "time" ? spanText(episode.from, episode.to) : episode.from + "~" + episode.to + "번째 측정");

  /** 한 줄의 그림: 보이는 값, 세로 범위, 경로. 초기 범위도 세로축 안에 넣어 얼마나 벗어났는지 보이게 한다. */
  function laneShape(lane: TimelineLane, height: number) {
    const points = visiblePoints(lane, range, zoomed);
    const observed = points.map(point => point.value);
    const ahead = lane.focus && outlook ? [
      ...(outlook.trusted ? outlook.points.flatMap(p => [p.estimate, p.lower, p.upper].filter((v): v is number => v !== null)) : []),
      // 안내선은 지금까지 값의 1.5배 안쪽만(멀리 있는 선이 그래프를 납작하게 만들지 않게), 고른 선은 항상.
      ...outlook.guides.filter(g => g.value === outlook!.chosen || Math.abs(g.value) <= 1.5 * Math.max(...observed.map(Math.abs))).map(g => g.value),
    ] : [];
    const values = [...observed, ...ahead];
    const low = Math.min(...values, lane.usual.low), high = Math.max(...values, lane.usual.high);
    const pad = high > low ? (high - low) * 0.1 : Math.max(Math.abs(low) * 0.05, 1);
    const y = (value: number) => height - (value - low + pad) / (high - low + 2 * pad) * height;
    const path = points.map((point, i) => (i && point.join !== false && (point.join === true || axis === "acquisition") ? "L" : "M")
      + X(point.x).toFixed(1) + " " + y(point.value).toFixed(1)).join(" ");
    const ticks = niceTicks(low - pad, high + pad, height > 80 ? 3 : 2).map(value => ({value, top: y(value) / height * 100}))
      .filter(tick => tick.top > 6 && tick.top < 94);
    return {points, y, path, ticks};
  }
  const heightOf = (lane: TimelineLane) => compact ? (lane.focus ? 96 : 56) : (lane.focus ? 120 : 68);

  /** 모델 한 줄: 점수, 기준(점선), 기준을 넘은 부분(빨강), 학습 기간(옅은 띠). 측정이 건너뛴 곳은 잇지 않는다. */
  function modelShape(model: TimelineModel, height: number) {
    const all = model.trend.points.filter(p => p.pointer.position / model.divisor >= lo && p.pointer.position / model.divisor <= hi);
    const drawn = drawTrend(all, 240);
    const values = all.flatMap(p => [p.score, p.threshold].filter((v): v is number => v !== null));
    const low = Math.min(0, ...values), high = Math.max(low + 1e-9, ...values);
    const y = (v: number) => height - 3 - (v - low) / (high - low) * (height - 8);
    let path = "", threshold = "", over = "", previous: TrendPoint | null = null;
    const gap = model.divisor === 1 ? 1 : Infinity;
    for (const point of drawn) {
      const at = X(point.pointer.position / model.divisor);
      if (point.score === null) { previous = null; continue; }
      const joined = previous !== null && (gap === Infinity || point.pointer.position - previous.pointer.position <= gap);
      path += (joined ? "L" : "M") + at.toFixed(1) + " " + y(point.score).toFixed(1) + " ";
      if (point.threshold !== null) threshold += (joined ? "L" : "M") + at.toFixed(1) + " " + y(point.threshold).toFixed(1) + " ";
      if (joined && (point.exceeds || previous!.exceeds))
        over += "M" + X(previous!.pointer.position / model.divisor).toFixed(1) + " " + y(previous!.score!).toFixed(1) + "L" + at.toFixed(1) + " " + y(point.score).toFixed(1) + " ";
      previous = point;
    }
    return {path, threshold, over, all};
  }

  // 운전 수준 색: 정지는 옅은 회색, 부하가 클수록 진하게(한 색의 단계).
  const levelOpacity = (band: number, count: number) => 0.25 + 0.75 * (band - 1) / Math.max(1, count - 1);

  // ── 커서: 줄 어디에 올려도 같은 시점이 모든 줄에 그어지고, 그 시점의 값이 위 한 줄에 나온다.
  let rows: HTMLElement | null = $state(null);
  const plotOf = () => rows?.querySelector<HTMLElement>(".plot") ?? null;
  let hover: number | null = $state(null);
  let pinned: number | null = $state(null);
  const shown = $derived(hover ?? (axis === "acquisition" ? selected : pinned));
  let cursorLeft = $state(0);
  function positionAt(clientX: number): number | null {
    const plot = plotOf();
    if (!plot) return null;
    const rect = plot.getBoundingClientRect();
    const fraction = (clientX - rect.left) / rect.width;
    return fraction < 0 || fraction > 1 ? null : lo + fraction * (hi - lo);
  }
  function snap(at: number): number {
    if (axis === "time") return at;
    const focus = lanes.find(lane => lane.focus) ?? lanes[0];
    return valueAt(focus?.points ?? [], at, Infinity)?.x ?? Math.round(at);
  }
  function move(event: PointerEvent) {
    const at = positionAt(event.clientX);
    hover = at === null ? null : snap(at);
  }
  function choose(event: MouseEvent) {
    const at = positionAt(event.clientX);
    if (at === null) return;
    const chosen = snap(at);
    if (axis === "acquisition") onSelect?.(chosen); else pinned = pinned !== null && Math.abs(X(pinned) - X(chosen)) < 4 ? null : chosen;
  }
  $effect(() => {
    const plotEl = plotOf();
    if (!rows || !plotEl || shown === null) return;
    const outer = rows.getBoundingClientRect(), plot = plotEl.getBoundingClientRect();
    cursorLeft = plot.left - outer.left + (shown - lo) / (hi - lo) * plot.width;
  });

  /** 칸 간격: 가장 가까운 값을 고를 때 이보다 멀면 그 자리엔 값이 없다고 본다. */
  function reachOf(points: TimelinePoint[]): number {
    if (axis === "acquisition") return 1.5;
    const gaps = points.slice(1).map((point, i) => point.x - points[i].x).filter(gap => gap > 0).sort((a, b) => a - b);
    return (gaps[Math.floor(gaps.length / 2)] ?? (hi - lo) / 100) * 1.5;
  }
  /** 위 한 줄: 커서 자리(없으면 기록 마지막)의 각 줄 값. */
  const readout = $derived.by(() => {
    const at = shown ?? record.to;
    const parts: string[] = [];
    for (const lane of lanes) {
      const points = visiblePoints(lane, {from: record.from, to: record.to}, zoomed);
      const found = valueAt(points, at, reachOf(points));
      // 기록 끝에 그 운전 수준의 값이 없으면 '마지막 측정' 줄에서는 빼고, 커서 자리에서는 없다고 쓴다.
      if (found || shown !== null) parts.push(lane.label + " " + (found ? measure(found.value, lane.unit) : "값 없음"));
    }
    if (operation) {
      const column = operation.columns.find(col => col.from <= at && at < col.to) ?? (shown === null ? operation.columns.at(-1) : undefined);
      if (column) {
        const band = column.shares.indexOf(Math.max(...column.shares));
        parts.push(bandName(operation.names, band) + " " + Math.round(column.shares[band] * 100) + "%");
      }
    }
    for (const model of models) {
      const points = model.trend.points.filter(p => p.score !== null);
      const near = points.reduce<TrendPoint | null>((best, p) => !best || Math.abs(p.pointer.position / model.divisor - at)
        < Math.abs(best.pointer.position / model.divisor - at) ? p : best, null);
      const reach = axis === "acquisition" ? 1.5 : reachOf(points.map(p => ({x: p.pointer.position / model.divisor, value: 0})));
      if (near && (shown === null || Math.abs(near.pointer.position / model.divisor - at) <= reach))
        parts.push(model.name + " " + measure(near.score!, null) + (near.threshold !== null ? "(기준 " + measure(near.threshold, null) + ")" : ""));
    }
    return {at: shown === null ? "마지막 측정 · " + place(record.to) : place(at), parts};
  });
  const xScale = $derived(axis === "time" ? {kind: "clock" as const} : measurementScale(periodSeconds));
</script>

<section class="timeline" class:compact aria-label="설비 시간축">
  <header class="head">
    <div class="title">
      <h3>변화 구간 <span>{episodeText}</span></h3>
      <p>{lanes.length > 1 ? "함께 변한 신호 " + lanes.length + "개" : "변한 신호 1개"}{ongoing ? " · 기록 끝까지 이어짐" : ""}</p>
    </div>
    {#if episodes.length > 1}
      <div class="choices" role="group" aria-label="변화 시기">
        {#each episodes as item (item.label)}<button type="button" aria-pressed={item.selected} onclick={item.onPick}>{item.label}</button>{/each}
      </div>
    {/if}
    <div class="choices" role="group" aria-label="보는 범위">
      <button type="button" aria-pressed={zoomed} onclick={() => zoomed = true}>변화 구간 확대</button>
      <button type="button" aria-pressed={!zoomed} onclick={() => zoomed = false}>기록 전체</button>
    </div>
  </header>
  <p class="readout" aria-live="polite"><strong>{readout.at}</strong>{#each readout.parts as part, i (i)}<span>{part}</span>{/each}</p>

  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="rows" bind:this={rows} onpointermove={move} onpointerleave={() => hover = null} onclick={choose}>
    {#each lanes as lane (lane.key)}
      {@const height = heightOf(lane)}
      {@const shape = laneShape(lane, height)}
      <div class="lane-head">
        <button type="button" class="name" aria-pressed={lane.focus} onclick={event => {event.stopPropagation(); onFocus?.(lane.key);}}>{lane.label}</button>
        {#if lane.condition}<span class="condition">{lane.condition} 중의 값</span>{/if}
        {#if lane.decision}<span class="decision-chip">판단 · {lane.decision}</span>{/if}
        <span class="numbers">{lane.numbers}</span>
        {#if lane.focus && outlook && outlook.guides.length}
          {@const chosen = outlook.guides.find(g => g.value === outlook!.chosen) ?? null}
          {@const crossed = chosen ? firstCrossing(lane.points, chosen.value, lane.up) : null}
          <span class="outlook-row">
            <span class="outlook-label">전망 기준선</span>
            <span class="choices small" role="group" aria-label="전망 기준선">
              {#each outlook.guides as guide (guide.value)}<button type="button" aria-pressed={guide.value === outlook.chosen}
                onclick={event => {event.stopPropagation(); outlook!.onGuide(guide.value === outlook!.chosen ? null : guide.value);}}>{guide.label}</button>{/each}
            </span>
            <span class="reach-text">{#if !chosen}{:else if outlook.loading}계산 중{:else if crossed}{chosen.label}({measure(chosen.value, lane.unit)}) · {place(crossed.x)}에서 넘음{:else if outlook.reach && reachSteps !== null}{chosen.label}({measure(chosen.value, lane.unit)}) · {outlook.reach.state === "expected" ? "도달 예상" : "예측 범위로 가장 이르면"} 추가 {reachSteps}{axis === "acquisition" ? "회" : ""} 뒤{:else}{chosen.label}({measure(chosen.value, lane.unit)}) · 전망 기간 안 도달 예상 없음{/if}{#if chosen && !outlook.trusted && !crossed}{" · "}과거 검증에서 예측이 '마지막 값 유지'보다 부정확{/if}</span>
          </span>
        {/if}
      </div>
      <div class="gutter" style:height={height + "px"}>{#each shape.ticks as tick (tick.value)}<span style:top={tick.top + "%"}>{measure(tick.value, null)}</span>{/each}</div>
      <div class="plot" class:focus={lane.focus}>
        <svg viewBox={"0 0 " + W + " " + height} style:height={height + "px"} preserveAspectRatio="none" role="img"
          aria-label={lane.label + " · 회색 띠는 초기 범위, 음영은 변화 구간"}>
          {#each weekends as day (day.from)}<rect x={clampX(day.from)} width={Math.max(0, clampX(day.to) - clampX(day.from))} height={height} class="weekend"/>{/each}
          <rect x="0" width={W} y={shape.y(lane.usual.high)} height={Math.max(1, shape.y(lane.usual.low) - shape.y(lane.usual.high))} class="usual"/>
          <rect x={clampX(lane.interval.from)} width={Math.max(2, clampX(lane.interval.to) - clampX(lane.interval.from))} height={height} class="interval"/>
          {#if lane.focus && outlook}
            {@const tail = X(record.to)}
            <rect x={Math.max(0, tail)} width={Math.max(0, W - Math.max(0, tail))} height={height} class="future"/>
            {#if outlook.trusted && outlook.points.length}
              {@const band = outlook.points.filter(p => p.lower !== null && p.upper !== null)}
              {#if band.length > 1}<path class="forecast-band" d={"M" + band.map(p => X(p.x).toFixed(1) + " " + shape.y(p.upper!).toFixed(1)).join(" L") + " L" + [...band].reverse().map(p => X(p.x).toFixed(1) + " " + shape.y(p.lower!).toFixed(1)).join(" L") + " Z"}/>{/if}
              <path class="forecast" d={"M" + outlook.points.map(p => X(p.x).toFixed(1) + " " + shape.y(p.estimate).toFixed(1)).join(" L")}/>
            {/if}
            {#each outlook.guides as guide (guide.value)}
              {#if guide.value === outlook.chosen || shape.ticks.length === 0 || (shape.y(guide.value) > 0 && shape.y(guide.value) < height)}
                <line x1="0" x2={W} y1={shape.y(guide.value)} y2={shape.y(guide.value)} class="guide" class:chosen={guide.value === outlook.chosen}/>
              {/if}
            {/each}
          {/if}
          <path d={shape.path} class="trace"/>
          {#if shape.points.length <= 160}{#each shape.points as point, i (i)}<circle cx={X(point.x)} cy={shape.y(point.value)} r={lane.focus ? 2.2 : 1.6}/>{/each}{/if}
        </svg>
        {#if lane.focus && outlook}
          {@const tail = Math.max(0, X(record.to)) / W * 100}
          <span class="tag future-tag" style:left={tail + "%"}>{outlook.loading ? "계산 중" : "전망"}</span>
          {#each outlook.guides as guide (guide.value)}
            {@const top = shape.y(guide.value) / height * 100}
            {#if top > 2 && top < 98}<span class="tag guide-tag" class:chosen={guide.value === outlook.chosen} style:top={top + "%"}>{guide.label.replace("초기의 ", "×").replace("배", "")}</span>{/if}
          {/each}
          {#if outlook.chosen !== null}
            {@const crossed = firstCrossing(lane.points, outlook.chosen, lane.up)}
            {@const reach = outlook.reach}
            {#if crossed}
              <i class="reach-line" style:left={clampX(crossed.x) / W * 100 + "%"}></i>
            {:else if reach && reachSteps !== null}
              <i class="reach-line" style:left={clampX(record.to + reachSteps) / W * 100 + "%"}></i>
            {/if}
          {/if}
        {/if}
        {#if lane.focus}
          <span class="tag usual-tag" style:top={shape.y(lane.usual.high) / height * 100 + "%"}>초기 범위</span>
          <span class="tag interval-tag" style:left={clampX(lane.interval.from) / W * 100 + "%"}>{axis === "time" ? clockText(lane.interval.from) : lane.interval.from + "번째"}부터</span>
        {/if}
      </div>
    {/each}

    {#if operation}
      <div class="lane-head">
        <strong class="name static">운전 상태</strong>
        <span class="legend">{#each operation.names.levels as _, i (i)}<i style:opacity={levelOpacity(i + 1, operation.names.levels.length)}></i>{bandName(operation.names, i + 1).replace(" 운전", "")}{/each}<i class="stopped"></i>정지</span>
      </div>
      <div class="gutter" style:height="32px"></div>
      <div class="plot">
        <svg viewBox={"0 0 " + W + " 32"} style:height="32px" preserveAspectRatio="none" role="img" aria-label="시간별 운전 수준 비율">
          {#each operation.columns.filter(col => col.to >= lo && col.from <= hi) as col (col.from)}
            {@const x0 = clampX(col.from)}{@const width = Math.max(0.6, clampX(col.to) - x0)}
            {@const levels = col.shares.slice(1)}
            {#each levels as share, i (i)}
              {@const below = levels.slice(i + 1).reduce((sum, s) => sum + s, 0)}
              {#if share > 0}<rect x={x0} {width} y={32 * below} height={32 * share} class="level" style:opacity={levelOpacity(i + 1, levels.length)}/>{/if}
            {/each}
            {#if col.shares[0] > 0}<rect x={x0} {width} y={32 * (1 - col.shares[0])} height={32 * col.shares[0]} class="stopped"/>{/if}
          {/each}
        </svg>
      </div>
    {/if}

    {#each models as model (model.key)}
      {@const height = compact ? 36 : 44}
      {@const shape = modelShape(model, height)}
      <div class="lane-head">
        <strong class="name static">{model.name}</strong><span class="numbers">{model.count}</span>
        {#if model.shares && operation}
          <span class="shares" aria-label="학습 기간과 변화 구간의 운전 수준 비율">
            {#each [["학습 기간", model.shares.training], ["변화 구간", model.shares.episode]] as [name, shares] (name)}
              <span class="share-row">{name}<span class="bar">{#each (shares as number[]).slice(1) as share, i (i)}<i style:width={share * 100 + "%"} style:opacity={levelOpacity(i + 1, (shares as number[]).length - 1)}></i>{/each}<i class="stopped" style:width={(shares as number[])[0] * 100 + "%"}></i></span></span>
            {/each}
          </span>
        {/if}
      </div>
      <div class="gutter" style:height={height + "px"}></div>
      <div class="plot">
        <svg viewBox={"0 0 " + W + " " + height} style:height={height + "px"} preserveAspectRatio="none" role="img" aria-label={model.name + " 점수와 기준"}>
          {#if model.training && model.training.to >= lo && model.training.from <= hi}
            <rect x={clampX(model.training.from)} width={Math.max(1, clampX(model.training.to) - clampX(model.training.from))} height={height} class="training"/>
          {/if}
          <rect x={clampX(episode.from)} width={Math.max(2, clampX(episode.to) - clampX(episode.from))} height={height} class="interval"/>
          <path d={shape.threshold} class="threshold"/><path d={shape.path} class="score"/><path d={shape.over} class="over"/>
        </svg>
        {#if model.training && model.training.to >= lo && model.training.from <= hi}
          <span class="tag training-tag" style:left={clampX(model.training.from) / W * 100 + "%"}>학습 기간</span>
        {/if}
      </div>
    {/each}

    <div></div>
    <XAxis {lo} {hi} scale={xScale} />
    {#if shown !== null}<i class="cursor" class:pinned={hover === null} style:left={cursorLeft + "px"}></i>{/if}
  </div>
  {#if models.length}<p class="key"><span><i class="k-score"></i>모델 점수</span><span><i class="k-over"></i>기준 넘음</span><span><i class="k-threshold"></i>모델 기준</span>{#if axis === "time" && weekends.length}<span><i class="k-weekend"></i>토·일</span>{/if}</p>{/if}
</section>

<style>
  .timeline { min-width: 0; display: grid; gap: var(--space-2); }
  .head { display: flex; flex-wrap: wrap; align-items: flex-end; gap: var(--space-2) var(--space-4); }
  .title { margin-right: auto; min-width: 0; }
  .title h3 { margin: 0; font-size: var(--font-section); }
  .title h3 span { font-weight: 650; }
  .title p { margin: 2px 0 0; font-size: var(--font-small); color: var(--color-ink-muted); }
  .choices { display: inline-flex; border: 1px solid var(--color-control-border, var(--color-border)); border-radius: var(--radius-control); overflow: hidden; }
  .choices button { font: inherit; font-size: var(--font-small); padding: 5px 10px; border: 0; background: var(--color-surface); color: var(--color-ink); cursor: pointer; }
  .choices button + button { border-left: 1px solid var(--color-border); }
  .choices button[aria-pressed="true"] { background: var(--color-surface-selected); color: var(--color-action); font-weight: 650; }
  .readout { margin: 0; min-height: 1.5em; display: flex; flex-wrap: wrap; gap: 2px var(--space-3); font-size: var(--font-small); font-variant-numeric: tabular-nums; color: var(--color-ink); }
  .readout strong { font-weight: 700; }
  .readout span { color: var(--color-ink-muted); }
  .rows { position: relative; display: grid; grid-template-columns: 56px minmax(0, 1fr); column-gap: 6px; cursor: crosshair; user-select: none; }
  .lane-head { grid-column: 1 / -1; display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px var(--space-3); margin-top: var(--space-3); font-size: var(--font-small); cursor: default; }
  .lane-head:first-child { margin-top: 0; }
  .name { font: inherit; font-weight: 700; color: var(--color-ink); padding: 0; border: 0; background: none; cursor: pointer; border-bottom: 2px solid transparent; }
  .name[aria-pressed="true"] { border-bottom-color: var(--color-action); }
  .name.static { cursor: default; }
  .condition { color: var(--color-ink-muted); }
  .numbers { margin-left: auto; font-variant-numeric: tabular-nums; color: var(--color-ink); }
  .gutter { position: relative; font-size: 11px; color: var(--color-ink-muted); font-variant-numeric: tabular-nums; }
  .gutter span { position: absolute; right: 0; transform: translateY(-50%); white-space: nowrap; }
  .plot { position: relative; min-width: 0; border-bottom: 1px solid var(--color-border); }
  svg { display: block; width: 100%; }
  svg path { vector-effect: non-scaling-stroke; }
  .weekend { fill: var(--color-ink); fill-opacity: .035; }
  .usual { fill: var(--color-ink); fill-opacity: .09; }
  .interval { fill: var(--color-caution-ink); fill-opacity: .14; }
  .trace { fill: none; stroke: var(--color-action); stroke-width: 1.6; }
  .focus .trace { stroke-width: 2; }
  circle { fill: var(--color-action); }
  .level { fill: var(--color-action); }
  .stopped { fill: var(--color-ink); fill-opacity: .06; }
  .training { fill: var(--color-ink); fill-opacity: .07; }
  .score { fill: none; stroke: var(--color-action); stroke-width: 1.5; }
  .over { fill: none; stroke: var(--color-failure-ink); stroke-width: 2; }
  .threshold { fill: none; stroke: var(--color-caution-ink); stroke-width: 1.2; stroke-dasharray: 4 4; }
  .tag { position: absolute; font-size: var(--font-label); pointer-events: none; white-space: nowrap; }
  .usual-tag { left: 4px; transform: translateY(-110%); color: var(--color-ink-muted); }
  .interval-tag { top: 3px; transform: translateX(5px); color: var(--color-caution-ink); font-weight: 650; background: var(--color-surface); padding: 0 4px; border-radius: 3px; }
  .training-tag { top: 2px; transform: translateX(4px); color: var(--color-ink-muted); }
  .future { fill: var(--color-ink); fill-opacity: .03; }
  .forecast { fill: none; stroke: var(--color-action); stroke-width: 1.6; stroke-dasharray: 5 4; }
  .forecast-band { fill: var(--color-action); fill-opacity: .12; stroke: none; }
  .guide { stroke: var(--color-ink-muted); stroke-width: 1; stroke-dasharray: 2 4; vector-effect: non-scaling-stroke; }
  .guide.chosen { stroke: var(--color-failure-ink); stroke-dasharray: 6 3; stroke-width: 1.4; }
  .future-tag { top: 3px; transform: translateX(6px); color: var(--color-ink-muted); }
  .guide-tag { right: 4px; transform: translateY(-100%); color: var(--color-ink-muted); font-size: 11px; }
  .guide-tag.chosen { color: var(--color-failure-ink); font-weight: 650; }
  .outlook-row { flex-basis: 100%; display: flex; flex-wrap: wrap; align-items: center; gap: 4px var(--space-3); }
  .choices.small button { padding: 2px 8px; font-size: var(--font-label); }
  .reach-text { color: var(--color-ink); font-variant-numeric: tabular-nums; }
  .outlook-label { color: var(--color-ink-muted); }
  .decision-chip { font-size: var(--font-label); padding: 0 6px; border-radius: 999px; border: 1px solid var(--color-border); background: var(--color-surface-selected); }
  .training-tag { background: var(--color-surface); padding: 0 3px; border-radius: 3px; }
  .reach-line { position: absolute; top: 0; bottom: 0; border-left: 1.5px dashed var(--color-failure-ink); pointer-events: none; }
  .legend, .shares { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 2px 8px; color: var(--color-ink-muted); }
  .legend i { display: inline-block; width: 10px; height: 10px; margin-right: 3px; background: var(--color-action); vertical-align: middle; }
  .legend i.stopped { background: var(--color-ink); opacity: .08; }
  .shares { margin-left: var(--space-2); font-size: var(--font-label); }
  .share-row { display: inline-flex; align-items: center; gap: 4px; }
  .bar { display: inline-flex; width: 96px; height: 10px; border: 1px solid var(--color-border); }
  .bar i { display: block; height: 100%; background: var(--color-action); }
  .bar i.stopped { background: var(--color-ink); opacity: .08; }
  .cursor { position: absolute; top: 0; bottom: 1.6em; width: 0; border-left: 1px solid var(--color-ink); opacity: .55; pointer-events: none; }
  .cursor.pinned { border-left-style: dashed; opacity: .8; }
  .key { margin: 0; display: flex; flex-wrap: wrap; gap: var(--space-3); font-size: var(--font-label); color: var(--color-ink-muted); }
  .key i { display: inline-block; width: 16px; border-top: 2px solid; vertical-align: middle; margin-right: 4px; }
  .k-score { border-color: var(--color-action); } .k-over { border-color: var(--color-failure-ink); }
  .k-threshold { border-color: var(--color-caution-ink); border-top-style: dashed !important; }
  .k-weekend { height: 10px; border: 0 !important; background: var(--color-ink); opacity: .08; }
  .compact .lane-head { margin-top: var(--space-2); }
</style>
