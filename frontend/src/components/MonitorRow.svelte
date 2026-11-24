<script lang="ts">
  import {onDestroy, type Snippet} from "svelte";
  import {investigationHref, latestEpisode, ongoing, visibleSeries, SERIES_COLORS, type FleetChange, type FleetGroup, type FleetRead} from "../fleet-observation";
  import {measure} from "../chart-axis";
  import {clockText} from "../asset-timeline";
  import {versusStart,plainLabel} from "../change-story";
  import {DECISION_LABEL} from "../review-writes";
  import {elapsedText} from "../time-axis";
  import AssetName from "./AssetName.svelte";
  import TrendChart from "./TrendChart.svelte";
  import MonitorChat from "./MonitorChat.svelte";
  import {investigationOriginUrl} from "../routes";

  /** 설비 한 줄: 왼쪽에 이름·지금 값·특이사항, 오른쪽에 화면 폭을 쓰는 실제 추이(폭이 곧 시간을 보는 해상도다).
   * 'AI 조사' 대화 칸은 이 줄이 만들고, 관제 목록 오른쪽 칸(onChat)에 띄운다. 줄 안에 열면 줄 높이가 대화 칸만큼
   * 늘어 그래프 아래가 비고 다음 설비가 밀려났다. */
  let {assetId, name, role = null, read, group, replaying, until, found, analyzed, analysisFailed, lo, hi, height, playing, chatting = false, onChat, onPause, onSignal}: {
    assetId: string; name: string; read: FleetRead; group: FleetGroup;
    /** 설비가 하는 일(한 줄): '압축공기 공급', '회전축 지지'. 모르면 null. */
    role?: string | null;
    /** 재생 중이면 위치(시각 또는 측정 번호, 기록 시작 전이면 null)와 그 위치까지 판정한 변화. */
    replaying: boolean; until: number | null; found: FleetChange[]; analyzed: number | null; analysisFailed: boolean;
    lo: number; hi: number; height: number; playing: boolean;
    /** 이 줄의 대화 칸이 열려 있는지, 대화 칸을 열고(내용) 닫는(null) 곳. */
    chatting?: boolean; onChat: (panel: Snippet | null) => void;
    onPause: () => void; onSignal: (channel: string) => void} = $props();
  let picked = $state<number | null>(null);
  let loadPick = $state<number | null>(null);
  let hovered = $state<number | null>(null);
  const cursor = $derived(hovered ?? picked ?? loadPick);
  $effect(() => {
    if (playing) { picked = null; loadPick = null; }
  });
  // 재생을 시작하거나 물을 특이사항이 없어지면(재생 위치를 옮김) 대화 칸을 닫는다. 줄이 사라질 때도.
  $effect(() => {
    if (chatting && (playing || !lead?.reviewKey)) onChat(null);
  });
  onDestroy(() => { if (chatting) onChat(null); });

  const series = $derived(!replaying ? group.series : until === null ? group.series.map(row => ({...row, points: []})) : visibleSeries(group, until));
  const changes = $derived((replaying ? found : read.changes).filter(row => until !== null && row.from <= until).map(row => ({...row, to: Math.min(row.to, until!)})));
  const episode = $derived(latestEpisode(changes));
  const lead = $derived(episode.find(row => row.key === group.focus) ?? episode[0]);
  const changeName = $derived(lead ? plainLabel(lead.label, lead.channel) : null);
  const still = $derived(lead ? ongoing(group, changes, until ?? group.record.to) : false);
  // 진동 변화가 마지막 측정까지 이어지면 크기는 지금 값으로 말한다. 구간 대표값은 이미 지난 수준까지 섞여
  // 계속 커지는 진동을 실제보다 작게 보인다. 조사 화면도 같은 값을 쓴다.
  const now = $derived(lead && still && group.axis === "acquisition" ? series.find(row => row.key === lead.key)?.points.at(-1)?.value ?? null : null);
  const shownAfter = $derived(lead ? now ?? lead.after : null);
  const reach = $derived(group.axis === "time" ? (group.bucketMs ?? 60_000) : 1);
  const lastFocus = $derived(series.find(row => row.key === group.focus)?.points.at(-1));
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
  const judged = $derived(lead?.reviewKey ? read.judgments?.[lead.reviewKey] ?? null : null);
  const savedJudgment = $derived(judged ? {
    label: judged.closed ? "검토 종료" : judged.decision ? DECISION_LABEL[judged.decision] : "확인함",
    note: judged.note,
  } : null);
  const scope = $derived(replaying && analyzed !== null ? {kind: group.axis === "time" ? "history" as const : "vibration" as const, until: analyzed} : null);
  const followup = $derived(lead?.followup ? {
    ...lead.followup,
    href: investigationOriginUrl(lead.followup.href, new URL(href(lead), location.origin).href),
  } : null);
</script>

<li class="row" class:chatting>
  <div class="card-main">
    <div class="summary">
      <header class="equipment-head">
        <div class="title"><a class="name" href={href(lead)} onclick={onPause}><AssetName label={name}/></a>
          <span class="kind">{[role, read.live ? "수신 중" : "저장 기록"].filter(Boolean).join(" · ")}</span></div>
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
            <strong>{changeName} <span aria-hidden="true">·</span> {now !== null && lead.before !== null ? "지금 " + versusStart(now, lead.before, group.unit) : lead.up ? "초기보다 높아짐" : "초기보다 낮아짐"}</strong>
            <span class="change-values">
              {#if lead.before !== null && shownAfter !== null}
                <b>{measure(lead.before, group.unit, 3)} → {measure(shownAfter, group.unit, 3)}</b>
              {/if}
              <small>{group.axis === "time" ? clockText(lead.from) : lead.from + "번째 측정"}부터 · {duration(lead)}</small>
            </span>
            {#if lead.load}<small class="change-values">같은 기간 {lead.load.label} {measure(lead.load.before, null, 3)} → {measure(lead.load.after, lead.load.unit, 3)}</small>{/if}
          </div>
          <div class="finding-actions">
            {#if lead.reviewKey && !read.live}
              <button type="button" class="ui-button ai" aria-pressed={chatting} onclick={() => { onPause(); onChat(chatting ? null : chatPanel); }}>
                <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2.5 3.5h11v7h-6l-3 2.5v-2.5h-2z"/></svg>AI에 질문</button>
            {/if}
            <a class="ui-button ui-button-primary investigate" href={href(lead)} onclick={onPause} aria-label={name + " 특이사항 조사"}>특이사항 조사 →</a>
          </div>
        </section>
      {/if}
      <footer class="row-footer">
        {#if analysisFailed}<span role="status">이 모니터링 시점의 특이사항을 읽지 못했습니다</span>
        {:else if !lead}<span>{!replaying ? "이 기록에는 특이사항이 없습니다" : analyzed === null ? "특이사항을 찾고 있습니다" : "지금까지 특이사항 없음"}</span>
          <a class="secondary-action" href={href()} onclick={onPause}>기록 살펴보기 →</a>{/if}
        {#if !replaying && other}
          <button type="button" class="secondary-action" onclick={() => onSignal(other.channel)}>다른 특이사항 {read.others.length}개</button>
        {/if}
      </footer>
    </div>
    <div class="plot-area">
      <div class="plot-title">
        <h2>{plainLabel(group.label, group.focus)}{group.unit ? " · " + group.unit : ""}</h2>
        {#if lead}<span><i class="reference"></i>초기 수준 <i class="change"></i>특이사항</span>{/if}
      </div>
      <TrendChart {group} {series} {lo} {hi} {changes} reference={lead?.before ?? null} live={replaying && playing}
        height={mainHeight} axis={!companion} guide={cursor} endLabel={true} onHover={at => hovered = at}
        bind:picked={() => picked, value => { picked = value; loadPick = null; if (value !== null) onPause(); }}/>
      {#if companion}
        <p class="load-label">{companion.label}</p>
        <TrendChart group={companion} series={load} {lo} {hi} changes={changes.map(row => ({...row, key: "load:" + row.key}))}
          height={loadHeight} axis={true} colors={["var(--color-ink-muted)"]} endLabel={true} guide={cursor} onHover={at => hovered = at}
          bind:picked={() => loadPick, value => { loadPick = value; picked = null; if (value !== null) onPause(); }}/>
      {/if}
    </div>
  </div>
</li>

{#snippet chatPanel()}
  {#if lead?.reviewKey}
    <section class="card-chat" aria-label="AI 조사">
      <div class="chat-head"><div><strong>AI 조사 · <AssetName label={name}/></strong><span>{changeName} · {group.axis === "time" ? clockText(lead.from) + "부터" : lead.from + "번째 측정부터"} · {duration(lead)}</span></div>
        <button type="button" class="close" aria-label="AI 조사 닫기" onclick={() => onChat(null)}><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8"/></svg></button></div>
      {#key [lead.reviewKey, scope?.until].join(":")}
        <MonitorChat {assetId} reviewKey={lead.reviewKey} {scope} {followup} {savedJudgment} {onPause} compareLoad={lead.compareLoad}/>
      {/key}
    </section>
  {/if}
{/snippet}

<style>
  .row {
    display:grid; gap:20px; min-width:0; list-style:none; padding:18px 20px;
    background:var(--color-surface); border:1px solid var(--color-border); border-radius:10px;
  }
  /* 대화 칸이 열린 줄: 오른쪽 칸이 어느 설비의 이야기인지 테두리로 잇는다. */
  .row.chatting { border-color:var(--color-action); box-shadow:0 0 0 1px var(--color-action); }
  .card-main { display:grid; grid-template-columns:300px minmax(0,1fr); gap:12px 28px; min-width:0; align-items:start; }
  .summary { display:grid; gap:12px; min-width:0; align-content:start; }
  .equipment-head { display:grid; gap:3px; }
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
    display:grid; gap:10px;
    padding:10px 12px; border-left:3px solid var(--color-change-mark);
    background:var(--color-uncertain-surface); border-radius:0 6px 6px 0;
  }
  .change-copy { display:grid; gap:2px; min-width:0; font-size:var(--font-small); }
  .change-values { display:flex; align-items:baseline; flex-wrap:wrap; gap:2px 10px; }
  .change-values b { font-variant-numeric:tabular-nums; font-size:1rem; }
  .change-values small { color:var(--color-ink-muted); }
  .finding-actions { display:flex; align-items:center; flex-wrap:wrap; gap:6px; }
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
  .load-label { margin:5px 0 4px 52px; font-size:var(--font-label); color:var(--color-ink-muted); }
  .row-footer { display:flex; align-items:center; flex-wrap:wrap; min-height:20px; gap:6px 16px; font-size:var(--font-label); color:var(--color-ink-muted); }
  /* 오른쪽 칸: 목록 높이만큼, 길면 화면 안에서 따라온다(입력란이 화면 밖으로 나가지 않게). */
  .card-chat {
    position:sticky; top:16px; box-sizing:border-box; height:min(100%, calc(100vh - 200px)); min-height:420px;
    display:grid; grid-template-rows:auto minmax(0,1fr); gap:8px; padding:16px;
    background:var(--color-surface); border:1px solid var(--color-border); border-radius:10px;
  }
  .card-chat :global(.agent) { min-height:0; }
  .chat-head { display:flex; align-items:start; justify-content:space-between; gap:8px; }
  .chat-head div { display:grid; gap:1px; min-width:0; }
  .chat-head strong { font-size:var(--font-small); }
  .chat-head span { font-size:var(--font-label); color:var(--color-ink-muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .close { display:grid; place-items:center; width:28px; height:28px; border:0; border-radius:6px; background:none; color:var(--color-ink-muted); cursor:pointer; }
  .close:hover { background:var(--color-surface-selected); color:var(--color-ink); }
  .close svg { width:14px; height:14px; fill:none; stroke:currentColor; stroke-width:1.6; stroke-linecap:round; }
  @media(max-width:1000px) { .card-main { grid-template-columns:minmax(0,1fr); } .card-chat { position:static; height:480px; } }
  @media(max-width:500px) { .row { padding:14px; } }
</style>
