<script lang="ts">
  import {onDestroy, onMount, untrack} from "svelte";
  import {assetOptionLabel, type Asset} from "../monitor";
  import {attention, focusChannel, monitorDatasets, ongoing, readFleet, readFleetChanges, sharedSpan, splitChanges, untilAt,
    SERIES_COLORS, type FleetChange, type FleetGroup, type FleetRead, type MonitorDataset} from "../fleet-observation";
  import {clockText} from "../asset-timeline";
  import {elapsedText, measurementScale} from "../time-axis";
  import {readPublicDatasets, type PublicDatasets} from "../public-datasets";
  import {recentAsset} from "../observation";
  import AssetName from "./AssetName.svelte";
  import MonitorRow from "./MonitorRow.svelte";
  import DatasetSchematic from "./DatasetSchematic.svelte";
  import XAxis from "./XAxis.svelte";

  /** 데이터셋 관제: 한 데이터셋의 설비를 한 줄씩, 같은 신호 묶음과 같은 규칙의 그래프로 늘어놓는다.
   * 줄 순서는 마지막 측정까지 이어지는 변화 → 끝난 변화 → 변화 없음. 사람이 정할 것은 '어느 설비를 먼저 열어 볼지'다.
   * 저장 기록은 데이터셋 단위로 재생한다. 기간이 겹치는 기록은 하나의 시계로, 아니면 기록마다 같은 비율로 움직인다. */
  let {assets, cycle, checkedAt, onRefresh}: {assets: Asset[]; cycle: number; checkedAt: string; onRefresh: () => void} = $props();

  let publicData: PublicDatasets | null = $state(null), publicRead = $state(false);
  onMount(() => {
    const request = new AbortController();
    void readPublicDatasets(request.signal).then(data => { if (!request.signal.aborted) publicData = data; })
      .catch(() => {}).finally(() => { if (!request.signal.aborted) publicRead = true; });
    return () => request.abort();
  });
  const datasets = $derived(publicRead ? monitorDatasets(assets, publicData) : []);
  // 조사 화면에 다녀오면 보던 데이터셋으로 돌아온다(주소에 없으면 이 탭에서 마지막으로 본 것).
  const LAST = "phm.monitor.dataset";
  function lastDataset(): string | null { try { return sessionStorage.getItem(LAST); } catch { return null; } }
  let chosen = $state(new URLSearchParams(location.search).get("dataset") ?? lastDataset());
  const dataset: MonitorDataset | undefined = $derived(datasets.find(row => row.key === chosen) ?? datasets[0]);
  $effect(() => { const key = dataset?.key; if (key) try { sessionStorage.setItem(LAST, key); } catch { /* 기억하지 못해도 첫 데이터셋을 연다. */ } });
  function choose(key: string) {
    playing = false;
    chosen = key;
    const url = new URL(location.href);
    url.searchParams.set("dataset", key);
    history.replaceState(history.state, "", url);
  }

  type Card = {read: FleetRead | null; error: boolean; busy: boolean; found: FleetChange[]; analyzed: number | null; analyzing: boolean;
    /** 이 읽기에 요청한 신호 이름(null이면 설비 자신의 첫 변화 묶음). */
    like: string | null};
  /** 설비마다 처음 읽은 묶음(자신의 첫 변화). 데이터셋의 '보는 신호' 선택지가 된다. */
  let defaults: Record<string, {like: string; label: string}> = $state({});
  // 데이터셋마다 보는 신호는 하나. 정하지 않았으면 가장 먼저 볼 설비(첫 줄)의 묶음을 따른다.
  let signals: Record<string, string> = $state(Object.fromEntries([...new URLSearchParams(location.search)].filter(([key]) => key === "signal")
    .map(([, value]) => [new URLSearchParams(location.search).get("dataset") ?? "", value])));
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
  const blank = (): Card => ({read: null, error: false, busy: true, found: [], analyzed: null, analyzing: false, like: null});

  // 재생 위치(비율)는 데이터셋마다 따로, 조사 화면에 다녀와도 이어 보도록 탭에 남긴다.
  const STORE = "phm.monitor.replay";
  function restored(): Record<string, number> {
    try { return JSON.parse(sessionStorage.getItem(STORE) ?? "{}") as Record<string, number>; } catch { return {}; }
  }
  let replays: Record<string, number> = $state(restored()), playing = $state(false), seconds = $state(60);
  const fraction = $derived(dataset && replays[dataset.key] !== undefined ? replays[dataset.key] : null);
  $effect(() => {
    const value = JSON.stringify(replays);
    try { sessionStorage.setItem(STORE, value); } catch { /* 저장하지 못해도 재생은 된다. */ }
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
    if (!dataset || !firstRead || signals[dataset.key]) return;
    const first = rows.map(row => defaults[row.asset.assetId]?.like).find(Boolean);
    if (first) untrack(() => signals = {...signals, [dataset.key]: first});
  });
  const options = $derived.by(() => {
    const out = new Map<string, string>();
    for (const asset of members) { const row = defaults[asset.assetId]; if (row && ![...out.values()].includes(row.label)) out.set(row.like, row.label); }
    return [...out].map(([like, label]) => ({like, label}));
  });
  const revisions = $derived(JSON.stringify(members.map(a => {
    const read = cards[a.assetId]?.read;
    // 이미 같은 신호 묶음을 그리고 있으면 다시 읽지 않는다.
    const like = signal && read?.group && !read.live && focusChannel(read.group) !== signal ? signal : cards[a.assetId]?.like ?? null;
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
        cards[id] = {...cards[id], read, like, busy: false, error: false, found: [], analyzed: null};
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
  function analyze() {
    if (fraction === null || disposed || !dataset) return;
    for (const id of dataset.assetIds) {
      const card = cards[id], group = card?.read?.group;
      if (!card || !group || card.read?.live || judging.has(id) || Date.now() - (started.get(id) ?? 0) < 500) continue;
      const until = untilOf(card);
      if (until === null || requested.get(id) === until) continue;
      requested.set(id, until); started.set(id, Date.now());
      const request = new AbortController();
      judging.set(id, request);
      card.analyzing = true;
      void readFleetChanges(id, group, until, request.signal).then(found => {
        const now = cards[id] ? untilOf(cards[id]) : null;
        if (request.signal.aborted || fraction === null || now === null || now < until) return;
        cards[id].found = splitChanges(group, found).changes;
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
  onDestroy(() => { disposed = true; for (const request of [...loading.values(), ...judging.values()]) request.abort(); });

  let innerHeight = $state(900), list: HTMLOListElement | null = $state(null), listTop = $state(260);
  $effect(() => { innerHeight; rows.length; shared; if (list) listTop = list.getBoundingClientRect().top + scrollY; });
  // 설비가 적으면 줄이 화면 높이를 나눠 쓰고, 많으면 한 줄 140px로 내려 읽는다.
  const rowHeight = $derived(Math.max(140, Math.min(rows.length === 1 ? 440 : 300, Math.floor((innerHeight - listTop - 16 - 8 * (rows.length - 1)) / Math.max(1, rows.length)))));
  const chartHeight = $derived(rowHeight - (shared ? 26 : 50));
  const legend = $derived(rows.find(row => row.card?.read?.group)?.card?.read?.group ?? null);
  const counts = $derived({
    ongoing: rows.filter(row => row.card?.read?.group && ongoing(row.card.read.group, row.card.read.changes)).length,
    stored: rows.filter(row => row.card?.read && !row.card.read.live).length,
    live: rows.filter(row => row.card?.read?.live).length,
  });
  const position = (group: FleetGroup | null, at: number) => !group ? "" : group.axis === "time" ? clockText(at)
    : "시험 시작 후 " + elapsedText((at - 1) * (group.periodSeconds ?? 60));
</script>

<svelte:window bind:innerHeight/>
<section class="monitor" aria-label="데이터셋 관제">
  <header class="bar">
    <div class="datasets" role="tablist" aria-label="데이터셋">
      {#each datasets as row (row.key)}
        <button type="button" role="tab" aria-selected={row.key === dataset?.key} onclick={() => choose(row.key)}>
          <strong>{row.title}</strong><span>{row.assetIds.length}대</span>
        </button>
      {/each}
    </div>
    <div class="status">
      <span>{#if counts.live}<i class="live-dot"></i>수신 중 {counts.live}대{" · "}{/if}{#if counts.stored}저장 기록 {counts.stored}대{" · "}{/if}목록 확인 {checkedAt}</span>
      <button type="button" class="ui-button quiet" onclick={onRefresh}>다시 확인</button>
    </div>
  </header>

  {#if dataset}
    {@const kinds = [...new Set(Object.values(dataset.detail))]}
    <DatasetSchematic kind={dataset.key} equipment={dataset.key === "aihub-239" && kinds.length === 1 ? kinds[0] : null}/>
    <div class="toolbar">
      {#if counts.stored}
        <div class="transport" aria-label="저장 기록 재생">
          <button type="button" class="ui-button play" class:on={playing} onclick={() => playing ? playing = false : play()}>
            <span aria-hidden="true">{playing ? "❚❚" : "▶"}</span>{playing ? "일시정지" : fraction !== null && fraction < 1 ? "이어서 재생" : "기록 재생"}</button>
          <select bind:value={seconds} aria-label="재생 속도"><option value={20}>전체 20초</option><option value={60}>전체 1분</option><option value={120}>전체 2분</option></select>
          {#if fraction !== null}
            <input type="range" aria-label="재생 위치" min="0.01" max="1" step="0.001" value={fraction} oninput={event => seek(Number(event.currentTarget.value))}/>
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
      {#if legend}
        <ul class="legend" aria-label="그래프 읽는 법">
          {#each legend.series as row, index (row.key)}<li><i class="swatch" style:background={SERIES_COLORS[index % SERIES_COLORS.length]}></i>{row.short}</li>{/each}
          <li><i class="dash"></i>처음 수준</li>
          <li><i class="band"></i>찾은 변화</li>
          {#if rows.length > 1}<li class="summary">{rows.length}대 중 변화 이어짐 {counts.ongoing}대</li>{/if}
        </ul>
      {/if}
    </div>

    {#if shared}
      <div class="axis-row" aria-hidden="true"><span></span><XAxis lo={shared.from} hi={clock ?? shared.to}
        scale={legend?.axis === "acquisition" ? measurementScale(legend.periodSeconds) : {kind: "clock"}}/><span></span></div>
    {/if}

    <ol class="rows" bind:this={list}>
      {#each rows as {asset, card} (asset.assetId)}
        {@const name = assetOptionLabel(assets, asset.assetId)}
        {@const switching = !!card?.busy && card.like !== (desired.get(asset.assetId) ?? null)}
        {#if card?.read?.group && !switching}
          <MonitorRow assetId={asset.assetId} {name} detail={name.startsWith(dataset.detail[asset.assetId] ?? "\u0000") ? null : dataset.detail[asset.assetId] ?? null} read={card.read} group={card.read.group}
            replaying={replay(card)} until={untilOf(card)} found={card.found} analyzed={card.analyzed}
            lo={shared?.from ?? card.read.group.record.from} hi={shared ? (clock ?? shared.to) : (untilOf(card) ?? card.read.group.record.from)}
            shared={!!shared} height={chartHeight} {playing} onPause={() => playing = false} onSignal={pickSignal}/>
        {:else}
          <li class="row" style:--row={rowHeight + "px"}>
            <div class="who"><span class="name"><AssetName label={name}/></span><span class="detail">{dataset.detail[asset.assetId] ?? ""}</span></div>
            <div class="chart pending" style:height={chartHeight + "px"}>
              {#if card?.error}<span>측정을 읽지 못했습니다</span><button type="button" class="ui-button quiet" onclick={() => reload(asset.assetId)}>다시 읽기</button>
              {:else if card?.read && !switching && card.like}<span>이 설비에는 '{options.find(row => row.like === card.like)?.label ?? card.like}' 기록이 없습니다</span>
              {:else if card?.read && !switching}<span>표시할 측정이 없습니다</span>
              {:else}<span role="status">{switching ? "보는 신호로 다시 읽고 있습니다" : "측정 추이를 읽고 있습니다"}</span>{/if}
            </div>
            <div></div>
          </li>
        {/if}
      {/each}
    </ol>
  {:else if publicRead}<p class="none">설비가 없습니다.</p>{/if}
</section>

<style>
  .monitor{display:grid;gap:12px}
  .bar{display:flex;align-items:end;justify-content:space-between;gap:16px;border-bottom:1px solid var(--color-border)}
  .datasets{display:flex;gap:4px;min-width:0;overflow-x:auto}
  .datasets button{display:grid;gap:0;text-align:left;padding:6px 16px 8px;border:0;border-bottom:3px solid transparent;background:none;color:var(--color-ink-muted);font:inherit;cursor:pointer;white-space:nowrap}
  .datasets button strong{font-size:1.05rem;font-weight:650}
  .datasets button span{font-size:var(--font-label)}
  .datasets button[aria-selected="true"]{color:var(--color-ink);border-bottom-color:var(--color-action)}
  .datasets button:hover{color:var(--color-ink)}
  .status{display:flex;align-items:center;gap:12px;padding-bottom:8px;font-size:var(--font-label);color:var(--color-ink-muted);white-space:nowrap}
  .live-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--color-series-1);margin-right:6px}
  .quiet{min-height:0;padding:6px 12px;font-size:var(--font-label)}
  .toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px 24px;flex-wrap:wrap;min-height:40px}
  .transport{display:flex;align-items:center;gap:10px;flex:1;min-width:320px;max-width:760px}
  .transport select{padding:6px 8px;font-size:var(--font-label)}
  .transport input{flex:1;min-width:120px;accent-color:var(--color-action)}
  .transport output{font-size:var(--font-label);font-variant-numeric:tabular-nums;white-space:nowrap}
  .play{display:inline-flex;align-items:center;gap:8px;min-height:0;padding:7px 14px;font-size:var(--font-small)}.play span{font-size:.75em}
  .play.on{color:var(--color-action);border-color:var(--color-action)}
  .signals{display:flex;gap:2px;padding:2px;border:1px solid var(--color-border);border-radius:8px;background:var(--color-surface)}
  .signals button{border:0;background:none;padding:5px 12px;border-radius:6px;font:inherit;font-size:var(--font-label);color:var(--color-ink-muted);cursor:pointer}
  .signals button[aria-checked="true"]{background:var(--color-surface-selected);color:var(--color-ink);font-weight:650}
  .legend{display:flex;align-items:center;gap:6px 16px;flex-wrap:wrap;margin:0;padding:0;list-style:none;font-size:var(--font-label);color:var(--color-ink-muted)}
  .legend li{display:flex;align-items:center;gap:6px}
  .swatch{display:inline-block;width:16px;height:3px;border-radius:2px}
  .dash{display:inline-block;width:18px;border-top:1.5px dashed var(--color-reference-line)}
  .band{display:inline-block;width:14px;height:12px;background:var(--color-change-fill);border-left:1.5px solid var(--color-change-line)}
  .legend .summary{color:var(--color-ink);font-weight:600;margin-left:8px}
  .axis-row{display:grid;grid-template-columns:220px minmax(0,1fr) 250px;gap:20px}
  .axis-row{padding:0 20px;position:sticky;top:0;z-index:1;background:var(--color-canvas)}
  .axis-row :global(.x-axis){padding-left:52px}
  /* 세로 눈금 칸 폭을 고정해 줄마다 그래프 시작이 같고 위의 공유 가로축과 맞는다. */
  .chart :global(.plotted){grid-template-columns:44px minmax(0,1fr)}
  .rows{display:grid;gap:8px;margin:0;padding:0;list-style:none}
  .row{display:grid;grid-template-columns:220px minmax(0,1fr) 250px;gap:20px;height:var(--row);padding:10px 20px;background:var(--color-surface);border:1px solid var(--color-border);border-radius:8px;box-sizing:border-box}
  .who{display:flex;flex-direction:column;gap:4px;min-width:0}
  .name{font-weight:650}
  .detail{font-size:var(--font-label);color:var(--color-ink-muted)}
  .chart.pending{display:flex;align-items:center;justify-content:center;gap:12px;align-self:center;font-size:var(--font-label);color:var(--color-ink-muted);border:1px dashed var(--color-border);border-radius:6px}
  .none{color:var(--color-ink-muted)}
</style>
