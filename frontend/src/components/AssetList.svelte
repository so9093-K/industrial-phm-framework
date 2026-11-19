<script lang="ts">
  import {assetOptionLabel, flowLabel, type Asset} from "../monitor";
  import {attentionText, notePriority, type AttentionState, type Note} from "../monitor-attention";
  import {vibrationLinks} from "../vibration-findings";
  import {bandName, changeValue, percent, findingLinks, findingSpan} from "../record-findings";
  import {equipmentKind, latestReading, readOverview, sparklinePoints, tracePath, type OverviewRow} from "../asset-overview";
  import {measurementLabel} from "../time-axis";
  import {onDestroy, onMount, untrack} from "svelte";
  import {readPublicDatasets, unfinishedImports, type UnfinishedImport} from "../public-datasets";
  import {assetTabUrl, systemUrl} from "../routes";
  import ChangeInterval from "./ChangeInterval.svelte";
  import OverviewTrace from "./OverviewTrace.svelte";
  import ChangeNumbers from "./ChangeNumbers.svelte";
  import {changeHeadline} from "../change-story";
  import AssetFocus from "./AssetFocus.svelte";
  import LatestMeasurement from "./LatestMeasurement.svelte";
  type Props = {
    assets: Asset[];
    observed: (at: string | null) => string;
    href: (assetId: string) => string;
    /** Model, receipt and baseline notes per asset, added to the monitor's own count. */
    notes?: Record<string, number>;
    /** On 관측 현황 the reasons are in the operating details on the same page. */
    reasons?: boolean;
    primaryNotes?:Record<string,Note>;
    notesState?: AttentionState;
  };
  let {assets, observed, href, notes = {}, reasons = false, primaryNotes={}, notesState = "ready"}: Props = $props();
  const count = (asset: Asset): number | null =>
    asset.attentionCount === null && notes[asset.assetId] === undefined ? null : (asset.attentionCount ?? 0) + (notes[asset.assetId] ?? 0);
  type Order = "attention" | "name";
  let order: Order = $state("attention");
  let kind = $state("");
  let groupByKind = $state(false);
  const name = (asset: Asset) => assetOptionLabel(assets, asset.assetId);
  const kinds = $derived([...new Set(assets.map(asset => equipmentKind(name(asset))))].sort());
  // Use the most important known reason, then the count and stable server order.
  const ordered = $derived(assets
    .map((asset, index) => ({asset, index}))
    .filter(({asset}) => !kind || equipmentKind(name(asset)) === kind)
    .sort((a, b) => order === "name" ? name(a.asset).localeCompare(name(b.asset), "ko")
      : notePriority(primaryNotes[a.asset.assetId]) - notePriority(primaryNotes[b.asset.assetId])
        || (count(b.asset) ?? 0) - (count(a.asset) ?? 0) || a.index - b.index)
    .map(({asset}) => asset));
  // Grouping is an explicit view; the default keeps the chosen order across every kind.
  const grouped = $derived.by(() => {
    if (!groupByKind || kinds.length < 2 || kind) return [{kind: "", rows: ordered}];
    const by = new Map<string, Asset[]>();
    for (const asset of ordered) by.set(equipmentKind(name(asset)), [...(by.get(equipmentKind(name(asset))) ?? []), asset]);
    return [...by].map(([label, rows]) => ({kind: label, rows}));
  });

  // Keep two requests in flight across every monitor update. Only changed assets are
  // queued; superseded requests cannot publish their older overview into a newer row.
  let rows: Record<string, OverviewRow | "loading" | "failed"> = $state({});
  const request = new AbortController();
  const wanted = new Map<string, string>();
  const queue = new Set<string>();
  const inFlight = new Map<string, AbortController>();
  let active = 0;
  function drain() {
    while (active < 2 && queue.size && !request.signal.aborted) {
      // A running calculation finishes before this asset's newest revision is read.
      // Coalesce intermediate receipts, so aborting HTTP cannot pile up server work.
      const id = [...queue].find(candidate => !inFlight.has(candidate));
      if (id === undefined) break;
      queue.delete(id);
      const revision = wanted.get(id);
      if (revision === undefined) continue;
      const pending = new AbortController();
      inFlight.set(id, pending);
      active++;
      void (async () => {
        try {
          for (const attempt of [0, 1]) {
            try {
              const value = await readOverview(id, pending.signal);
              if (!pending.signal.aborted && wanted.get(id) === revision) rows[id] = value;
              break;
            } catch {
              if (pending.signal.aborted || wanted.get(id) !== revision) return;
              if (attempt) {
                if (wanted.get(id) === revision) rows[id] = "failed";
              } else await new Promise(done => setTimeout(done, 2000));
            }
          }
        } finally {
          if (inFlight.get(id) === pending) inFlight.delete(id);
          active--;
          drain();
        }
      })();
    }
  }
  function loadRow(id: string) {
    if (!wanted.has(id) || inFlight.has(id)) return;
    rows[id] = "loading";
    queue.add(id);
    drain();
  }
  const revisions = $derived(JSON.stringify(assets.map(asset => [asset.assetId,
    asset.overviewRevision ?? JSON.stringify([asset.lastObservedAt, asset.lastReceivedAt, asset.lastPosition])])));
  $effect(() => {
    const current = new Map<string, string>(JSON.parse(revisions));
    untrack(() => {
      for (const id of wanted.keys()) if (!current.has(id)) {
        wanted.delete(id); queue.delete(id); inFlight.get(id)?.abort(); delete rows[id];
      }
      for (const [id, revision] of current) if (wanted.get(id) !== revision) {
        wanted.set(id, revision);
        rows[id] = "loading";
        queue.add(id);
      }
      drain();
    });
  });
  onDestroy(() => {request.abort(); for (const pending of inFlight.values()) pending.abort();});
  // An asset still being imported, or left with part of its record, says so on its row; the list
  // is read again while an import runs so its count moves.
  let publicBearings:string[]=$state([]);
  let canImport=$state(false);
  const offerBearing=$derived(publicBearings.length>0&&!assets.some(asset=>publicBearings.includes(asset.assetId)));
  const bearingHref=systemUrl("connections")+"&dataset_kind=xjtu-sy#public-datasets";
  let imports: Map<string, UnfinishedImport> = $state(new Map());
  onMount(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const read = async () => {
      try {
        const datasets=await readPublicDatasets(request.signal);
        imports=unfinishedImports(datasets);
        canImport=datasets.canImport;
        publicBearings=datasets.items.filter(item=>item.kind==="xjtu-sy").map(item=>item.assetId);
      } catch { return; }
      if ([...imports.values()].some((note) => note.running)) timer = setTimeout(() => void read(), 15000);
    };
    void read();
    return () => clearTimeout(timer);
  });
  function showReasons(assetId:string) {
    const heading=document.getElementById("attention-"+assetId);
    const detail=heading?.closest("details");
    if(detail)detail.open=true;
  }
  // Stopped in grey, running levels in one hue from light (low current) to dark (high).
  const COLORS = ["#c3ccd2", "#b3dbe5", "#7cbccd", "#4a9bb3", "#1f7690", "#0b5068"];
  function colors(levels: number): string[] {
    return [COLORS[0], ...Array.from({length: levels}, (_, index) => COLORS[1 + (levels === 1 ? 2 : Math.round(index * 4 / (levels - 1)))])];
  }
  function when(row: OverviewRow): string {
    const found = row.finding!;
    // 설비 요약의 문장과 같은 표현으로 언제부터 얼마 동안인지 말한다.
    if (row.historyInterval) return findingSpan(row.historyInterval).replace(/ 동안$/, "");
    if (found.start && found.end) {
      const day = (iso: string) => new Date(iso).toLocaleString("ko-KR", {timeZone: "Asia/Seoul", year: "numeric", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false});
      return day(found.start) + " ~ " + day(found.end);
    }
    return found.from !== null && found.to !== null ? measurementLabel(found.from, row.main?.periodSeconds) + "부터" : "";
  }
</script>

<section class="ui-panel" aria-labelledby="asset-list-title">
  <div class="head">
    <h2 id="asset-list-title">설비 기록 <span>{assets.length}개</span></h2>
    <div class="head-tools">
    {#if offerBearing}<div class="bearing-start"><a class="bearing-entry" href={bearingHref}>{canImport?"공개 베어링 진동 기록 가져오기":"준비된 베어링 진동 기록 보기"} →</a>
      {#if !canImport}<small>보기 전용 · 가져오려면 변경 가능한 작업공간을 여세요.</small>{/if}</div>{/if}
    {#if assets.length > 1}<details class="view-options" class:compact={assets.length<=3} open={assets.length>3}>
      <summary>정렬·필터</summary><div class="filters">
      {#if kinds.length > 1}<label>종류 <select bind:value={kind}><option value="">전체</option>{#each kinds as item (item)}<option value={item}>{item}</option>{/each}</select></label>{/if}
      {#if kinds.length>1}<label class="group-toggle"><input type="checkbox" bind:checked={groupByKind}/>종류별로 묶기</label>{/if}
      <label>정렬 <select bind:value={order}><option value="attention">확인 항목이 중요한 순</option><option value="name">이름순</option></select></label>
    </div></details>{/if}
    </div>
  </div>
  {#if assets.length === 1}
    {@const asset = assets[0]}
    {#if imports.get(asset.assetId)}{@const unfinished = imports.get(asset.assetId)!}<p class="issue import">{unfinished.text} <a href={systemUrl("connections")}>{unfinished.running ? "진행 상황 보기" : "다시 가져오기"} →</a></p>{/if}
    <AssetFocus {asset} name={name(asset)} read={rows[asset.assetId]} {observed} href={href(asset.assetId)} note={primaryNotes[asset.assetId]}
      countText={attentionText(count(asset), notesState)} onRetry={() => void loadRow(asset.assetId)}
      reasonHref={reasons && (notes[asset.assetId]??0)>0 ? "#attention-"+encodeURIComponent(asset.assetId) : null}
      onReasons={() => showReasons(asset.assetId)}/>
  {:else}
  <p class="context">{groupByKind&&!kind?"설비 종류별로 묶고, 각 종류 안에서 정렬합니다.":order === "name"?"설비 이름순입니다. 달라진 것을 누르면 그 구간의 신호로 이동합니다.":"먼저 확인할 것이 있는 설비부터 보여 줍니다. 달라진 것을 누르면 그 구간의 신호로 이동합니다."}</p>
  <div class="table" role="table" aria-label="설비 비교">
    <div class="columns" role="row">
      <span role="columnheader">설비</span><span role="columnheader">기록에서 달라진 것</span>
      <span role="columnheader">신호 추이</span><span role="columnheader">마지막 측정에서 확인할 것</span>
    </div>
    {#each grouped as group (group.kind)}
      {#if group.kind}<div class="kind" role="row"><span role="cell" aria-colspan="4">{group.kind} · {group.rows.length}대</span></div>{/if}
      {#each group.rows as asset (asset.assetId)}
        {@const note = primaryNotes[asset.assetId]}
        {@const stored = asset.flow === "stored-history"}
        {@const read = rows[asset.assetId]}
        {@const row = typeof read === "object" ? read : null}
        {@const waiting = read === "failed" ? "읽지 못함" : "계산 중"}
        <div class="row" role="row">
          <div class="cell asset" role="cell">
            <a href={href(asset.assetId)}>{name(asset)}</a>
            <small>{stored ? "과거 저장 기록" : flowLabel(asset.flow)} · {asset.lastObservedAt ? "마지막 측정 " + observed(asset.lastObservedAt)
              : asset.lastPosition != null ? "마지막 " + asset.lastPosition + "번째 측정" : "측정 시각 정보 없음"}</small>
            {#if imports.get(asset.assetId)}
              {@const unfinished = imports.get(asset.assetId)!}
              <small class="issue import">{unfinished.text} <a href={systemUrl("connections")}>{unfinished.running ? "진행 상황 보기" : "다시 가져오기"} →</a></small>
            {/if}
          </div>
          <div class="cell" role="cell" data-label="기록에서 달라진 것">
            {#if row?.finding}
              {@const found = row.finding}
              {@const inspect = row.historyInterval ? findingLinks(asset.assetId,row.historyInterval,row.historyInterval.baseline,row.historyInterval.bucketSeconds??null).signal : row.vibrationInterval ? vibrationLinks(asset.assetId,row.vibrationInterval.change).signal : null}
              <a class="finding" href={inspect??href(asset.assetId)}>{changeHeadline(row.historyInterval??row.vibrationInterval?.change??{...found,kind:found.kind==="level-change"?"level-change":"departure"})}</a>
              <ChangeNumbers facts={row.historyInterval??row.vibrationInterval?.change??{...found,kind:found.kind==="level-change"?"level-change":"departure"}} fallback="비교 가능한 값 없음" compact/>
              <small>{found.band != null && row.operation ? bandName(row.operation.names, found.band) + " 중 · " : ""}{when(row)}</small>
              <a class="investigate-change" href={inspect??href(asset.assetId)}>변화 구간 조사하기 →</a>
              {#if row.findingCount > 1}<small>다른 변화 {row.findingCount - 1}건</small>{/if}
            {:else if row}<small>{row.judged ? "처음 30%와 견줘 크게 달라진 구간 없음" : "판단할 신호 없음"}</small>
            {:else}<small role="status">{read === "failed" ? "변화를 불러오지 못함" : "변화 확인 중"}</small>
              <a href={assetTabUrl(asset.assetId,"signals")}>신호 기록 보기 →</a>
              {#if read === "failed"}<button type="button" class="retry" onclick={() => void loadRow(asset.assetId)}>다시 확인</button>{/if}{/if}

          </div>
          <div class="cell trace-cell" role="cell" data-label="신호 추이">
            {#if row?.historyInterval?.trace?.length}
              <ChangeInterval finding={row.historyInterval} height={96} focus/>
            {:else if row?.vibrationInterval}
              {@const changed=row.vibrationInterval}
              <OverviewTrace main={{label:changed.change.label,unit:changed.change.unit,axis:"acquisition",periodSeconds:changed.periodSeconds,latest:null,trace:changed.change.trace.map(point=>({x:point.at,value:point.value,join:point.join}))}} range={changed.change} height={96}/>
            {:else if row?.main}
              <small>{row.main.label}</small>
              <span class="latest">{row.main.latest ? changeValue(row.main.latest.value, row.main.unit) : "값 없음"}</span>
              {#if row.main.trace.length > 1}{@const points = sparklinePoints(row.main.trace,240,36)}<svg viewBox="0 0 240 36" preserveAspectRatio="none" aria-hidden="true"><path d={tracePath(points)} />{#each points as point,i(i)}<circle cx={point.x} cy={point.y} r="1.5" fill="currentColor"/>{/each}</svg>{/if}
            {/if}
            <!-- 켜졌다 꺼지는 설비는 얼마나 멈춰 있었는지가 값만큼 중요하다. -->

          </div>
          <div class="cell" role="cell" data-label="마지막 측정에서 확인할 것">
            {#if row?.finding}<LatestMeasurement main={latestReading(row)}/>{/if}
            <small>확인할 항목 {attentionText(count(asset), notesState)}</small>
            {#if note}<strong class="primary-reason">{note.label}</strong>
              <a class="investigate" href={note.href}>{note.kind==="departure"&&row?.finding?"최근 측정 살펴보기":note.action} →</a>{/if}
            {#if row?.operation || row?.copied || (row?.finding&&row.main) || note || (reasons && (notes[asset.assetId]??0)>0)}<details class="row-details"><summary>운전·확인 상세</summary>
            {#if row?.operation?.shares}
              {@const operation = row.operation}
              {@const shares = row.operation.shares}
              {@const palette = colors(operation.names.levels.length)}
              <span class="bar" title={shares.map((share, band) => bandName(operation.names, band) + " " + percent(share)).join(" · ")}>
                {#each shares as share, band (band)}{#if share > 0}<i style={"width:" + share * 100 + "%;background:" + palette[band]}></i>{/if}{/each}
              </span>
              <small>{shares[0] >= 0.005 ? "정지 " + percent(shares[0]) : "정지 없음"} · 운전 수준 {operation.names.levels.length}개</small>
            {:else if row}<small>{row.kind === "vibration" ? "진동 측정" : "운전 수준을 나눌 정보 없음"}</small>
            {:else}<small>{waiting}</small>{/if}
              {#if row?.operation?.shares}<p class="shares">{row.operation.shares.map((share,band)=>bandName(row.operation!.names,band)+" "+percent(share)).join(" · ")}</p>{/if}
              {#if row?.copied}<p class="reason-detail">신호 {row.copied}개는 변화 비교에서 제외했습니다. <a href={href(asset.assetId)}>해당 기록 확인 →</a></p>{/if}
              {#if note}<p class="reason-detail">{note.detail}</p>{/if}
            {#if reasons && (notes[asset.assetId]??0)>0}<a class="reason-link" href={"#attention-"+encodeURIComponent(asset.assetId)} onclick={()=>showReasons(asset.assetId)}>확인 항목 모두 보기 →</a>{/if}
            </details>{/if}

          </div>
        </div>
      {/each}
    {/each}
  </div>
  {/if}
</section>

<style>
  .bearing-start{display:grid;gap:var(--space-1)}.bearing-start small{font-size:var(--font-label);color:var(--color-ink-muted)}
  .view-options>summary{cursor:pointer;font-size:var(--font-small);color:var(--color-action);font-weight:650;padding-block:var(--space-2)}.view-options:not(.compact)>summary{display:none}.view-options.compact[open] .filters{padding-top:var(--space-2)}
  .head-tools{display:flex;align-items:center;justify-content:end;gap:var(--space-3) var(--space-5);flex-wrap:wrap}.bearing-entry{font-size:var(--font-small);font-weight:650}.trace-cell :global(figure){margin:0}.trace-cell :global(figcaption){font-size:var(--font-label)}
  .head{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:var(--space-2) var(--space-4)}
  h2{margin:0}h2 span{font-weight:400;color:var(--color-ink-muted);font-size:var(--font-small)}
  .filters{display:flex;flex-wrap:wrap;gap:var(--space-3);font-size:var(--font-small)}
  .filters label{display:flex;align-items:center;gap:var(--space-1)}
  .context{color:var(--color-ink-muted);font-size:var(--font-small)}
  .table{display:grid;border-top:1px solid var(--color-border)}
  .row,.columns{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.45fr) minmax(0,1.15fr) minmax(0,.85fr);gap:var(--space-3);padding:var(--space-3) 0;border-bottom:1px solid var(--color-border);align-items:start;min-width:0}
  .columns{font-size:var(--font-small);color:var(--color-ink-muted);padding-block:var(--space-2)}
  .kind{padding:var(--space-2);font-weight:650;font-size:var(--font-small);border-bottom:1px solid var(--color-border);background:var(--color-surface-selected)}
  .cell{display:grid;gap:2px;min-width:0;overflow-wrap:anywhere}
  .cell small{color:var(--color-ink-muted);font-size:var(--font-small)}
  .asset a{font-weight:650;color:var(--color-ink)}
  .latest{font-weight:700;font-variant-numeric:tabular-nums}
  .finding{font-weight:650}
  .investigate-change{font-weight:650;font-size:var(--font-small);margin-top:var(--space-2)}
  .primary-reason{font-weight:650}
  .reason-detail,.shares{margin:var(--space-2) 0 0;font-size:var(--font-small);color:var(--color-ink-muted);overflow-wrap:anywhere}
  .row-details summary{cursor:pointer;padding-block:var(--space-2);font-size:var(--font-small);color:var(--color-action)}
  .group-toggle input{width:auto;margin:0}
  .retry{padding:var(--space-1) var(--space-2);justify-self:start;border:1px solid var(--color-border);border-radius:var(--radius-control);background:var(--color-surface);color:var(--color-action);cursor:pointer}
  .issue.import{font-size:var(--font-small);color:var(--color-caution-ink)}
  .cell small.issue{color:var(--color-caution-ink)}
  .bar{display:flex;height:10px;border-radius:2px;overflow:hidden;background:var(--color-surface-selected);max-width:10rem}
  .bar i{display:block;height:100%}
  svg{display:block;width:100%;max-width:16rem;height:36px}
  svg path{fill:none;stroke:var(--color-action);stroke-width:1.5;vector-effect:non-scaling-stroke}
  @media(max-width:760px){
    .row{grid-template-columns:1fr;gap:var(--space-2)}
    .columns{display:none}
    .cell[data-label]::before{content:attr(data-label);font-size:var(--font-small);color:var(--color-ink-muted);font-weight:650}
  }
</style>
