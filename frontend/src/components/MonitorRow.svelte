<script lang="ts">
  import {investigationHref, latestEpisode, ongoing, visibleSeries, SERIES_COLORS, type FleetChange, type FleetGroup, type FleetRead} from "../fleet-observation";
  import {measure} from "../chart-axis";
  import {clockText, episodes} from "../asset-timeline";
  import {versusStart,plainLabel} from "../change-story";
  import {DECISION_LABEL} from "../review-writes";
  import {elapsedText} from "../time-axis";
  import AssetName from "./AssetName.svelte";
  import TrendChart from "./TrendChart.svelte";
  import MonitorChat from "./MonitorChat.svelte";
  import {noticeSentences} from "../monitor-chat";
  import type {RunEnding} from "../public-datasets";

  /** 설비 카드: 이름과 마지막 값, 특이사항 한 줄, 그 아래 실제 추이. 'AI 조사'는 그래프를 가리지 않게 카드 오른쪽에
   * 대화 칸을 연다(카드는 그동안 한 줄을 다 쓴다). */
  let {assetId, name, role = null, ending = null, read, group, replaying, until, found, analyzed, analysisFailed, lo, hi, height, playing, onPause, onSignal}: {
    assetId: string; name: string; read: FleetRead; group: FleetGroup;
    /** 끝까지 잰 시험 기록의 결말. 모니터링이 그 측정에 닿아야 그래프에 보인다. */
    ending?: RunEnding | null;
    /** 설비가 하는 일(한 줄): '압축공기 공급', '회전축 지지'. 모르면 null. */
    role?: string | null;
    /** 재생 중이면 위치(시각 또는 측정 번호, 기록 시작 전이면 null)와 그 위치까지 판정한 변화. */
    replaying: boolean; until: number | null; found: FleetChange[]; analyzed: number | null; analysisFailed: boolean;
    lo: number; hi: number; height: number; playing: boolean;
    onPause: () => void; onSignal: (channel: string) => void} = $props();
  let chatOpen = $state(false);
  let picked = $state<number | null>(null);
  let loadPick = $state<number | null>(null);
  let hovered = $state<number | null>(null);
  const cursor = $derived(hovered ?? picked ?? loadPick);
  $effect(() => {
    if (playing) { picked = null; loadPick = null; chatOpen = false; }
  });

  const series = $derived(!replaying ? group.series : until === null ? group.series.map(row => ({...row, points: []})) : visibleSeries(group, until));
  const changes = $derived((replaying ? found : read.changes).filter(row => until !== null && row.from <= until).map(row => ({...row, to: Math.min(row.to, until!)})));
  const episode = $derived(latestEpisode(changes));
  const lead = $derived(episode.find(row => row.key === group.focus) ?? episode[0]);
  const changeName = $derived(lead ? plainLabel(lead.label, lead.channel) : null);
  const still = $derived(lead ? ongoing(group, changes, until ?? group.record.to) : false);
  const reach = $derived(group.axis === "time" ? (group.bucketMs ?? 60_000) : 1);
  const lastFocus = $derived(series.find(row => row.key === group.focus)?.points.at(-1));
  // 모니터링이 기록의 마지막 측정에 닿았을 때만 결말을 보인다.
  const ended = $derived(ending && series.some(row => (row.points.at(-1)?.x ?? -Infinity) >= ending.at) ? ending : null);
  const other = $derived([...read.others].sort((a, b) => b.from - a.from)[0]);
  const href = (change?: FleetChange) => {
    if (read.live) return read.href;
    const position = replaying ? (change ? analyzed ?? until : until) : null;
    return investigationHref(assetId, group, position, change);
  };

  const short = (at: number) => group.axis === "time" ? new Date(at).toLocaleString("ko-KR",{year:"numeric",month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit",hour12:false})
    : Math.floor(at) + "번째" + (group.periodSeconds ? " · " + elapsedText((Math.floor(at) - 1) * group.periodSeconds) : "");
  function nearest(points: {x: number; value: number}[], at: number) {
    let best: {x: number; value: number} | null = null;
    for (const point of points) if (!best || Math.abs(point.x - at) < Math.abs(best.x - at)) best = point;
    return best && Math.abs(best.x - at) <= reach ? best : null;
  }
  const duration = (change: FleetChange) => group.axis === "time" ? elapsedText((change.to - change.from) / 1000) : (change.to - change.from + 1) + "회 측정";
  // 부하 신호(전류): 전압 그래프 바로 아래 같은 시간축에. 모니터링 중이면 같은 시점까지만 그린다.
  const companion = $derived(read.companion);
  const load = $derived(!companion ? [] : !replaying ? companion.series : until === null ? companion.series.map(row => ({...row, points: []})) : visibleSeries(companion, until));
  const mainHeight = $derived(companion ? Math.round(height * .68) : height);
  const loadHeight = $derived(companion ? Math.max(48, height - mainHeight - 20) : 0);
  const loadPoint = $derived(load[0] ? (cursor !== null ? nearest(load[0].points, cursor) : load[0].points.at(-1)) : null);
  // 앞서 찾은 변화(가장 최근 시기 앞의 시기들): 최근 것부터 두 개까지.
  const earlier = $derived(episodes(changes, change => change).slice(0, -1).reverse().slice(0, 2)
    .map(span => span.members.find(row => row.key === group.focus) ?? span.members[0]));
  // 남긴 판단: 같은 특이사항(기간·기준이 같은 것)에만 붙인다. 모니터링 중에는 기간이 잘려 다른 특이사항이 되므로
  // 판단이 없다고 '판단 전'이라 말하지 않는다.
  const judgmentOf = (change: FleetChange) => change.reviewKey ? read.judgments?.[change.reviewKey] ?? null : null;
  const judged = $derived(lead ? judgmentOf(lead) : null);
  const day = (at: string) => new Date(at).toLocaleDateString("ko-KR", {month: "long", day: "numeric"});
  const verdict = (change: FleetChange) => {
    const own = judgmentOf(change);
    return own?.closed ? "검토 종료" : own?.decision ? DECISION_LABEL[own.decision] : own ? "확인함" : null;
  };
  // AI 관제가 하는 말: 가장 최근 특이사항, 앞의 특이사항(오래된 것부터), 남긴 판단.
  const notice = $derived(lead ? noticeSentences({
    what: lead.label,
    size: (lead.before !== null && lead.after !== null ? versusStart(lead.after, lead.before, group.unit) : null) ?? (lead.up ? "높음" : "낮음"),
    before: lead.before !== null && lead.after !== null ? measure(lead.before, group.unit, 3) : null,
    after: lead.before !== null && lead.after !== null ? measure(lead.after, group.unit, 3) : null,
    when: group.axis === "time" ? clockText(lead.from) : lead.from + "번째 측정",
    still, duration: duration(lead),
    load: lead.load ? {label: lead.load.label, before: measure(lead.load.before, lead.load.unit, 2), after: measure(lead.load.after, lead.load.unit, 2),
      ratio: lead.load.before ? lead.load.after / lead.load.before : 1} : null,
  }) : null);
  const past = $derived([...earlier].reverse().map(change => ({key: change.key + change.from,
    when: group.axis === "time" ? clockText(change.from) : change.from + "번째",
    text: change.label + " " + (change.up ? "높음" : "낮음") + (verdict(change) ? " · " + verdict(change) : "")})));
  const spoken = $derived(judged && lead ? {verdict: verdict(lead)!, day: day(judged.at), note: judged.note} : lead && !replaying && !read.live ? "pending" as const : null);
  const scope = $derived(replaying && analyzed !== null ? {kind: group.axis === "time" ? "history" as const : "vibration" as const, until: analyzed} : null);
  const watched = $derived(read.live ? "최근 관측 확인" : !replaying ? "기록 전체 확인" : analyzed === null ? "변화 판정 중" : "~" + short(analyzed) + "까지 확인");
</script>

<li class="row" class:chatting={chatOpen && !!lead?.reviewKey}>
  <div class="card-main">
    <header class="equipment-head">
      <div class="title"><a class="name" href={href(lead)} onclick={onPause}><AssetName label={name}/></a>
        <span class="kind">{role ? role + " · " : ""}{read.live?"수신 중":group.axis==="acquisition"?"저장된 시험 기록":"과거 저장 기록"}{replaying?" · 모니터링 중":""}</span></div>
      <div class="reading"><span>{group.axis==="time"?(cursor!==null?"선택 구간 평균":"최근 구간 평균"):(cursor!==null?"선택한 측정":"마지막 측정")}</span><time>{cursor!==null?short(cursor):lastFocus?short(group.axis==="time"?Math.min(until??group.record.to,lastFocus.x+(group.bucketMs??0)):lastFocus.x):"기록 시작 전"}</time>{#if picked !== null || loadPick !== null}<button type="button" class="clear-pick" onclick={() => { picked = null; loadPick = null; }}>선택 해제</button>{/if}</div>
    </header>
    <dl class="values">
      {#each series as row,index(row.key)}
        {@const point=cursor!==null?nearest(row.points,cursor):row.points.at(-1)}
        <div><dt><i style:background={SERIES_COLORS[index%SERIES_COLORS.length]}></i>{series.length>1?row.short:group.label}</dt><dd>{point?measure(point.value,group.unit,group.unit==="V"?4:3):"—"}</dd></div>
      {/each}
      {#if companion}<div class="load"><dt>{companion.label}</dt><dd>{loadPoint?measure(loadPoint.value,companion.unit,3):"—"}</dd></div>{/if}
    </dl>
    {#if lead}
      <section class="finding" aria-label="이 그래프의 특이사항">
        <div class="change-copy">
          <strong>{changeName} <span aria-hidden="true">·</span> {lead.up ? "초기보다 높아짐" : "초기보다 낮아짐"}</strong>
          <span class="change-values">
            {#if lead.before !== null && lead.after !== null}
              <b>{measure(lead.before, group.unit, 3)} → {measure(lead.after, group.unit, 3)}</b>
            {/if}
            <small>{group.axis === "time" ? clockText(lead.from) : lead.from + "번째 측정"}부터 · {duration(lead)}</small>
          </span>
        </div>
        <div class="finding-actions">
          {#if lead.reviewKey && !read.live}
            <button type="button" class="ui-button ai" aria-pressed={chatOpen} onclick={() => { onPause(); chatOpen = !chatOpen; }}>
              <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2.5 3.5h11v7h-6l-3 2.5v-2.5h-2z"/></svg>AI 조사</button>
          {/if}
          <a class="ui-button ui-button-primary investigate" href={href(lead)} onclick={onPause} aria-label={name + " 특이사항 조사"}>특이사항 조사 →</a>
        </div>
      </section>
    {/if}
    <div class="plot-area">
      <div class="plot-title">
        <h2>{plainLabel(group.label, group.focus)}{group.unit ? " · " + group.unit : ""}</h2>
        {#if lead || ended}<span>{#if lead}<i class="reference"></i>초기 수준 <i class="change"></i>특이사항{/if}{#if ended}<i class="ending"></i>{ended.label}{/if}</span>{/if}
      </div>
      <TrendChart {group} {series} {lo} {hi} {changes} reference={lead?.before ?? null} live={replaying && playing}
        height={mainHeight} axis={!companion} guide={cursor} endLabel={true} {ending} onHover={at => hovered = at}
        bind:picked={() => picked, value => { picked = value; loadPick = null; if (value !== null) onPause(); }}/>
      {#if companion}
        <p class="load-label">{companion.label}</p>
        <TrendChart group={companion} series={load} {lo} {hi} changes={changes.map(row => ({...row, key: "load:" + row.key}))}
          height={loadHeight} axis={true} colors={["var(--color-ink-muted)"]} endLabel={true} guide={cursor} onHover={at => hovered = at}
          bind:picked={() => loadPick, value => { loadPick = value; picked = null; if (value !== null) onPause(); }}/>
      {/if}
    </div>
    <footer class="row-footer">
      {#if analysisFailed}<span role="status">이 모니터링 시점의 특이사항을 읽지 못했습니다</span>
      {:else if !lead}<span>{replaying && analyzed !== until ? "특이사항을 찾고 있습니다" : "이 기록에는 특이사항이 없습니다"}</span>
        <a class="secondary-action" href={href()} onclick={onPause}>기록 살펴보기 →</a>{/if}
      {#if !replaying && other}
        <button type="button" class="secondary-action" onclick={() => onSignal(other.channel)}>다른 특이사항 {read.others.length}개</button>
      {/if}
    </footer>
  </div>
  {#if chatOpen && lead?.reviewKey}
    <aside class="card-chat" aria-label="AI 조사">
      <div class="chat-inner">
        <div class="chat-head"><div><strong>AI 조사</strong><span>{changeName} · {watched}</span></div>
          <button type="button" class="close" aria-label="AI 조사 닫기" onclick={() => chatOpen = false}><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8"/></svg></button></div>
        <MonitorChat {assetId} reviewKey={lead.reviewKey} {scope} {watched} {notice} when={null} judged={spoken} earlier={past} heading={false}
          calm="이 기록에는 특이사항이 없습니다." checking={replaying && analyzed === null} detailHref={href(lead)} canAsk={!read.live} {onPause}/>
      </div>
    </aside>
  {/if}
</li>

<style>
  .row {
    display:grid; gap:20px; min-width:0; list-style:none; padding:18px 20px;
    background:var(--color-surface); border:1px solid var(--color-border); border-radius:10px;
  }
  /* AI 조사를 열면 카드가 한 줄을 다 쓰고 오른쪽에 대화 칸: 그래프를 보면서 묻는다. */
  .row.chatting { grid-column:1 / -1; grid-template-columns:minmax(0,1fr) 380px; }
  .card-main { display:grid; gap:10px; min-width:0; align-content:start; }
  .equipment-head { display:flex; align-items:baseline; justify-content:space-between; gap:6px 12px; flex-wrap:wrap; }
  .title { display:flex; align-items:baseline; gap:8px; min-width:0; }
  .name { font-size:1.1rem; font-weight:700; color:var(--color-ink); text-decoration:none; }
  .name:hover { text-decoration:underline; }
  .kind,.reading { font-size:var(--font-label); color:var(--color-ink-muted); }
  .reading { display:flex; flex-wrap:wrap; gap:4px 8px; align-items:center; }
  .reading time { font-variant-numeric:tabular-nums; }
  .clear-pick,.secondary-action {
    font:inherit; font-size:var(--font-label); color:var(--color-action); border:0; background:none;
    padding:0; cursor:pointer; text-decoration:none;
  }
  .clear-pick:hover,.secondary-action:hover { text-decoration:underline; }
  .values { display:flex; flex-wrap:wrap; gap:4px 14px; margin:0; }
  .values > div,.values dt { display:flex; align-items:baseline; gap:5px; }
  .values dt { font-size:var(--font-label); color:var(--color-ink-muted); }
  .values dt i { align-self:center; width:10px; height:3px; border-radius:2px; }
  .values dd { margin:0; font-size:var(--font-small); font-weight:650; font-variant-numeric:tabular-nums; }
  .finding {
    display:flex; align-items:center; justify-content:space-between; gap:8px 14px; flex-wrap:wrap;
    padding:8px 10px 8px 12px; border-left:3px solid var(--color-change-mark);
    background:var(--color-uncertain-surface); border-radius:0 6px 6px 0;
  }
  .change-copy { display:grid; gap:2px; min-width:0; font-size:var(--font-small); }
  .change-values { display:flex; align-items:baseline; flex-wrap:wrap; gap:2px 10px; }
  .change-values b { font-variant-numeric:tabular-nums; font-size:1rem; }
  .change-values small { color:var(--color-ink-muted); }
  .finding-actions { display:flex; align-items:center; gap:6px; }
  .finding-actions .ui-button { display:inline-flex; align-items:center; gap:6px; min-height:34px; padding:5px 12px; font-size:var(--font-label); font-weight:650; white-space:nowrap; text-decoration:none; }
  .ai { color:var(--color-action); }
  .ai[aria-pressed="true"] { background:var(--color-surface-selected); border-color:var(--color-action); }
  .ai svg { width:14px; height:14px; fill:none; stroke:currentColor; stroke-width:1.5; stroke-linejoin:round; }
  .plot-area { min-width:0; }
  .plot-area :global(.plotted) { grid-template-columns:44px minmax(0,1fr); }
  .plot-title { display:flex; align-items:center; justify-content:space-between; gap:8px; margin:0 0 7px; }
  .plot-title h2 { margin:0; font-size:var(--font-label); }
  .plot-title > span { display:flex; align-items:center; gap:5px; font-size:11px; color:var(--color-ink-muted); }
  .reference { width:14px; border-top:1px dashed var(--color-reference-line); }
  .change { width:12px; height:9px; background:var(--color-change-fill); margin-left:6px; }
  .ending { width:0; height:11px; border-left:1.5px solid var(--color-ink); margin-left:8px; }
  .load-label { margin:5px 0 4px 52px; font-size:var(--font-label); color:var(--color-ink-muted); }
  .row-footer { display:flex; align-items:center; flex-wrap:wrap; min-height:20px; gap:6px 16px; font-size:var(--font-label); color:var(--color-ink-muted); }
  .card-chat { position:relative; min-height:480px; border-left:1px solid var(--color-border); padding-left:16px; }
  .chat-inner { position:absolute; inset:0 0 0 16px; display:grid; grid-template-rows:auto minmax(0,1fr); gap:8px; }
  .chat-inner :global(.agent) { min-height:0; }
  .chat-head { display:flex; align-items:start; justify-content:space-between; gap:8px; }
  .chat-head div { display:grid; gap:1px; min-width:0; }
  .chat-head strong { font-size:var(--font-small); }
  .chat-head span { font-size:var(--font-label); color:var(--color-ink-muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .close { display:grid; place-items:center; width:28px; height:28px; border:0; border-radius:6px; background:none; color:var(--color-ink-muted); cursor:pointer; }
  .close:hover { background:var(--color-surface-selected); color:var(--color-ink); }
  .close svg { width:14px; height:14px; fill:none; stroke:currentColor; stroke-width:1.6; stroke-linecap:round; }
  @media(max-width:1000px) { .row.chatting { grid-template-columns:minmax(0,1fr); } .card-chat { border-left:0; padding-left:0; } .chat-inner { inset:0; } }
  @media(max-width:500px) { .row { padding:14px; } }
</style>
