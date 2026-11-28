<script lang="ts">
  import {untrack} from "svelte";
  import {clockText} from "../date-format";
  import {ongoing, pointInBucket, visibleSeries, SERIES_COLORS, type FleetGroup, type FleetRead} from "../fleet-observation";
  import {measure} from "../chart-axis";
  import {plainLabel} from "../change-story";
  import {flowLabel} from "../monitor";
  import {changeRange, type ChangeActivity, type MonitorChatPoint} from "../monitor-activity";
  import {elapsedText} from "../time-axis";
  import AssetName from "./AssetName.svelte";
  import TrendChart from "./TrendChart.svelte";

  let {name, flow, role = null, read, group, href, activity, selected, replaying, until, analyzed, readingChanges = false, analysisFailed, lo, hi, height, playing, onQuestion, onPoint, onPause, onSignal}: {
    name: string; flow: string; read: FleetRead; group: FleetGroup; href: string; activity: ChangeActivity | null; selected: boolean;
    /** 설비가 하는 일(한 줄): '압축공기 공급', '회전축 지지'. 모르면 null. */
    role?: string | null;
    /** 재생 중이면 위치(시각 또는 측정 번호, 기록 시작 전이면 null)와 그 위치까지 판정한 변화. */
    replaying: boolean; until: number | null; analyzed: number | null; readingChanges?: boolean; analysisFailed: boolean;
    lo: number; hi: number; height: number; playing: boolean;
    onQuestion: (activity: ChangeActivity, point: MonitorChatPoint | null) => void;
    onPoint: (point: MonitorChatPoint | null) => void;
    onPause: () => void; onSignal: (channel: string) => void} = $props();
  let picked = $state<number | null>(null);
  let hovered = $state<number | null>(null);
  const cursor = $derived(hovered ?? picked);
  $effect(() => {
    if (playing) hovered = null;
    if (picked !== null && (playing || picked < lo || picked > hi)) untrack(() => pick(null));
  });
  const series = $derived(!replaying ? group.series : until === null ? group.series.map(row => ({...row, points: []})) : visibleSeries(group, until));
  const lead = $derived(activity?.change ?? null);
  const changeName = $derived(lead ? plainLabel(lead.label, lead.channel) : null);
  // 변화 구간이 기록 끝(재생 중이면 판정한 위치)에 닿는지에 따라 강조를 조절한다.
  const judgedUntil = $derived(replaying ? analyzed ?? until ?? group.record.to : group.record.to);
  const continuing = $derived(lead ? ongoing(group, [lead], judgedUntil) : false);
  // 재생 중 판정은 화면 위치보다 늦게 도착한다. 따라오기 전에는 '없음'이라고 하지 않는다.
  const lagging = $derived(replaying && analyzed !== null && until !== null
    && analyzed < until - (group.axis === "time" ? (group.bucketMs ?? 60_000) * 1.5 : 1));
  // Use the synchronized server observation that selected the representative axis.
  const now = $derived(lead?.current ?? null);
  const shownBefore = $derived(now?.reference ?? lead?.before ?? null);
  const shownAfter = $derived(now?.value ?? lead?.after ?? null);
  const lastFocus = $derived(series.find(row => row.key === group.focus)?.points.at(-1));
  const readAt = $derived(cursor ?? lastFocus?.x ?? null);
  const stamp = $derived(cursor === null && lastFocus && group.axis === "time"
    ? Math.min(until ?? group.record.to, lastFocus.x + (group.bucketMs ?? 0)) : readAt);
  const other = $derived([...read.others].sort((a, b) => b.from - a.from)[0]);

  const short = (at: number) => group.axis === "time" ? clockText(at)
    : Math.floor(at) + "번째" + (group.periodSeconds ? " · " + elapsedText((Math.floor(at) - 1) * group.periodSeconds) : "");
  // 부하 신호(전류): 전압 그래프 바로 아래 같은 시간축에. 모니터링 중이면 같은 시점까지만 그린다.
  const companion = $derived(read.companion);
  const load = $derived(!companion ? [] : !replaying ? companion.series : until === null ? companion.series.map(row => ({...row, points: []})) : visibleSeries(companion, until));
  const compact = $derived(lead && !continuing && !replaying && !read.live);
  const plotHeight = $derived(compact ? Math.min(height, 168) : height);
  const mainHeight = $derived(companion ? Math.round(plotHeight * .68) : plotHeight);
  const loadHeight = $derived(companion ? Math.max(42, plotHeight - mainHeight - 20) : 0);
  const loadPoint = $derived(readAt !== null && load[0] ? pointInBucket(load[0].points, readAt, companion?.bucketMs ?? null) : null);
  const distinctLines = $derived(group.axis === "time" && series.length === 3);
  const onsetLink = $derived(lead && activity && lead.from >= lo && lead.from <= hi && series.some(row => row.points.length)
    ? {href: activity.href, label: name + " 변화 구간 조사", title: short(lead.from) + "부터의 변화 조사", onOpen: onPause} : undefined);
  function chatPoint(at: number | null): MonitorChatPoint | null {
    if (at === null) return null;
    const label = group.axis === "time" ? clockText(at) : Math.floor(at) + "번째 측정";
    return {point: {at, axis: group.axis, label}, clear: () => { if (picked === at) picked = null; }};
  }
  function pick(at: number | null) {
    picked = at;
    hovered = null;
    if (selected) onPoint(chatPoint(at));
    if (at !== null) onPause();
  }
</script>

<li class="row" class:selected class:compact>
  <div class="card-main">
    <div class="summary">
      <header class="equipment-head">
        <div class="title"><a class="name" href={activity?.href ?? href} onclick={onPause}><AssetName label={name}/></a>
          {#if role || read.live}<span class="kind">{[role, read.live ? flowLabel(flow) : null].filter(Boolean).join(" · ")}</span>{/if}</div>
      </header>
      {#if lead}
        <section class="finding" class:ended={!continuing} aria-label="이 그래프의 특이사항">
          <div class="change-copy">
            <!-- 지금도 이어지는지는 제목 줄에 둔다. 범위만 적으면 베어링이 지금도 오르는 중이라는 것이 그래프로만 읽혔다. -->
            <span class="change-head"><strong>{changeName} <span class="keep">{now ? "초기의 약 " + now.ratioLabel : lead.up ? "초기보다 높아짐" : "초기보다 낮아짐"}</span></strong>
              <span class="state" class:ongoing={continuing}>{continuing ? "이어짐" : "끝남"}</span></span>
            <span class="change-values">
              {#if shownBefore !== null && shownAfter !== null}
                <b>{measure(shownBefore, group.unit, 3)} → {measure(shownAfter, group.unit, 3)}</b>
              {/if}
              <small>
                {changeRange(lead, group.axis)}{#if group.axis === "time" && lead.to > lead.from} <span class="keep">({elapsedText((lead.to - lead.from) / 1000)})</span>{/if}
              </small>
            </span>
            {#if lead.load}<small class="change-values">같은 기간 {lead.load.label} {measure(lead.load.before, null, 3)} → {measure(lead.load.after, lead.load.unit, 3)}</small>{/if}
          </div>
          <div class="finding-actions">
            {#if activity?.question}
              <button type="button" class="ui-button ai" onclick={() => onQuestion(activity!, chatPoint(picked))}>
                <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2.5 3.5h11v7h-6l-3 2.5v-2.5h-2z"/></svg>AI에게 질문</button>
            {/if}
            {#if !onsetLink}<a class="ui-button ui-button-primary investigate" href={activity?.href ?? href} onclick={onPause} aria-label={name + " 변화 구간 조사"}>변화 구간 조사 →</a>{/if}
          </div>
        </section>
      {/if}
      {#if analysisFailed || !lead || (!replaying && other)}<footer class="row-footer">
        {#if analysisFailed}<span role="status">이 모니터링 시점의 특이사항을 읽지 못했습니다</span>
        {:else if !lead}<span>{readingChanges || (replaying && (analyzed === null || lagging)) ? "특이사항을 찾고 있습니다"
          : replaying ? "지금까지 특이사항 없음" : "이 기록에는 특이사항이 없습니다"}</span>
          <a class="secondary-action" {href} onclick={onPause}>기록 살펴보기 →</a>{/if}
        {#if !replaying && other}
          <button type="button" class="secondary-action" onclick={() => onSignal(other.channel)}>다른 특이사항 {read.others.length}개</button>
        {/if}
      </footer>{/if}
    </div>
    <div class="plot-area">
      <div class="plot-title">
        <h2>{plainLabel(group.label, group.focus)}{group.unit ? " · " + group.unit : ""}</h2>
        <div class="reading">
          {#if stamp !== null}
            <span>{group.axis === "time" ? (cursor === null ? "마지막 구간 평균" : "구간 평균")
              : (cursor === null ? "마지막 측정" : "선택 측정")}</span>
            <span class="stamp">{short(stamp)}</span>
          {:else}<span>표시할 측정 없음</span>{/if}
          {#if picked !== null}<button type="button" class="clear-pick" onclick={() => pick(null)}>선택 해제</button>{/if}
        </div>
        {#if lead && shownBefore !== null}<span class="reference-key"><i></i>초기 수준</span>{/if}
      </div>
      <div class="chart-readings">
        <dl class="values">
          {#each series as row,index(row.key)}
            {@const point=readAt===null?null:pointInBucket(row.points,readAt,group.bucketMs)}
            <div><dt><i aria-hidden="true" style:--series={SERIES_COLORS[index%SERIES_COLORS.length]}
              class:dashed={distinctLines && index === 1} class:dotted={distinctLines && index === 2}></i>{series.length>1?row.short:group.label}</dt>
              <dd title={point?"":"해당 구간에 측정값 없음"}>{point?measure(point.value,group.unit,group.unit==="V"?4:3):"—"}</dd></div>
          {/each}
          {#if companion}<div class="load"><dt><i aria-hidden="true" style:--series="var(--color-ink-muted)"></i>{companion.label}</dt><dd title={loadPoint?"":"해당 구간에 측정값 없음"}>{loadPoint?measure(loadPoint.value,companion.unit,3):"—"}</dd></div>{/if}
        </dl>
      </div>
      <!-- 그래프에 카드와 같은 특이사항 구간을 표시한다. -->
      <TrendChart {group} {series} {lo} {hi} changes={lead ? [lead] : []} selectedRange={selected} reference={shownBefore} live={replaying && playing}
        height={mainHeight} axis={!companion} guide={cursor} guideSamples {distinctLines} {onsetLink} endLabel
        formatValue={short} onHover={at => hovered = at} bind:picked={() => picked, pick}/>
      {#if companion}
        <p class="load-label">{companion.label}</p>
        <TrendChart group={companion} series={load} {lo} {hi} changes={lead ? [{...lead, key: "load:" + lead.key}] : []}
          height={loadHeight} colors={["var(--color-ink-muted)"]} selectedRange={selected} endLabel guide={cursor} guideSamples live={replaying && playing}
          formatValue={short} onHover={at => hovered = at} bind:picked={() => picked, pick}/>
      {/if}
    </div>
  </div>
</li>

<style>
  .row {
    display:grid; gap:20px; min-width:0; list-style:none; padding:18px 20px;
    background:var(--color-surface); border:1px solid var(--color-border); border-radius:10px;
  }
  .row.compact {padding-block:12px}
  .row.compact .summary{gap:8px}.row.compact .finding{gap:6px;padding-block:7px}
  .row.selected { border-color:var(--color-action); }
  .card-main { display:grid; grid-template-columns:clamp(215px, 34%, 300px) minmax(0,1fr); gap:12px 28px; min-width:0; align-items:start; }
  .summary { display:grid; gap:12px; min-width:0; align-content:start; }
  .equipment-head { display:grid; gap:3px; }
  .title { display:flex; align-items:baseline; gap:8px; min-width:0; }
  .name { font-size:1.1rem; font-weight:700; color:var(--color-ink); text-decoration:none; }
  .name:hover { text-decoration:underline; }
  .kind,.reading { font-size:var(--font-label); color:var(--color-ink-muted); }
  .reading { display:flex; flex-wrap:wrap; gap:4px 8px; align-items:center; }
  .reading .stamp { color:var(--color-ink); font-weight:600; font-variant-numeric:tabular-nums; }
  .clear-pick,.secondary-action {
    font:inherit; font-size:var(--font-label); color:var(--color-action); border:0; background:none;
    padding:0; cursor:pointer; text-decoration:none;
  }
  .clear-pick:hover,.secondary-action:hover { text-decoration:underline; }
  .values { display:flex; flex-wrap:wrap; gap:4px 14px; margin:0; }
  .values > div,.values dt { display:flex; align-items:baseline; gap:5px; }
  .values dt { font-size:var(--font-label); color:var(--color-ink-muted); }
  .values dt i { align-self:center; width:14px; border-top:2px solid var(--series); }
  .values dt i.dashed { border-top-style:dashed; }
  .values dt i.dotted { border-top-style:dotted; }
  .values dd { margin:0; font-size:var(--font-small); font-weight:650; font-variant-numeric:tabular-nums; }
  .chart-readings { margin:0 0 8px 52px; }
  .chart-readings .values { gap:2px 12px; }
  .finding {
    display:grid; gap:10px;
    padding:10px 12px; border-left:3px solid var(--color-change-mark);
    background:var(--color-uncertain-surface); border-radius:0 6px 6px 0;
  }
  .finding.ended { border-left-color:var(--color-border); background:var(--color-surface-selected); }
  .change-copy { display:grid; gap:2px; min-width:0; font-size:var(--font-small); }
  .change-values { display:flex; align-items:baseline; flex-wrap:wrap; gap:2px 10px; }
  .change-values b { font-variant-numeric:tabular-nums; font-size:1rem; }
  /* 사실을 담은 글씨는 13px 아래로 내리지 않는다(한글은 11~12px에서 읽기 힘들다). */
  .change-values small { color:var(--color-ink-muted); font-size:var(--font-label); }
  .change-head { display:flex; align-items:baseline; justify-content:space-between; gap:8px; }
  .keep { white-space:nowrap; }
  .state { flex:none; padding:1px 8px; border-radius:999px; font-size:var(--font-label); font-weight:650;
    color:var(--color-ink-muted); background:var(--color-surface); border:1px solid var(--color-border); }
  .state.ongoing { color:var(--color-caution-ink); border-color:var(--color-change-mark); }
  .finding-actions { display:flex; align-items:center; flex-wrap:wrap; gap:6px; }
  .finding-actions .ui-button { display:inline-flex; align-items:center; gap:6px; min-height:34px; padding:5px 9px; font-size:var(--font-label); font-weight:650; white-space:nowrap; text-decoration:none; }
  .ai { color:var(--color-action); }
  .ai svg { width:14px; height:14px; fill:none; stroke:currentColor; stroke-width:1.5; stroke-linejoin:round; }
  .plot-area { min-width:0; }
  .plot-area :global(.plotted) { grid-template-columns:44px minmax(0,1fr); }
  .plot-title { display:flex; flex-wrap:wrap; align-items:baseline; gap:2px 12px; margin:0 0 5px; }
  .plot-title h2 { margin:0; font-size:var(--font-small); }
  .reference-key { display:flex; align-items:center; gap:5px; margin-inline-start:auto; font-size:var(--font-label); color:var(--color-ink-muted); }
  .reference-key i { width:14px; border-top:1px dashed var(--color-reference-line); }
  .load-label { margin:5px 0 4px 52px; font-size:var(--font-label); color:var(--color-ink-muted); }
  .row-footer { display:flex; align-items:center; flex-wrap:wrap; min-height:20px; gap:6px 16px; font-size:var(--font-label); color:var(--color-ink-muted); }
  @media(max-width:1000px) { .card-main { grid-template-columns:minmax(0,1fr); } }
  @media(max-width:500px) { .row { padding:14px; } }
</style>
