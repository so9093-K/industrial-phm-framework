<script lang="ts">
  import {tick} from "svelte";
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

  /** 설비 카드의 실제 추이와 변화 요약. AI 질문은 선택한 변화에서만 연다. */
  let {assetId, name, read, group, replaying, until, found, analyzed, lo, hi, height, playing, onPause, onSignal}: {
    assetId: string; name: string; read: FleetRead; group: FleetGroup;
    /** 재생 중이면 위치(시각 또는 측정 번호, 기록 시작 전이면 null)와 그 위치까지 판정한 변화. */
    replaying: boolean; until: number | null; found: FleetChange[]; analyzed: number | null;
    lo: number; hi: number; height: number; playing: boolean;
    onPause: () => void; onSignal: (channel: string) => void} = $props();
  let chatOpen=$state(false),cardElement:HTMLLIElement;
  async function toggleChat(){onPause();chatOpen=!chatOpen;if(chatOpen){await tick();cardElement?.scrollIntoView({block:"nearest",behavior:"smooth"});}}
  let picked: number | null = $state(null), cursor: number | null = $state(null);
  $effect(()=>{if(playing)picked=null;});

  const series = $derived(!replaying ? group.series : until === null ? group.series.map(row => ({...row, points: []})) : visibleSeries(group, until));
  const changes = $derived((replaying ? found : read.changes).filter(row => until !== null && row.from <= until).map(row => ({...row, to: Math.min(row.to, until!)})));
  const episode = $derived(latestEpisode(changes));
  const lead = $derived(episode.find(row => row.key === group.focus) ?? episode[0]);
  const still = $derived(lead ? ongoing(group, changes, until ?? group.record.to) : false);
  const reach = $derived(group.axis === "time" ? (group.bucketMs ?? 60_000) : 1);
  const lastFocus = $derived(series.find(row => row.key === group.focus)?.points.at(-1));
  const other = $derived([...read.others].sort((a, b) => b.from - a.from)[0]);
  const href = (change?: FleetChange) => read.live ? read.href : investigationHref(assetId, group, replaying ? until : null, change);

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

<li class="row" class:expanded={chatOpen} bind:this={cardElement}>
  <header class="equipment-head">
    <div><a class="name" href={href(lead)} onclick={onPause}><AssetName label={name}/></a>
      <span class="kind">{read.live?"수신 중":group.axis==="acquisition"?"저장된 시험 기록":"과거 저장 기록"}{replaying?" · 기록 재생":""}</span></div>
    <a class="investigate" href={href(lead)} onclick={onPause}>자세히 조사 →</a>
  </header>
  <div class="reading"><span>{group.axis==="time"?(cursor!==null?"선택 구간 평균":"최근 구간 평균"):(cursor!==null?"선택한 측정":"마지막 측정")}</span><time>{cursor!==null?short(cursor):lastFocus?short(group.axis==="time"?Math.min(until??group.record.to,lastFocus.x+(group.bucketMs??0)):lastFocus.x):"기록 시작 전"}</time>{#if picked!==null}<button type="button" class="clear-pick" onclick={()=>picked=null}>선택 해제</button>{/if}</div>
  <dl class="values">
    {#each series as row,index(row.key)}
      {@const point=cursor!==null?nearest(row.points,cursor):row.points.at(-1)}
      <div><dt><i style:background={SERIES_COLORS[index%SERIES_COLORS.length]}></i>{series.length>1?row.short:group.label}</dt><dd>{point?measure(point.value,group.unit,group.unit==="V"?4:3):"—"}</dd></div>
    {/each}
    {#if companion}<div class="load"><dt>{companion.label}</dt><dd>{loadPoint?measure(loadPoint.value,companion.unit,3):"—"}</dd></div>{/if}
  </dl>
  <div class="workspace">
    <div class="plot-area">
      <div class="plot-title"><h2>{plainLabel(group.label,group.focus)}{group.unit?" · "+group.unit:""}</h2><span><i class="reference"></i>초기 수준 <i class="change"></i>변화 구간</span></div>
      <TrendChart {group} {series} {lo} {hi} {changes} reference={lead?.before??null} live={replaying&&playing} height={mainHeight} axis={!companion}
        bind:picked={()=>picked,value=>{picked=value;if(value!==null)onPause();}} bind:cursor/>
      {#if companion}<p class="load-label">{companion.label}</p>
        <TrendChart group={companion} series={load} {lo} {hi} changes={changes.map(row=>({...row,key:"load:"+row.key}))} height={loadHeight} axis={true}
          colors={["var(--color-ink-muted)"]} guide={cursor} bind:cursor/>
      {/if}
    </div>
    {#if chatOpen}<aside class="conversation" aria-label={name+" AI 질문"}>
      <header><strong>이 변화에 질문</strong><button type="button" aria-label="AI 질문 닫기" onclick={()=>chatOpen=false}>닫기</button></header>
      {#key lead?.reviewKey??lead?.key??"calm"}<MonitorChat {assetId} reviewKey={lead?.reviewKey??null} {scope} {watched} {notice} when={null} judged={spoken} earlier={past}
        calm="선택한 기록에서 뚜렷하게 달라진 구간이 없습니다." checking={replaying&&analyzed===null} detailHref={href(lead)} canAsk={!read.live&&!!lead?.reviewKey} {onPause}/>{/key}
    </aside>{/if}
  </div>
  <footer class="finding">
    {#if lead}<div><span class="finding-label">{plainLabel(lead.label,lead.channel)} · {lead.up?"초기보다 높아짐":"초기보다 낮아짐"}</span>
      <strong>{lead.before!==null?measure(lead.before,group.unit,3):"—"} <span>→</span> {lead.after!==null?measure(lead.after,group.unit,3):"—"}</strong>
      <small>변화 구간 대표값 · {group.axis==="time"?clockText(lead.from):lead.from+"번째 측정"}부터 · {duration(lead)}</small></div>
    {:else}<div class="calm">{replaying&&analyzed===null?"측정 추이를 읽으며 변화를 살피고 있습니다":"선택한 기록에서 뚜렷한 변화가 발견되지 않았습니다"}</div>{/if}
    <div class="actions">{#if lead?.reviewKey&&!read.live}<button type="button" class="ui-button" aria-expanded={chatOpen} onclick={()=>void toggleChat()}>AI 질문</button>{/if}
      {#if !replaying&&other}<button type="button" class="other" onclick={()=>onSignal(other.channel)}>다른 변화 {read.others.length}개</button>{/if}</div>
  </footer>
</li>

<style>
  .row{display:grid;gap:12px;min-width:0;list-style:none;padding:18px 20px;background:var(--color-surface);border:1px solid var(--color-border);border-radius:10px;box-sizing:border-box}
  .row.expanded{grid-column:1/-1}.equipment-head{display:flex;align-items:start;justify-content:space-between;gap:12px}.equipment-head>div{display:grid;gap:3px}
  .name{font-size:1.1rem;font-weight:700;color:var(--color-ink);text-decoration:none}.name:hover{text-decoration:underline}
  .kind,.reading{font-size:12px;color:var(--color-ink-muted)}.investigate{font-size:var(--font-label);font-weight:650;white-space:nowrap;text-decoration:none;color:var(--color-action)}
  .clear-pick{font:inherit;font-size:12px;color:var(--color-action);border:0;background:none;padding:0;cursor:pointer}
  .reading{display:flex;gap:10px;align-items:center}.reading time{font-variant-numeric:tabular-nums}
  .values{display:flex;flex-wrap:wrap;gap:10px 24px;margin:0}.values>div{display:grid;gap:1px}.values dt{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--color-ink-muted)}
  .values dt i{display:inline-block;width:12px;height:3px;border-radius:2px}.values dd{margin:0;font-size:1.2rem;font-weight:700;font-variant-numeric:tabular-nums}.values .load dd{font-weight:500;color:var(--color-ink-muted)}
  .workspace{display:grid;gap:20px;min-width:0}.expanded .workspace{grid-template-columns:minmax(0,1fr) 340px}.plot-area{min-width:0}
  .plot-title{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px}.plot-title h2{margin:0;font-size:12px;font-weight:600}.plot-title>span{display:flex;align-items:center;gap:5px;font-size:11px;color:var(--color-ink-muted)}
  .reference{width:14px;border-top:1px dashed var(--color-reference-line)}.change{width:12px;height:9px;background:var(--color-change-fill);margin-left:6px}
  .load-label{margin:0 0 4px 52px;font-size:11px;color:var(--color-ink-muted)}
  .finding{border-top:1px solid var(--color-border);padding-top:12px;display:flex;align-items:center;justify-content:space-between;gap:12px;min-width:0}.finding>div:first-child{display:grid;gap:2px;min-width:0}
  .finding-label{font-size:var(--font-label);font-weight:600}.finding strong{font-size:1.1rem;font-variant-numeric:tabular-nums}.finding strong span{color:var(--color-ink-muted);font-weight:400;margin-inline:4px}.finding small{font-size:11px;color:var(--color-ink-muted)}
  .actions{display:flex;align-items:center;flex-wrap:wrap;justify-content:end;gap:8px}.actions button{white-space:nowrap;font-size:var(--font-label);padding:6px 10px;min-height:32px}
  .other{border:0;background:none;color:var(--color-action);font:inherit;cursor:pointer}.calm{font-size:var(--font-small);color:var(--color-ink-muted)}
  .conversation{min-width:0;min-height:300px;display:flex;flex-direction:column;border-left:1px solid var(--color-border);padding-left:20px}.conversation>header{display:flex;align-items:center;justify-content:space-between;font-size:var(--font-small);margin-bottom:8px}.conversation>header button{font:inherit;font-size:12px;border:0;background:none;color:var(--color-action);cursor:pointer}.conversation :global(.agent){flex:1;min-height:280px}
  @media(max-width:800px){.expanded .workspace{grid-template-columns:minmax(0,1fr)}.conversation{border-left:0;border-top:1px solid var(--color-border);padding:16px 0 0}}
  @media(max-width:500px){.row{padding:14px}.values{gap:8px 14px}.finding{align-items:start;flex-direction:column}.actions{justify-content:start}}
</style>
