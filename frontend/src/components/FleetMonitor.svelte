<script lang="ts">
  import {onDestroy, onMount, untrack} from "svelte";
  import {assetOptionLabel, flowLabel, type Asset} from "../monitor";
  import {investigationHref, latestEpisode, positionAt, readFleet, readFleetChanges, visibleSeries, SERIES_COLORS,
    type FleetChange, type FleetGroup, type FleetRead} from "../fleet-observation";
  import {measure} from "../chart-axis";
  import {clockText} from "../asset-timeline";
  import {measurementLabel} from "../time-axis";
  import {readPublicDatasets} from "../public-datasets";
  import {systemUrl} from "../routes";
  import {recentAsset} from "../observation";
  import AssetName from "./AssetName.svelte";
  import FleetTrace from "./FleetTrace.svelte";

  /** 설비 관제: 설비마다 지켜보는 신호 묶음의 실제 추이를 나란히 두고, 저장 기록은 함께 재생한다.
   * 재생 중에는 위치까지 끝난 측정만 그리고, 변화는 그 위치까지의 기록으로 판정한 가장 최근 결과를 칠한다.
   * 판정 기준(기록 앞부분)이 기록과 함께 길어지므로 앞선 판정을 쌓지 않는다. 재생 끝은 정지 화면과 같다. */
  let {assets, cycle, checkedAt, onRefresh}: {assets: Asset[]; cycle: number; checkedAt: string; onRefresh: () => void} = $props();

  type Card = {read: FleetRead | null; error: boolean; busy: boolean; found: FleetChange[]; analyzed: number | null; analyzing: boolean};
  let cards: Record<string, Card> = $state({});
  let picked: Record<string, number | null> = $state({}), cursor: Record<string, number | null> = $state({});
  const blank = (): Card => ({read: null, error: false, busy: true, found: [], analyzed: null, analyzing: false});

  // 재생 위치는 설비마다 다른 기록 길이에 대한 비율이다. 조사 화면에 다녀와도 같은 위치에서 이어 보도록 탭에 남긴다.
  const STORE = "phm.fleet.replay";
  function restored(): number | null {
    try { const value = Number(sessionStorage.getItem(STORE)); return value > 0 && value <= 1 ? value : null; } catch { return null; }
  }
  let fraction: number | null = $state(restored()), playing = $state(false), seconds = $state(60);
  $effect(() => {
    const value = fraction;
    try { if (value === null) sessionStorage.removeItem(STORE); else sessionStorage.setItem(STORE, String(value)); } catch { /* 저장하지 못해도 재생은 된다. */ }
  });

  // 읽기: 설비 목록이나 수신 중인 출처의 관측 주기가 바뀔 때만 다시 읽는다. 재생 중인 저장 기록은 다시 읽지 않는다.
  const wanted = new Map<string, string>(), queue = new Set<string>(), loading = new Map<string, AbortController>();
  let disposed = false;
  const revisions = $derived(JSON.stringify(assets.map(a => [a.assetId,
    (a.overviewRevision ?? JSON.stringify([a.lastObservedAt, a.lastReceivedAt, a.lastPosition])) + ":" + (recentAsset(a) ? cycle : 0)])));
  function drain() {
    while (loading.size < 2 && queue.size && !disposed) {
      const id = [...queue][0];
      queue.delete(id);
      const revision = wanted.get(id), asset = assets.find(a => a.assetId === id);
      if (!asset) continue;
      const request = new AbortController();
      loading.set(id, request);
      cards[id] = {...(cards[id] ?? blank()), busy: true, error: false};
      void readFleet(asset, request.signal).then(read => {
        if (request.signal.aborted || wanted.get(id) !== revision) return;
        cards[id] = {...cards[id], read, busy: false, error: false};
        analyze();
      }).catch(() => {
        if (!request.signal.aborted && wanted.get(id) === revision) cards[id] = {...cards[id], busy: false, error: true};
      }).finally(() => { loading.delete(id); drain(); });
    }
  }
  $effect(() => {
    const current = new Map<string, string>(JSON.parse(revisions));
    untrack(() => {
      for (const id of wanted.keys()) if (!current.has(id)) {
        wanted.delete(id); queue.delete(id); loading.get(id)?.abort(); delete cards[id];
      }
      for (const [id, version] of current) {
        const stored = !cards[id]?.read?.live;
        if (wanted.get(id) === version || (fraction !== null && stored && cards[id]?.read)) continue;
        wanted.set(id, version); queue.add(id);
      }
      drain();
    });
  });
  function reload(id: string) { wanted.set(id, (wanted.get(id) ?? "") + ":retry"); queue.add(id); drain(); }

  // 변화 판정: 설비마다 한 번에 하나, 끝나면 그때의 재생 위치로 다시. 판정은 계산이 끝난 위치까지만 표시한다.
  const judging = new Map<string, AbortController>(), requested = new Map<string, number>(), started = new Map<string, number>();
  function analyze() {
    const at = fraction;
    if (at === null || disposed) return;
    for (const [id, card] of Object.entries(cards)) {
      const group = card.read?.group;
      if (!group || card.read?.live || judging.has(id) || Date.now() - (started.get(id) ?? 0) < 500) continue;
      const until = positionAt(group, at);
      if (requested.get(id) === until) continue;
      requested.set(id, until); started.set(id, Date.now());
      const request = new AbortController();
      judging.set(id, request);
      card.analyzing = true;
      void readFleetChanges(id, group, until, request.signal).then(found => {
        const now = fraction;
        if (request.signal.aborted || now === null || positionAt(group, now) < until || !cards[id]) return;
        cards[id].found = found;
        cards[id].analyzed = until;
      }).catch(() => { /* 다음 위치에서 다시 판정한다. */ }).finally(() => {
        judging.delete(id);
        if (cards[id]) cards[id].analyzing = false;
        analyze();
      });
    }
  }
  function resetJudgement() {
    for (const request of judging.values()) request.abort();
    judging.clear(); requested.clear(); started.clear();
    for (const card of Object.values(cards)) { card.found = []; card.analyzed = null; card.analyzing = false; }
  }
  let timer: ReturnType<typeof setInterval> | null = null;
  $effect(() => {
    if (!playing) return;
    const id = setInterval(() => {
      const next = Math.min(1, (fraction ?? 0.1) + 0.1 / seconds);
      fraction = next;
      if (next >= 1) playing = false;
      analyze();
    }, 100);
    timer = id;
    return () => { clearInterval(id); timer = null; };
  });
  function play() {
    if (fraction === null || fraction >= 1) { resetJudgement(); fraction = 0.1; }
    for (const id of Object.keys(picked)) picked[id] = null;
    playing = true;
    analyze();
  }
  function seek(value: number) {
    playing = false;
    if (fraction !== null && value < fraction) resetJudgement();
    fraction = Math.max(0.01, Math.min(1, value));
    analyze();
  }
  function stop() { playing = false; resetJudgement(); fraction = null; }
  onMount(() => { if (fraction !== null) analyze(); });
  onDestroy(() => {
    disposed = true;
    if (timer !== null) clearInterval(timer);
    for (const request of [...loading.values(), ...judging.values()]) request.abort();
  });

  let bearingHref = $state("");
  onMount(() => {
    const request = new AbortController();
    void readPublicDatasets(request.signal).then(data => {
      const bearings = data.items.filter(item => item.kind === "xjtu-sy");
      if (!request.signal.aborted && bearings.length && !assets.some(a => bearings.some(item => item.assetId === a.assetId)))
        bearingHref = systemUrl("connections") + "&dataset_kind=xjtu-sy#public-datasets";
    }).catch(() => {});
    return () => request.abort();
  });

  const stored = $derived(assets.filter(a => cards[a.assetId]?.read && !cards[a.assetId]?.read?.live).length);
  const received = $derived(assets.filter(a => a.flow === "running").length);
  /** 한 칸이 지금 그리는 것: 재생 중이면 위치까지, 아니면 기록 전체(수신 중이면 최근 1시간). */
  function view(card: Card) {
    const read = card.read!, group = read.group!;
    const replay = fraction !== null && !read.live;
    const until = replay ? positionAt(group, fraction!) : group.record.to;
    const changes = (replay ? card.found : read.changes).filter(row => row.from <= until).map(row => ({...row, to: Math.min(row.to, until)}));
    return {group, replay, until, series: replay ? visibleSeries(group, until) : group.series, changes};
  }
  const place = (group: FleetGroup, at: number) => group.axis === "time" ? clockText(at) : measurementLabel(at, group.periodSeconds);
  const span = (group: FleetGroup, change: FleetChange) => group.axis === "time" ? clockText(change.from) + "부터" : change.from + "번째 측정부터";
  /** 'R상·S상·T상' → 'R·S·T상'. */
  const together = (names: string[]) => names.length > 1 && names.every(name => name.endsWith("상"))
    ? names.map(name => name.slice(0, -1)).join("·") + "상" : names.join("·");
  function nearest(points: {x: number; value: number}[], at: number, reach: number) {
    let best: {x: number; value: number} | null = null;
    for (const point of points) if (!best || Math.abs(point.x - at) < Math.abs(best.x - at)) best = point;
    return best && Math.abs(best.x - at) <= reach ? best : null;
  }
</script>

<section class="fleet" aria-labelledby="fleet-title">
  <header class="fleet-head">
    <div><h1 id="fleet-title">설비 모니터링 <small>{assets.length}대</small></h1>
      <p>{#if received}<span class="live-dot"></span>수신 중 {received}대{" · "}{/if}{#if stored}저장 기록 {stored}대{" · "}{/if}목록 확인 {checkedAt}</p></div>
    <div class="tools">
      {#if bearingHref}<a href={bearingHref}>베어링 기록 가져오기</a>{/if}
      <button type="button" class="ui-button" onclick={onRefresh}>다시 확인</button>
    </div>
  </header>
  {#if stored}
    <div class="transport" aria-label="저장 기록 재생">
      <button type="button" class="ui-button play" class:on={playing} onclick={() => playing ? playing = false : play()}>
        <span aria-hidden="true">{playing ? "❚❚" : "▶"}</span>{playing ? "일시정지" : fraction !== null && fraction < 1 ? "이어서 재생" : "기록 재생"}</button>
      <label>재생 속도<select bind:value={seconds}><option value={20}>전체 약 20초</option><option value={60}>전체 약 1분</option><option value={120}>전체 약 2분</option></select></label>
      {#if fraction !== null}
        <input type="range" aria-label="재생 위치" min="0.01" max="1" step="0.001" value={fraction}
          oninput={event => seek(Number(event.currentTarget.value))}/>
        <button type="button" class="ui-button" onclick={stop}>전체 기록 보기</button>
      {:else}<span class="note">저장 기록을 처음부터 재생 · 각 위치까지의 측정으로 변화 판정</span>{/if}
    </div>
  {/if}

  <div class="fleet-grid">
  {#each assets as asset (asset.assetId)}
    {@const card = cards[asset.assetId]}
    {@const name = assetOptionLabel(assets, asset.assetId)}
    <article class="asset" aria-label={name} aria-busy={card?.busy ?? true}>
      <header class="asset-head">
        <h2><a href={card?.read?.href ?? investigationHref(asset.assetId, null, null)}><AssetName label={name}/></a></h2>
        {#if card?.read?.live}<span class="flow live">수신 중</span>
        {:else if card?.read && fraction !== null}<span class="flow replay" class:playing>{playing ? "기록 재생 중" : "기록 재생 · 멈춤"}</span>
        {:else}<span class="flow" class:interrupted={["delayed", "error", "needs-attention"].includes(asset.flow)}>{asset.flow === "stored-history" ? "저장 기록" : flowLabel(asset.flow)}</span>{/if}
      </header>
      {#if card?.read?.group}
        {@const shown = view(card)}
        {@const group = shown.group}
        {@const at = cursor[asset.assetId] ?? null}
        {@const reach = group.axis === "time" ? (group.bucketMs ?? 60_000) : 1}
        {@const episode = latestEpisode(shown.changes)}
        {@const lead = episode.find(row => row.key === group.focus) ?? episode[0]}
        <div class="reading">
          <div class="values">
            <span class="group">{group.label}</span>
            <div class="numbers">
              {#each shown.series as row, index (row.key)}
                {@const point = at !== null ? nearest(row.points, at, reach) : row.points.at(-1)}
                <span class="value"><i style:background={SERIES_COLORS[index % SERIES_COLORS.length]}></i>{#if shown.series.length > 1}<small>{row.short}</small>{/if}<strong>{point ? measure(point.value, group.unit, 4) : "—"}</strong></span>
              {/each}
            </div>
          </div>
          <div class="when">
            {#if at !== null}<span>{group.axis === "time" ? "구간 평균" : "측정값"}{#if picked[asset.assetId] !== null && picked[asset.assetId] !== undefined} <button type="button" aria-label="고른 시점 해제" onclick={() => picked[asset.assetId] = null}>×</button>{/if}</span><time>{place(group, at)}</time>
            {:else}{@const last = shown.series.find(row => row.key === group.focus)?.points.at(-1)}
              {#if last}<span>{shown.replay ? "재생 위치" : card.read.live ? "마지막 측정" : group.axis === "time" ? "마지막 구간 평균" : "마지막 측정"}</span><time>{place(group, group.axis === "time" ? Math.min(shown.until, last.x + (group.bucketMs ?? 0)) : last.x)}</time>{/if}{/if}
          </div>
        </div>
        <FleetTrace {group} series={shown.series} lo={group.record.from} hi={shown.until} changes={shown.changes}
          live={shown.replay && playing} bind:picked={() => picked[asset.assetId] ?? null, value => { picked[asset.assetId] = value; if (value !== null) playing = false; }}
          bind:cursor={() => cursor[asset.assetId] ?? null, value => cursor[asset.assetId] = value}/>
        <footer class="asset-foot">
          <div class="fact">
            {#if lead}
              {@const members = shown.series.filter(row => episode.some(change => change.key === row.key))}
              {#if lead.before !== null && lead.after !== null}<strong>{measure(lead.before, group.unit, 3)} <b>→</b> {measure(lead.after, group.unit, 3)}</strong>{/if}
              <span>{shown.series.length > 1 ? together(members.map(row => row.short)) + " " + group.label : lead.label} {lead.up ? "높음" : "낮음"} · {span(group, lead)}</span>
            {:else if shown.replay && card.analyzed === null}<span>변화 판정 중</span>
            {:else}<span>{card.read.live ? "앞선 관측과 달라진 구간 없음" : "기록 앞부분과 달라진 구간 없음"}</span>{/if}
            {#if shown.replay}<small>판정 범위 · {card.analyzed === null ? "계산 중" : "~" + place(group, card.analyzed)}{card.analyzing && card.analyzed !== null ? " · 다음 위치 계산 중" : ""}</small>{/if}
          </div>
          <a class="investigate" href={card.read.live ? card.read.href : investigationHref(asset.assetId, group, shown.replay ? shown.until : null)}
            onclick={() => playing = false}>{lead ? "변화 구간 조사" : "측정 자세히 보기"} →</a>
        </footer>
      {:else if card?.read}<div class="empty">표시할 측정이 없습니다</div>
      {:else if !card?.error}<div class="empty" role="status">측정 추이를 읽고 있습니다</div>
      {:else}<div class="empty"><span>측정을 읽지 못했습니다</span><button type="button" class="ui-button" onclick={() => reload(asset.assetId)}>다시 읽기</button></div>{/if}
      {#if card?.error && card.read}<p class="read-error" role="status">갱신 실패 · 이전 조회 결과 <button type="button" onclick={() => reload(asset.assetId)}>다시 읽기</button></p>{/if}
    </article>
  {/each}
  </div>
</section>

<style>
  .fleet{display:grid;gap:16px}
  .fleet-head,.asset-head,.reading,.asset-foot{display:flex;align-items:center;justify-content:space-between;gap:12px}
  .fleet-head h1{font-size:1.6rem;margin:0}.fleet-head h1 small{font-size:var(--font-body);font-weight:400;color:var(--color-ink-muted);margin-left:8px}
  .fleet-head p{margin:6px 0 0;font-size:var(--font-label);color:var(--color-ink-muted)}
  .tools{display:flex;gap:12px;align-items:center}.tools>a{font-size:var(--font-small);font-weight:650;color:var(--color-action)}
  .live-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--color-action);margin-right:6px}
  .transport{display:flex;align-items:center;gap:12px 16px;flex-wrap:wrap;padding:10px 14px;border:1px solid var(--color-border);border-radius:var(--radius-panel);background:var(--color-surface)}
  .transport label{display:flex;align-items:center;gap:6px;font-size:var(--font-label);color:var(--color-ink-muted)}
  .transport select{padding:6px 8px}
  .transport input{flex:1;min-width:200px;accent-color:var(--color-action)}
  .transport .note{font-size:var(--font-label);color:var(--color-ink-muted)}
  .play{display:inline-flex;align-items:center;gap:8px;min-width:128px;justify-content:center}.play span{font-size:.8em}
  .play.on{color:var(--color-action);border-color:var(--color-action)}
  .fleet-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px;align-items:start}
  .asset{padding:16px 20px;background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius-panel);display:grid;gap:12px;min-width:0}
  .asset-head h2{margin:0;font-size:1.1rem}.asset-head a{color:var(--color-ink);text-decoration:none}.asset-head a:hover{text-decoration:underline}
  .flow{font-size:var(--font-label);color:var(--color-ink-muted);border:1px solid var(--color-border);border-radius:4px;padding:3px 7px;white-space:nowrap}
  .flow.live,.flow.replay.playing{color:var(--color-action);background:var(--color-surface-selected)}
  .flow.interrupted{color:var(--color-caution-ink);background:var(--color-caution-surface)}
  .reading{align-items:end}
  .values{display:grid;gap:4px;min-width:0}
  .group{font-size:var(--font-small);color:var(--color-ink-muted)}
  .numbers{display:flex;flex-wrap:wrap;gap:4px 18px}
  .value{display:inline-flex;align-items:baseline;gap:6px;font-variant-numeric:tabular-nums}
  .value i{display:inline-block;width:14px;height:3px;border-radius:2px;align-self:center}
  .value small{font-size:var(--font-small);color:var(--color-ink-muted)}
  .value strong{font-size:1.45rem;line-height:1.15}
  .when{display:grid;gap:3px;text-align:right;font-size:var(--font-label);color:var(--color-ink-muted);white-space:nowrap}
  .when time{color:var(--color-ink);font-variant-numeric:tabular-nums}
  .when button{border:0;background:none;color:var(--color-ink-muted);cursor:pointer;font-size:16px;line-height:1;padding:0 2px}
  .asset-foot{align-items:end;border-top:1px solid var(--color-border);padding-top:10px;min-height:48px}
  .fact{display:grid;gap:3px;min-width:0;font-size:var(--font-small)}
  .fact strong{font-size:var(--font-body);font-variant-numeric:tabular-nums}.fact b{font-weight:400;color:var(--color-ink-muted);margin-inline:4px}
  .fact small{font-size:var(--font-label);color:var(--color-ink-muted);font-variant-numeric:tabular-nums}
  .investigate{font-size:var(--font-small);font-weight:650;white-space:nowrap;color:var(--color-action)}
  .empty{display:grid;place-content:center;gap:12px;min-height:290px;color:var(--color-ink-muted);font-size:var(--font-small)}
  .read-error{margin:0;font-size:var(--font-label);color:var(--color-caution-ink)}
  .read-error button{font:inherit;border:0;background:none;text-decoration:underline;cursor:pointer}
  @media(min-width:1800px){.fleet-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
  @media(max-width:1000px){.fleet-grid{grid-template-columns:1fr}}
</style>
