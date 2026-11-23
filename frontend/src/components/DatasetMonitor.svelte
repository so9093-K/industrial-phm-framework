<script lang="ts">
  import {equipmentRole} from "../equipment-roles";
  import {onDestroy, onMount, untrack} from "svelte";
  import {assetOptionLabel, type Asset} from "../monitor";
  import {attention, focusChannel, monitorDatasets, readFleet, readFleetChanges, sharedSpan, splitChanges, untilAt,
    type FleetChange, type FleetGroup, type FleetRead, type MonitorDataset} from "../fleet-observation";
  import {clockText} from "../asset-timeline";
  import {elapsedText, measurementScale} from "../time-axis";
  import {readPublicDatasets, type PublicDatasets} from "../public-datasets";
  import {recentAsset} from "../observation";
  import AssetName from "./AssetName.svelte";
  import MonitorRow from "./MonitorRow.svelte";
  import DatasetSchematic from "./DatasetSchematic.svelte";
  import TaskDialog from "./TaskDialog.svelte";
  import {systemUrl} from "../routes";

  /** 설비별 실제 추이를 먼저 보고, 선택한 변화에서 조사와 AI 질문을 연다. */
  let {assets, cycle, checkedAt, onRefresh}: {assets: Asset[]; cycle: number; checkedAt: string; onRefresh: () => void} = $props();

  let publicData: PublicDatasets | null = $state(null), publicRead = $state(false);
  onMount(() => {
    const request = new AbortController();
    void readPublicDatasets(request.signal).then(data => { if (!request.signal.aborted) publicData = data; })
      .catch(() => {}).finally(() => { if (!request.signal.aborted) publicRead = true; });
    return () => request.abort();
  });
  const datasets = $derived(publicRead ? monitorDatasets(assets, publicData) : []);
  const all = $derived({key:"all",title:"전체 설비",assetIds:assets.map(asset=>asset.assetId),detail:Object.assign({},...datasets.map(row=>row.detail))} satisfies MonitorDataset);
  const filters=$derived([all,...datasets]);
  const filterLabel=(row:MonitorDataset)=>({all:"전체 설비","aihub-239":"전력·운전","xjtu-sy":"베어링 진동",connected:"연결한 설비"}[row.key]??row.title);
  let guideOpen=$state(false);
  // 조사 화면에 다녀오면 보던 데이터셋으로 돌아온다(주소에 없으면 이 탭에서 마지막으로 본 것).
  const LAST = "phm.monitor.view.v2";
  function lastDataset():string|null {try{return sessionStorage.getItem(LAST);}catch{return null;}}
  let chosen = $state(new URLSearchParams(location.search).get("dataset") ?? lastDataset() ?? "all");
  const dataset: MonitorDataset | undefined = $derived(filters.find(row => row.key === chosen) ?? all);
  $effect(() => { const key = dataset?.key; if (key) try { sessionStorage.setItem(LAST, key); } catch { /* 기억하지 못해도 첫 데이터셋을 연다. */ } });
  function choose(key: string) {
    playing = false;
    chosen = key;
    const url = new URL(location.href);
    url.searchParams.set("dataset", key);
    history.replaceState(history.state, "", url);
  }

  type Card = {read: FleetRead | null; error: boolean; busy: boolean; found: FleetChange[]; analyzed: number | null; failedAt: number | null;
    /** 이 읽기에 요청한 신호 이름(null이면 설비 자신의 첫 변화 묶음). */
    like: string | null};
  /** 설비마다 처음 읽은 묶음(자신의 첫 변화). 데이터셋의 '보는 신호' 선택지가 된다. */
  let defaults: Record<string, {like: string; label: string}> = $state({});
  // 데이터셋마다 보는 신호는 하나. 정하지 않았으면 가장 먼저 볼 설비(첫 줄)의 묶음을 따른다.
  let signals: Record<string, string> = $state(Object.fromEntries([...new URLSearchParams(location.search)].filter(([key]) => key === "signal")
    .map(([, value]) => [new URLSearchParams(location.search).get("dataset") ?? "", value])));
  function showSignal(assetId:string,channel:string){
    const category=datasets.find(row=>row.assetIds.includes(assetId));
    if(dataset?.key==="all"&&category)choose(category.key);
    pickSignal(channel);
  }
  function pickSignal(like: string) {
    if (!dataset) return;
    playing = false;
    signals = {...signals, [dataset.key]: like};
    const url = new URL(location.href);
    url.searchParams.set("dataset", dataset.key);
    url.searchParams.set("signal", like);
    history.replaceState(history.state, "", url);
  }
  let cards: Record<string, Card> = $state({});
  const blank = (): Card => ({read: null, error: false, busy: true, found: [], analyzed: null, failedAt: null, like: null});

  // 재생 위치(비율)는 데이터셋마다 따로, 조사 화면에 다녀와도 이어 보도록 탭에 남긴다.
  const STORE = "phm.monitor.replay";
  function restored(): Record<string, number> {
    try { return JSON.parse(sessionStorage.getItem(STORE) ?? "{}") as Record<string, number>; } catch { return {}; }
  }
  let replays: Record<string, number> = $state(restored()), playing = $state(false), seconds = $state(20);
  const fraction = $derived(dataset && replays[dataset.key] !== undefined ? replays[dataset.key] : null);
  $effect(() => {
    const value = JSON.stringify(replays);
    try { sessionStorage.setItem(STORE, value); } catch { /* 저장하지 못해도 모니터링은 된다. */ }
  });

  // 읽기: 고른 데이터셋의 설비만, 목록이 바뀌거나 수신 중인 출처의 관측 주기가 바뀔 때만 다시 읽는다.
  const wanted = new Map<string, string>(), queue = new Set<string>(), loading = new Map<string, AbortController>(), desired = new Map<string, string | null>();
  let disposed = false;
  const members = $derived(dataset ? assets.filter(asset => dataset.assetIds.includes(asset.assetId)) : []);
  // 줄 순서는 기록 전체의 결과로 한 번 정하고 재생 중에는 바꾸지 않는다(재생 중 줄이 움직이면 읽을 수 없다).
  const rows = $derived.by(() => {
    const list = members.map(asset => ({asset, card: cards[asset.assetId]}));
    return list.sort((a, b) => {
      const [x1, x2] = attention(a.card?.read ?? null), [y1, y2] = attention(b.card?.read ?? null);
      return x1 - y1 || x2 - y2 || a.asset.assetId.localeCompare(b.asset.assetId, "ko");
    });
  });
  // 보는 신호: 고른 것, 아니면 모든 줄의 첫 읽기가 끝난 뒤 첫 줄의 묶음. 그 전에는 설비 자신의 묶음으로 읽는다.
  const firstRead = $derived(members.length > 0 && members.every(a => cards[a.assetId]?.read || cards[a.assetId]?.error));
  const signal = $derived(dataset ? signals[dataset.key] ?? null : null);
  // 기본 신호는 모든 줄을 처음 읽은 순간 한 번만 정한다. 다시 읽어 줄 순서가 바뀌어도 따라 바뀌지 않는다.
  $effect(() => {
    if (!dataset || dataset.key === "all" || !firstRead || signals[dataset.key]) return;
    const first = rows.map(row => defaults[row.asset.assetId]?.like).find(Boolean);
    if (first) untrack(() => signals = {...signals, [dataset.key]: first});
  });
  const options = $derived.by(() => {
    if(dataset?.key==="all")return [];
    const out = new Map<string, string>();
    for (const asset of members) { const row = defaults[asset.assetId]; if (row && ![...out.values()].includes(row.label)) out.set(row.like, row.label); }
    return [...out].map(([like, label]) => ({like, label}));
  });
  const revisions = $derived(JSON.stringify(members.map(a => {
    const read = cards[a.assetId]?.read;
    // 이미 같은 신호 묶음을 그리고 있으면 다시 읽지 않는다.
    const like = dataset?.key === "all" ? null : signal && read?.group && !read.live && focusChannel(read.group) !== signal ? signal : cards[a.assetId]?.like ?? null;
    return [a.assetId, (a.overviewRevision ?? JSON.stringify([a.lastObservedAt, a.lastReceivedAt, a.lastPosition])) + ":" + (recentAsset(a) ? cycle : 0) + "|" + (like ?? ""), like];
  })));
  function drain() {
    while (loading.size < 2 && queue.size && !disposed) {
      const id = [...queue][0];
      queue.delete(id);
      const revision = wanted.get(id), asset = assets.find(a => a.assetId === id);
      if (!asset) continue;
      const request = new AbortController(), like = desired.get(id) ?? null;
      loading.set(id, request);
      cards[id] = {...(cards[id] ?? blank()), busy: true, error: false};
      void readFleet(asset, request.signal, like).then(read => {
        if (request.signal.aborted || wanted.get(id) !== revision) return;
        // 묶음이 바뀌었을 수 있으니 재생 판정은 새 묶음으로 다시 한다.
        cards[id] = {...cards[id], read, like, busy: false, error: false, found: [], analyzed: null, failedAt: null};
        requested.delete(id);
        if (like === null && read.group && !read.live) defaults[id] = {like: focusChannel(read.group), label: read.group.label};
        analyze();
      }).catch(() => {
        if (!request.signal.aborted && wanted.get(id) === revision) cards[id] = {...cards[id], busy: false, error: true};
      }).finally(() => { loading.delete(id); drain(); });
    }
  }
  $effect(() => {
    const current = new Map<string, string>((JSON.parse(revisions) as [string, string, string | null][]).map(([id, version, like]) => {
      desired.set(id, like);
      return [id, version];
    }));
    untrack(() => {
      for (const [id, version] of current) {
        const stored = cards[id]?.read && !cards[id]?.read?.live;
        // 재생 중인 저장 기록은 다시 읽지 않는다. 보는 신호를 바꾼 경우만 예외다.
        if (wanted.get(id) === version || (fraction !== null && stored && cards[id]?.like === desired.get(id))) continue;
        wanted.set(id, version); queue.add(id);
      }
      drain();
    });
  });
  function reload(id: string) { wanted.set(id, (wanted.get(id) ?? "") + ":retry"); queue.add(id); drain(); }

  const stored = $derived(rows.flatMap(row => row.card?.read?.group && !row.card.read.live ? [row.card.read.group] : []));
  const shared = $derived(sharedSpan(stored));
  const replay = (card: Card | undefined) => fraction !== null && !!card?.read?.group && !card.read.live;
  function untilOf(card: Card): number | null {
    const group = card.read!.group!;
    return replay(card) ? untilAt(group, fraction!, shared) : group.record.to;
  }
  const clock = $derived(shared && fraction !== null ? shared.from + (shared.to - shared.from) * fraction : null);

  // 변화 판정: 설비마다 한 번에 하나, 끝나면 그때의 재생 위치로 다시. 가장 최근 판정만 표시한다.
  const judging = new Map<string, AbortController>(), requested = new Map<string, number>(), started = new Map<string, number>();
  let analysisTimer: ReturnType<typeof setTimeout> | null = null;
  function cancelAnalysisTimer() {
    if (analysisTimer !== null) clearTimeout(analysisTimer);
    analysisTimer = null;
  }
  function analyze() {
    cancelAnalysisTimer();
    if (fraction === null || disposed || !dataset) return;
    let retryIn = Infinity;
    for (const id of dataset.assetIds) {
      const card = cards[id], group = card?.read?.group;
      if (!card || !group || card.read?.live || judging.has(id)) continue;
      const until = untilOf(card);
      if (until === null || requested.get(id) === until) continue;
      const wait = 500 - (Date.now() - (started.get(id) ?? 0));
      if (wait > 0) {
        retryIn = Math.min(retryIn, wait);
        continue;
      }
      requested.set(id, until); started.set(id, Date.now());
      const request = new AbortController();
      judging.set(id, request);
      card.failedAt = null;
      void readFleetChanges(id, group, until, request.signal).then(found => {
        const now = cards[id] ? untilOf(cards[id]) : null;
        if (request.signal.aborted || cards[id]?.read?.group !== group || fraction === null || now === null || now < until) return;
        cards[id].found = splitChanges(group, found).changes;
        cards[id].analyzed = until;
      }).catch(() => {
        if (!request.signal.aborted && cards[id]?.read?.group === group) cards[id].failedAt = until;
      }).finally(() => {
        if (judging.get(id) !== request) return;
        judging.delete(id);
        analyze();
      });
    }
    // A user can seek and pause during the cooldown. Always read that last requested position.
    if (Number.isFinite(retryIn)) analysisTimer = setTimeout(analyze, retryIn);
  }
  function resetJudgement() {
    cancelAnalysisTimer();
    for (const request of judging.values()) request.abort();
    judging.clear(); requested.clear(); started.clear();
    for (const card of Object.values(cards)) { card.found = []; card.analyzed = null; card.failedAt = null; }
  }
  function setFraction(value: number | null) {
    if (!dataset) return;
    if (value === null) { const {[dataset.key]: _gone, ...rest} = replays; replays = rest; }
    else replays = {...replays, [dataset.key]: Math.max(0.01, Math.min(1, value))};
  }
  $effect(() => {
    if (!playing) return;
    const id = setInterval(() => {
      const next = Math.min(1, (fraction ?? 0.1) + 0.1 / seconds);
      setFraction(next);
      if (next >= 1) playing = false;
      analyze();
    }, 100);
    return () => clearInterval(id);
  });
  function play() {
    if (fraction === null || fraction >= 1) { resetJudgement(); setFraction(0.1); }
    playing = true;
    analyze();
  }
  function seek(value: number) {
    playing = false;
    if (fraction !== null && value < fraction) resetJudgement();
    setFraction(value);
    analyze();
  }
  function stop() { playing = false; resetJudgement(); setFraction(null); }
  $effect(() => { dataset?.key; untrack(() => { resetJudgement(); analyze(); }); });
  onDestroy(() => { disposed = true; cancelAnalysisTimer(); for (const request of [...loading.values(), ...judging.values()]) request.abort(); });

  const chartHeight=$derived(rows.length===1?280:240);
  const legend = $derived(rows.find(row => row.card?.read?.group)?.card?.read?.group ?? null);
  const counts = $derived({
    stored: rows.filter(row => row.card?.read && !row.card.read.live).length,
    live: rows.filter(row => row.card?.read?.live).length,
  });
  const position = (group: FleetGroup | null, at: number) => !group ? "" : group.axis === "time" ? clockText(at)
    : "시험 시작 후 " + elapsedText((at - 1) * (group.periodSeconds ?? 60));
</script>

<section class="monitor" aria-label="데이터셋 관제">
  <header class="bar">
    <h1>설비 모니터링 <span>{assets.length}대</span></h1>
    <div class="status"><span>목록 갱신 {checkedAt}</span><button type="button" class="ui-button quiet" onclick={onRefresh}>새로고침</button>
      <a class="ui-button quiet" href={systemUrl("connections")}>데이터 추가</a></div>
  </header>

  {#if dataset}
    <div class="toolbar">
      <nav class="datasets" aria-label="설비 종류">
        {#each filters as row (row.key)}
          <button type="button" aria-pressed={row.key === dataset.key} onclick={() => choose(row.key)}>
            {filterLabel(row)} <span>{row.assetIds.length}</span>
          </button>
        {/each}
      </nav>
      {#if counts.stored}
        <div class="transport" class:with-progress={fraction !== null} aria-label="저장 기록 모니터링">
          <button type="button" class="ui-button play" class:on={playing} onclick={() => playing ? playing = false : play()}>
            <span aria-hidden="true">{playing ? "❚❚" : "▶"}</span>{playing ? "일시정지" : fraction !== null && fraction < 1 ? "이어서 모니터링" : "모니터링 시작"}</button>
          <select bind:value={seconds} aria-label="재생 속도"><option value={20}>전체 20초</option><option value={60}>전체 1분</option><option value={120}>전체 2분</option></select>
          {#if fraction !== null}
            <input type="range" aria-label="재생 시점" min="0.01" max="1" step="0.001" value={fraction} oninput={event => seek(Number(event.currentTarget.value))}/>
            {#if clock !== null}<output>{position(legend, clock)}</output>{/if}
            <button type="button" class="ui-button quiet" onclick={stop}>전체 기록</button>
          {/if}
        </div>
      {/if}
      {#if options.length > 1}
        <div class="signals" role="radiogroup" aria-label="보는 신호">
          {#each options as option (option.like)}
            <button type="button" role="radio" aria-checked={legend !== null && focusChannel(legend) === option.like || signal === option.like}
              onclick={() => pickSignal(option.like)}>{option.label}</button>
          {/each}
        </div>
      {/if}
      <button type="button" class="guide" onclick={()=>guideOpen=true}>설비·데이터 안내</button>
    </div>

    <ol class="rows" class:single={rows.length===1}>
      {#each rows as {asset, card} (asset.assetId)}
        {@const name = assetOptionLabel(assets, asset.assetId)}
        {@const home = datasets.find(row => row.assetIds.includes(asset.assetId))}
        {@const switching = !!card?.busy && card.like !== (desired.get(asset.assetId) ?? null)}
        {#if card?.read?.group && !switching}
          <MonitorRow assetId={asset.assetId} {name} read={card.read} group={card.read.group}
            replaying={replay(card)} until={untilOf(card)} found={card.found} analyzed={card.analyzed} analysisFailed={card.failedAt !== null && card.failedAt === untilOf(card)}
            lo={shared?.from ?? card.read.group.record.from} hi={shared ? (clock ?? shared.to) : (untilOf(card) ?? card.read.group.record.from)}
            role={equipmentRole(home?.key, home?.detail[asset.assetId])?.short ?? null}
            height={chartHeight} {playing} onPause={() => playing = false} onSignal={channel=>showSignal(asset.assetId,channel)}/>
        {:else}
          <!-- 읽는 동안에도 다 읽은 카드와 비슷한 높이로 두어, 옆 카드와 화면이 출렁이지 않게 한다. -->
          <li class="row" style:min-height={chartHeight + 260 + "px"}>
            <div class="who"><span class="name"><AssetName label={name}/></span><span class="detail">{dataset.detail[asset.assetId] ?? ""}</span></div>
            <div class="chart pending" style:height={chartHeight + "px"}>
              {#if card?.error}<span>측정을 읽지 못했습니다</span><button type="button" class="ui-button quiet" onclick={() => reload(asset.assetId)}>다시 읽기</button>
              {:else if card?.read && !switching && card.like}<span>이 설비에는 '{options.find(row => row.like === card.like)?.label ?? card.like}' 기록이 없습니다</span>
              {:else if card?.read && !switching}<span>표시할 측정이 없습니다</span>
              {:else}<span role="status">{switching ? "보는 신호로 다시 읽고 있습니다" : "측정 추이를 읽고 있습니다"}</span>{/if}
            </div>
          </li>
        {/if}
      {/each}
    </ol>
  {/if}
  <TaskDialog title="설비와 측정 데이터" bind:open={guideOpen}>
    <div class="data-guide">{#each datasets.filter(row=>dataset?.key==="all"||row.key===dataset?.key) as row(row.key)}
      <h2>{row.title}</h2><DatasetSchematic kind={row.key} equipment={new Set(Object.values(row.detail)).size===1?Object.values(row.detail)[0]:null}/>
    {/each}</div>
  </TaskDialog>
</section>

<style>
  .monitor{display:grid;gap:12px;min-width:0}
  .bar{display:flex;justify-content:space-between;align-items:center;gap:10px}
  h1{margin:0;font-size:1.35rem;line-height:1.2}h1 span{font-size:var(--font-small);font-weight:500;color:var(--color-ink-muted);margin-left:8px}
  .datasets{display:flex;flex-wrap:wrap;gap:4px}
  .datasets button{border:0;border-radius:6px;background:transparent;font:inherit;font-size:var(--font-small);color:var(--color-ink-muted);padding:6px 10px;cursor:pointer}
  .datasets button[aria-pressed="true"]{background:var(--color-sidebar);color:white;font-weight:650}.datasets button span{margin-left:4px;opacity:.75}
  .status{display:flex;align-items:center;flex-wrap:wrap;justify-content:end;gap:8px;font-size:12px;color:var(--color-ink-muted)}
  .status>span{text-align:right}.status a{text-decoration:none}
  /* 맨 위 조작은 모두 같은 높이(34px): 새로고침·데이터 추가·모니터링·속도·전체 기록. */
  .quiet{display:inline-flex;align-items:center;min-height:0;height:34px;box-sizing:border-box;padding:0 12px;font-size:var(--font-label)}
  .toolbar{display:flex;align-items:center;gap:6px 18px;flex-wrap:wrap;min-height:36px}
  .transport{display:flex;align-items:center;gap:8px;min-width:0}
  .transport.with-progress{flex:1 1 480px;max-width:850px}
  .transport select{height:34px;min-height:0;box-sizing:border-box;padding:0 8px;font-size:var(--font-label)}
  .transport input{flex:1;min-width:90px;accent-color:var(--color-action)}
  .transport output{font-size:var(--font-label);font-variant-numeric:tabular-nums;white-space:nowrap}
  .play{display:inline-flex;align-items:center;gap:8px;min-height:0;height:34px;box-sizing:border-box;padding:0 12px;font-size:var(--font-small)}.play span{font-size:.75em}
  .play.on{color:var(--color-action);border-color:var(--color-action)}
  .signals{display:flex;gap:2px;flex-wrap:wrap}.signals button{border:0;background:none;padding:5px 10px;border-radius:6px;font:inherit;font-size:var(--font-label);color:var(--color-ink-muted);cursor:pointer}
  .signals button[aria-checked="true"]{background:var(--color-surface-selected);color:var(--color-action);font-weight:650}
  .guide{margin-left:auto;border:0;background:none;color:var(--color-action);font:inherit;font-size:var(--font-label);cursor:pointer;padding:6px}
  .rows{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin:0;padding:0;list-style:none;align-items:start;min-width:0}.rows.single{grid-template-columns:minmax(0,1fr)}
  .row{list-style:none;padding:20px;background:var(--color-surface);border:1px solid var(--color-border);border-radius:10px;min-width:0}
  .who{display:flex;justify-content:space-between;gap:8px}.name{font-weight:650}.detail{font-size:var(--font-label);color:var(--color-ink-muted)}
  .chart.pending{display:flex;align-items:center;justify-content:center;gap:12px;min-height:240px;font-size:var(--font-label);color:var(--color-ink-muted)}
  .data-guide{display:grid;gap:16px}.data-guide h2{margin:0;font-size:var(--font-body)}
  @media(max-width:1050px){.rows{grid-template-columns:minmax(0,1fr)}}
  @media(max-width:650px){
    .bar{align-items:flex-start;flex-wrap:wrap}.status{justify-content:start}
    .status>span{order:1;flex-basis:100%;text-align:left}
    .toolbar{gap:6px 8px}.datasets{flex-basis:100%}
    .transport{flex-wrap:wrap}.transport input{flex-basis:100%}
  }
</style>
