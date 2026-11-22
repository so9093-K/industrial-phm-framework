<script lang="ts">
  import {aiInvestigationHref, investigationHref, latestEpisode, ongoing, visibleSeries, SERIES_COLORS, type FleetChange, type FleetGroup, type FleetRead} from "../fleet-observation";
  import {measure} from "../chart-axis";
  import {clockText, episodes} from "../asset-timeline";
  import {versusStart} from "../change-story";
  import {DECISION_LABEL} from "../review-writes";
  import {elapsedText} from "../time-axis";
  import AssetName from "./AssetName.svelte";
  import TrendChart from "./TrendChart.svelte";

  /** 데이터셋 관제의 한 줄: 왼쪽 이름·조건·마지막 값, 가운데 추이, 오른쪽 AI 관제.
   * AI 관제는 지금까지 확인한 범위에서 찾은 변화를 시각순으로 알린다: 가장 최근 변화와 같은 때의 부하,
   * 그 앞의 변화 몇 개. 'AI 조사'는 그 변화를 판정한 위치의 조사 화면을 열고 AI 조사를 바로 시작한다.
   * 부모가 읽기를 끝낸 줄에만 쓴다(묶음이 없거나 다시 읽는 중이면 부모가 대신 자리를 그린다). */
  let {assetId, name, detail, read, group, replaying, until, found, analyzed, lo, hi, shared, height, playing, onPause, onSignal}: {
    assetId: string; name: string; detail: string | null; read: FleetRead; group: FleetGroup;
    /** 재생 중이면 위치(시각 또는 측정 번호, 기록 시작 전이면 null)와 그 위치까지 판정한 변화. */
    replaying: boolean; until: number | null; found: FleetChange[]; analyzed: number | null;
    lo: number; hi: number; shared: boolean; height: number; playing: boolean;
    onPause: () => void; onSignal: (channel: string) => void} = $props();
  let picked: number | null = $state(null), cursor: number | null = $state(null);

  const series = $derived(!replaying ? group.series : until === null ? group.series.map(row => ({...row, points: []})) : visibleSeries(group, until));
  const changes = $derived((replaying ? found : read.changes).filter(row => until !== null && row.from <= until).map(row => ({...row, to: Math.min(row.to, until!)})));
  const episode = $derived(latestEpisode(changes));
  const lead = $derived(episode.find(row => row.key === group.focus) ?? episode[0]);
  const still = $derived(lead ? ongoing(group, changes, until ?? group.record.to) : false);
  const reach = $derived(group.axis === "time" ? (group.bucketMs ?? 60_000) : 1);
  const lastFocus = $derived(series.find(row => row.key === group.focus)?.points.at(-1));
  const other = $derived([...read.others].sort((a, b) => b.from - a.from)[0]);
  const href = (change?: FleetChange) => read.live ? read.href : investigationHref(assetId, group, replaying ? until : null, change);

  const short = (at: number) => group.axis === "time" ? clockText(at)
    : Math.floor(at) + "번째" + (group.periodSeconds ? " · " + elapsedText((Math.floor(at) - 1) * group.periodSeconds) : "");
  /** 'R상·S상·T상' → 'R·S·T상'. */
  const together = (names: string[]) => names.length > 1 && names.every(item => item.endsWith("상"))
    ? names.map(item => item.slice(0, -1)).join("·") + "상" : names.join("·");
  function nearest(points: {x: number; value: number}[], at: number) {
    let best: {x: number; value: number} | null = null;
    for (const point of points) if (!best || Math.abs(point.x - at) < Math.abs(best.x - at)) best = point;
    return best && Math.abs(best.x - at) <= reach ? best : null;
  }
  const duration = (change: FleetChange) => group.axis === "time" ? elapsedText((change.to - change.from) / 1000) : (change.to - change.from + 1) + "회 측정";
  const members = $derived(series.filter(row => episode.some(change => change.key === row.key)).map(row => row.short));
  // 부하 신호(전류): 전압 그래프 바로 아래 같은 시간축에. 모니터링 중이면 같은 시점까지만 그린다.
  const companion = $derived(read.companion);
  const load = $derived(!companion ? [] : !replaying ? companion.series : until === null ? companion.series.map(row => ({...row, points: []})) : visibleSeries(companion, until));
  const mainHeight = $derived(companion ? Math.round(height * .68) : height);
  const loadHeight = $derived(companion ? Math.max(48, height - mainHeight - 20) : 0);
  const loadPoint = $derived(load[0] ? (cursor !== null ? nearest(load[0].points, cursor) : load[0].points.at(-1)) : null);
  // 앞서 찾은 변화(가장 최근 시기 앞의 시기들): 최근 것부터 두 개까지.
  const earlier = $derived(episodes(changes, change => change).slice(0, -1).reverse().slice(0, 2)
    .map(span => span.members.find(row => row.key === group.focus) ?? span.members[0]));
  const named = (episode: FleetChange[], change: FleetChange) => {
    const names = series.filter(row => episode.some(item => item.key === row.key)).map(row => row.short);
    return series.length > 1 && names.length ? together(names) + " " + group.label : change.label;
  };
  // 남긴 판단: 같은 특이사항(기간·기준이 같은 것)에만 붙인다. 모니터링 중에는 기간이 잘려 다른 특이사항이 되므로
  // 판단이 없다고 '판단 전'이라 말하지 않는다.
  const judgmentOf = (change: FleetChange) => change.reviewKey ? read.judgments?.[change.reviewKey] ?? null : null;
  const judged = $derived(lead ? judgmentOf(lead) : null);
  const day = (at: string) => new Date(at).toLocaleDateString("ko-KR", {month: "long", day: "numeric"});
  const verdict = (change: FleetChange) => {
    const own = judgmentOf(change);
    return own?.closed ? "검토 종료" : own?.decision ? DECISION_LABEL[own.decision] : own ? "확인함" : null;
  };
  const watched = $derived(read.live ? "최근 관측 확인" : !replaying ? "기록 전체 확인" : analyzed === null ? "변화 판정 중" : "~" + short(analyzed) + "까지 확인");
</script>

<li class="row" class:ongoing={still} style:--row={height + (shared ? 26 : 50) + "px"}>
  <div class="who">
    <a class="name" href={href()} onclick={onPause}><AssetName label={name}/></a>
    {#if detail || read.live}<span class="detail">{detail ?? ""}{detail && read.live ? " · " : ""}{read.live ? "수신 중" : ""}</span>{/if}
    <dl class="values">
      {#each series as row, index (row.key)}
        {@const point = cursor !== null ? nearest(row.points, cursor) : row.points.at(-1)}
        <div><dt><i style:background={SERIES_COLORS[index % SERIES_COLORS.length]}></i>{series.length > 1 ? row.short : group.label}</dt><dd>{point ? measure(point.value, group.unit, 4) : "—"}</dd></div>
      {/each}
      {#if companion}<div class="load"><dt><i></i>{companion.label}</dt><dd>{loadPoint ? measure(loadPoint.value, companion.unit, 3) : "—"}</dd></div>{/if}
    </dl>
    <span class="time">{#if cursor !== null}{short(cursor)}{#if picked !== null} <button type="button" aria-label="고른 시점 해제" onclick={() => picked = null}>×</button>{/if}
      {:else if lastFocus}{replaying ? "모니터링 시점 " : "마지막 "}{short(group.axis === "time" ? Math.min(until ?? group.record.to, lastFocus.x + (group.bucketMs ?? 0)) : lastFocus.x)}
      {:else}기록 시작 전{/if}</span>
  </div>
  <div class="chart">
    <TrendChart {group} {series} {lo} {hi} {changes} reference={lead?.before ?? null} live={replaying && playing} height={mainHeight} axis={!shared && !companion}
      bind:picked={() => picked, value => { picked = value; if (value !== null) onPause(); }} bind:cursor/>
    {#if companion}
      <p class="load-label">{companion.label}</p>
      <TrendChart group={companion} series={load} {lo} {hi} changes={changes.map(row => ({...row, key: "load:" + row.key}))} height={loadHeight} axis={!shared}
        colors={["var(--color-ink-muted)"]} guide={cursor} bind:cursor/>
    {/if}
  </div>
  <div class="fact">
    <p class="watch"><span class="avatar" aria-hidden="true">AI</span><b>AI 관제</b><span>{watched}</span></p>
    {#if lead}
      {#key lead.key + lead.from}
        <article class="notice" class:settled={!!judged} aria-label="AI 관제가 찾은 특이사항">
          {#if judged}<span class="verdict"><b>{verdict(lead)}</b> · {day(judged.at)}</span>
          {:else if !replaying && !read.live}<span class="verdict pending">판단 전</span>{/if}
          <span class="when">{group.axis === "time" ? clockText(lead.from) : lead.from + "번째 측정"}부터 · {still ? "마지막 측정까지 이어짐" : duration(lead)}</span>
          <strong class="what">{named(episode, lead)}</strong>
          <span class="size">{lead.before !== null && lead.after !== null ? versusStart(lead.after, lead.before, group.unit) : lead.up ? "높음" : "낮음"}</span>
          {#if lead.before !== null && lead.after !== null}<span class="numbers">{measure(lead.before, group.unit, 3)} → {measure(lead.after, group.unit, 3)}</span>{/if}
          {#if lead.load}<span class="load-fact">같은 때 {lead.load.label} {measure(lead.load.before, lead.load.unit, 2)} → {measure(lead.load.after, lead.load.unit, 2)}</span>{/if}
          {#if judged?.note}<span class="memo" title={judged.note}>메모 · {judged.note}</span>{/if}
          <div class="act">
            {#if !read.live}<a class="ai-start" href={aiInvestigationHref(assetId, group, replaying ? analyzed : null, lead)} onclick={onPause} aria-label={name + " 변화 AI 조사"}>
              <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2.5 3.5h11v7h-6l-3 2.5v-2.5h-2z"/></svg>AI 조사</a>{/if}
            <a class="open" href={href(lead)} onclick={onPause} aria-label={name + " 변화 조사"}>조사 →</a>
          </div>
        </article>
      {/key}
      {#each earlier as change (change.key + change.from)}
        <span class="earlier">{group.axis === "time" ? clockText(change.from) : change.from + "번째"} · {change.label} {change.up ? "높음" : "낮음"}{verdict(change) ? " · " + verdict(change) : ""}</span>
      {/each}
    {:else}
      <div class="head"><span class="calm">{replaying && analyzed === null ? "변화 판정 중" : read.live ? "앞선 관측과 달라진 구간 없음" : "기록 앞부분과 달라진 구간 없음"}</span>
        <a class="open" href={href()} onclick={onPause} aria-label={name + " 측정 보기"}>보기 →</a></div>
    {/if}
    {#if !replaying && other}
      <button type="button" class="other" onclick={() => onSignal(other.channel)} title="보는 신호를 {other.label}(으)로 바꾸기">
        다른 신호 · {other.label} {group.axis === "time" ? clockText(other.from).replace(/ \d\d:\d\d$/, "") : other.from + "번째"}{read.others.length > 1 ? " 외 " + (read.others.length - 1) : ""}</button>
    {/if}
  </div>
</li>

<style>
  .row{display:grid;grid-template-columns:220px minmax(0,1fr) 250px;gap:20px;height:var(--row);padding:10px 20px;background:var(--color-surface);border:1px solid var(--color-border);border-left:4px solid transparent;border-radius:8px;align-items:stretch;box-sizing:border-box}
  .row.ongoing{border-left-color:var(--color-change-mark)}
  .who{display:flex;flex-direction:column;gap:4px;min-width:0}
  .name{font-weight:650;font-size:1rem;color:var(--color-ink);text-decoration:none}
  a.name:hover{text-decoration:underline}
  .detail{font-size:var(--font-label);color:var(--color-ink-muted)}
  .values{display:grid;gap:2px;margin:6px 0 0}
  .values div{display:grid;grid-template-columns:52px auto;align-items:baseline;gap:8px}
  .values dt{display:flex;align-items:center;gap:6px;font-size:var(--font-label);color:var(--color-ink-muted)}
  .values dt i{display:inline-block;width:12px;height:3px;border-radius:2px}
  .values dd{margin:0;font-size:1.05rem;font-weight:650;font-variant-numeric:tabular-nums}
  .values .load{margin-top:4px;grid-template-columns:max-content auto}.values .load dt{white-space:nowrap}.values .load dt i{background:var(--color-ink-muted)}.values .load dd{font-size:var(--font-small);font-weight:600}
  .load-label{margin:2px 0 0 52px;font-size:var(--font-label);color:var(--color-ink-muted)}
  .time{margin-top:auto;font-size:12px;color:var(--color-ink-muted);font-variant-numeric:tabular-nums;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .time button{border:0;background:none;color:var(--color-ink-muted);cursor:pointer;font-size:14px;padding:0 2px}
  .chart{min-width:0;align-self:center}
  /* 세로 눈금 칸 폭을 고정해 줄마다 그래프 시작이 같고 위의 공유 가로축과 맞는다. */
  .chart :global(.plotted){grid-template-columns:44px minmax(0,1fr)}
  .fact{display:flex;flex-direction:column;gap:6px;min-width:0;font-size:var(--font-small);overflow:hidden}
  .head{display:flex;align-items:baseline;justify-content:space-between;gap:8px}
  .watch{display:flex;align-items:center;gap:6px;margin:0;font-size:12px;color:var(--color-ink-muted);font-variant-numeric:tabular-nums;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .watch b{color:var(--color-ink);font-weight:650}
  .avatar{flex:none;display:grid;place-items:center;width:20px;height:20px;border-radius:50%;background:var(--color-action);color:#fff;font-size:9px;font-weight:700}
  .notice{display:flex;flex-direction:column;gap:2px;padding:8px 10px;border:1px solid var(--color-border);border-left:3px solid var(--color-change-mark);border-radius:8px;background:#fbfaf6;animation:arrive .5s ease-out}
  @keyframes arrive{from{opacity:0;transform:translateY(4px);box-shadow:0 0 0 3px rgb(217 160 40 / .35)}}
  @media (prefers-reduced-motion:reduce){.notice{animation:none}}
  .what{font-size:var(--font-small);font-weight:650;color:var(--color-ink)}
  .size{font-size:1.05rem;font-weight:650;color:var(--color-ink);line-height:1.35}
  .numbers,.when,.load-fact{color:var(--color-ink-muted);font-variant-numeric:tabular-nums}
  .when{font-size:12px}
  .load-fact{color:var(--color-ink)}
  .verdict{align-self:flex-start;padding:1px 8px;border:1px solid var(--color-ink);border-radius:999px;font-size:12px;color:var(--color-ink-muted);margin-bottom:2px}
  .verdict b{color:var(--color-ink);font-weight:650}
  .verdict.pending{border:1px dashed var(--color-control-border);color:var(--color-ink-muted)}
  .notice.settled{border-left-color:var(--color-ink-muted);background:var(--color-surface)}
  .memo{font-size:12px;color:var(--color-ink-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .act{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:4px}
  .ai-start{display:inline-flex;align-items:center;gap:5px;padding:4px 10px;border:1px solid var(--color-action);border-radius:999px;font-size:12px;font-weight:650;color:var(--color-action);text-decoration:none;background:var(--color-surface)}
  .ai-start:hover{background:var(--color-surface-selected)}
  .ai-start svg{width:13px;height:13px;fill:none;stroke:currentColor;stroke-width:1.5;stroke-linejoin:round}
  .earlier{font-size:12px;color:var(--color-ink-muted);font-variant-numeric:tabular-nums;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding-left:2px}
  .calm{color:var(--color-ink-muted)}
  .open{flex:none;font-size:var(--font-small);font-weight:650;color:var(--color-action);text-decoration:none}
  .open:hover{text-decoration:underline}
  .other{align-self:flex-start;margin-top:auto;border:0;background:none;padding:0;font:inherit;font-size:12px;color:var(--color-ink-muted);text-decoration:underline dotted;cursor:pointer;text-align:left}
  .other:hover{color:var(--color-action)}
</style>
