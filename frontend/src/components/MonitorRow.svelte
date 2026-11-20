<script lang="ts">
  import {investigationHref, latestEpisode, ongoing, visibleSeries, SERIES_COLORS, type FleetChange, type FleetGroup, type FleetRead} from "../fleet-observation";
  import {measure} from "../chart-axis";
  import {clockText} from "../asset-timeline";
  import {versusStart} from "../change-story";
  import {elapsedText} from "../time-axis";
  import AssetName from "./AssetName.svelte";
  import TrendChart from "./TrendChart.svelte";

  /** 데이터셋 관제의 한 줄: 왼쪽 이름·조건·마지막 값, 가운데 추이, 오른쪽 변화 사실과 조사 링크.
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
    </dl>
    <span class="time">{#if cursor !== null}{short(cursor)}{#if picked !== null} <button type="button" aria-label="고른 시점 해제" onclick={() => picked = null}>×</button>{/if}
      {:else if lastFocus}{replaying ? "재생 위치 " : "마지막 "}{short(group.axis === "time" ? Math.min(until ?? group.record.to, lastFocus.x + (group.bucketMs ?? 0)) : lastFocus.x)}
      {:else}기록 시작 전{/if}</span>
  </div>
  <div class="chart">
    <TrendChart {group} {series} {lo} {hi} {changes} reference={lead?.before ?? null} live={replaying && playing} {height} axis={!shared}
      bind:picked={() => picked, value => { picked = value; if (value !== null) onPause(); }} bind:cursor/>
  </div>
  <div class="fact">
    {#if lead}
      <div class="head"><strong class="what">{series.length > 1 ? together(members) + " " + group.label : lead.label}</strong>
        <a class="open" href={href(lead)} onclick={onPause} aria-label={name + " 변화 조사"}>조사 →</a></div>
      <span class="size">{lead.before !== null && lead.after !== null ? versusStart(lead.after, lead.before, group.unit) : lead.up ? "높음" : "낮음"}</span>
      {#if lead.before !== null && lead.after !== null}<span class="numbers">{measure(lead.before, group.unit, 3)} → {measure(lead.after, group.unit, 3)}</span>{/if}
      <span class="when">{group.axis === "time" ? clockText(lead.from) : lead.from + "번째 측정"}부터 · {still ? "마지막 측정까지 이어짐" : duration(lead)}</span>
    {:else}
      <div class="head"><span class="calm">{replaying && analyzed === null ? "변화 판정 중" : read.live ? "앞선 관측과 달라진 구간 없음" : "기록 앞부분과 달라진 구간 없음"}</span>
        <a class="open" href={href()} onclick={onPause} aria-label={name + " 측정 보기"}>보기 →</a></div>
    {/if}
    {#if replaying}<small>판정 범위 · {analyzed === null ? "계산 중" : "~" + short(analyzed)}</small>
    {:else if other}
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
  .time{margin-top:auto;font-size:12px;color:var(--color-ink-muted);font-variant-numeric:tabular-nums;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .time button{border:0;background:none;color:var(--color-ink-muted);cursor:pointer;font-size:14px;padding:0 2px}
  .chart{min-width:0;align-self:center}
  /* 세로 눈금 칸 폭을 고정해 줄마다 그래프 시작이 같고 위의 공유 가로축과 맞는다. */
  .chart :global(.plotted){grid-template-columns:44px minmax(0,1fr)}
  .fact{display:flex;flex-direction:column;gap:2px;min-width:0;font-size:var(--font-small);overflow:hidden}
  .head{display:flex;align-items:baseline;justify-content:space-between;gap:8px}
  .what{font-size:var(--font-small);font-weight:650}
  .size{font-size:1.05rem;font-weight:650;color:var(--color-ink)}
  .numbers,.when{color:var(--color-ink-muted);font-variant-numeric:tabular-nums}
  .fact small{font-size:12px;color:var(--color-ink-muted);font-variant-numeric:tabular-nums}
  .calm{color:var(--color-ink-muted)}
  .open{flex:none;font-size:var(--font-small);font-weight:650;color:var(--color-action);text-decoration:none}
  .open:hover{text-decoration:underline}
  .other{align-self:flex-start;margin-top:auto;border:0;background:none;padding:0;font:inherit;font-size:12px;color:var(--color-ink-muted);text-decoration:underline dotted;cursor:pointer;text-align:left}
  .other:hover{color:var(--color-action)}
</style>
