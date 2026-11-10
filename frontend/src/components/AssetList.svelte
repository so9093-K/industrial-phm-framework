<script lang="ts">
  import {assetOptionLabel, flowLabel, type Asset} from "../monitor";
  import {attentionText, notePriority, type AttentionState, type Note} from "../monitor-attention";
  import {bandName, changeValue, percent} from "../record-findings";
  import {equipmentKind, readOverview, sparkline, type OverviewRow} from "../asset-overview";
  import {measurementLabel} from "../time-axis";
  import {onDestroy, onMount, untrack} from "svelte";
  import {readPublicDatasets, unfinishedImports, type UnfinishedImport} from "../public-datasets";
  import {systemUrl} from "../routes";
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
  // Rows by kind of equipment when the list holds more than one kind, in the chosen order.
  const grouped = $derived.by(() => {
    if (kinds.length < 2 || kind) return [{kind: "", rows: ordered}];
    const by = new Map<string, Asset[]>();
    for (const asset of ordered) by.set(equipmentKind(name(asset)), [...(by.get(equipmentKind(name(asset))) ?? []), asset]);
    return [...by].map(([label, rows]) => ({kind: label, rows}));
  });

  // Each row fills in when its overview arrives; the summary's own computation is behind it.
  // Rows are read once per asset, two at a time, and only when the set of assets changes, so
  // the monitor's polling of the asset list does not restart them.
  let rows: Record<string, OverviewRow | "loading" | "failed"> = $state({});
  const request = new AbortController();
  const ids = $derived(assets.map(asset => asset.assetId).join("\n"));
  $effect(() => {
    const wanted = ids.split("\n").filter(Boolean);
    untrack(() => {
      const missing = wanted.filter(id => rows[id] === undefined);
      for (const id of missing) rows[id] = "loading";
      let next = 0;
      const work = async () => {
        while (next < missing.length && !request.signal.aborted) {
          const id = missing[next++];
          // A row whose summary is still being computed elsewhere is read once more.
          for (const attempt of [0, 1]) {
            try { rows[id] = await readOverview(id, request.signal); break; }
            catch {
              if (request.signal.aborted) return;
              if (attempt) rows[id] = "failed";
              else await new Promise(done => setTimeout(done, 2000));
            }
          }
        }
      };
      void Promise.all([work(), work()]);
    });
  });
  onDestroy(() => request.abort());
  // An asset still being imported, or left with part of its record, says so on its row; the list
  // is read again while an import runs so its count moves.
  let imports: Map<string, UnfinishedImport> = $state(new Map());
  onMount(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const read = async () => {
      try { imports = unfinishedImports(await readPublicDatasets(request.signal)); } catch { return; }
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
    if (found.start && found.end) {
      const day = (iso: string) => new Date(iso).toLocaleString("ko-KR", {timeZone: "Asia/Seoul", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false});
      return day(found.start) + " ~ " + day(found.end);
    }
    return found.from !== null && found.to !== null ? measurementLabel(found.from, row.main?.periodSeconds) + "부터" : "";
  }
</script>

<section class="ui-panel" aria-labelledby="asset-list-title">
  <div class="head">
    <h2 id="asset-list-title">설비 <span>{assets.length}개</span></h2>
    <div class="filters">
      {#if kinds.length > 1}<label>종류 <select bind:value={kind}><option value="">전체</option>{#each kinds as item (item)}<option value={item}>{item}</option>{/each}</select></label>{/if}
      <label>정렬 <select bind:value={order}><option value="attention">확인 항목이 중요한 순</option><option value="name">이름순</option></select></label>
    </div>
  </div>
  <p class="context">주요 변화는 각 설비 상태 요약의 첫 번째 변화입니다. 두 화면은 같은 계산을 씁니다.</p>
  <div class="table" role="table" aria-label="설비 비교">
    <div class="columns" role="row">
      <span role="columnheader">설비</span><span role="columnheader">운전</span><span role="columnheader">주 신호</span>
      <span role="columnheader">주요 변화</span><span role="columnheader">확인 항목</span>
    </div>
    {#each grouped as group (group.kind)}
      {#if group.kind}<div class="kind" role="row"><span role="cell">{group.kind} · {group.rows.length}대</span></div>{/if}
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
          <div class="cell" role="cell" data-label="운전">
            {#if row?.operation?.shares}
              {@const operation = row.operation}
              {@const shares = row.operation.shares}
              {@const palette = colors(operation.names.levels.length)}
              <span class="bar" title={shares.map((share, band) => bandName(operation.names, band) + " " + percent(share)).join(" · ")}>
                {#each shares as share, band (band)}{#if share > 0}<i style={"width:" + share * 100 + "%;background:" + palette[band]}></i>{/if}{/each}
              </span>
              <small>{shares[0] >= 0.005 ? "정지 " + percent(shares[0]) : "정지 없음"} · 운전 수준 {operation.names.levels.length}개</small>
            {:else if row}<small>{row.kind === "vibration" ? "진동 측정" : "전류 기록 없음"}</small>
            {:else}<small>{waiting}</small>{/if}
          </div>
          <div class="cell" role="cell" data-label="주 신호">
            {#if row?.main}
              <small>{row.main.label}</small>
              <span class="latest">{row.main.latest ? changeValue(row.main.latest.value, row.main.unit) : "값 없음"}</span>
              {#if row.main.trace.length > 1}<svg viewBox="0 0 120 28" preserveAspectRatio="none" aria-hidden="true"><path d={sparkline(row.main.trace, 120, 28)} /></svg>{/if}
            {:else if !row}<small>{waiting}</small>{/if}
          </div>
          <div class="cell" role="cell" data-label="주요 변화">
            {#if row?.finding}
              {@const found = row.finding}
              <a class="finding" href={href(asset.assetId)}>{found.label}{found.band != null && row.operation ? " · " + bandName(row.operation.names, found.band) + " 중" : ""}
                {found.reference !== null && found.typical !== null ? changeValue(found.reference, null) + " → " + changeValue(found.typical, found.unit)
                  : (found.direction === "up" ? "상승" : "하락")}</a>
              <small>{when(row)}{row.findingCount > 1 ? " · 외 " + (row.findingCount - 1) + "건" : ""}</small>
            {:else if row}<small>{row.judged ? "처음 30%와 견줘 크게 달라진 구간 없음" : "판단할 신호 없음"}</small>
            {:else}<small>{waiting}</small>{/if}
            {#if row?.copied}<small class="issue">데이터 확인 필요 · 신호 {row.copied}개</small>{/if}
          </div>
          <div class="cell" role="cell" data-label="확인 항목">
            <small>확인할 항목 {attentionText(count(asset), notesState)}</small>
            {#if note}<strong class="primary-reason">{note.label}</strong><small class="reason-detail" title={note.detail}>{note.detail}</small>
              <a class="investigate" href={note.href}>{note.action} →</a>{/if}
            {#if reasons && (notes[asset.assetId]??0)>0}<a class="reason-link" href={"#attention-"+encodeURIComponent(asset.assetId)} onclick={()=>showReasons(asset.assetId)}>확인 항목 모두 보기 →</a>{/if}
          </div>
        </div>
      {/each}
    {/each}
  </div>
</section>

<style>
  .head{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:var(--space-2) var(--space-4)}
  h2{margin:0}h2 span{font-weight:400;color:var(--color-ink-muted);font-size:var(--font-small)}
  .filters{display:flex;flex-wrap:wrap;gap:var(--space-3);font-size:var(--font-small)}
  .filters label{display:flex;align-items:center;gap:var(--space-1)}
  .context{color:var(--color-ink-muted);font-size:var(--font-small)}
  .table{display:grid;border-top:1px solid var(--color-border)}
  .row,.columns{display:grid;grid-template-columns:minmax(10rem,1.3fr) minmax(8rem,.9fr) minmax(9rem,1fr) minmax(12rem,1.6fr) minmax(9rem,1fr);gap:var(--space-3);padding:var(--space-3) 0;border-bottom:1px solid var(--color-border);align-items:start;min-width:0}
  .columns{font-size:var(--font-small);color:var(--color-ink-muted);padding-block:var(--space-2)}
  .kind{padding:var(--space-2);font-weight:650;font-size:var(--font-small);border-bottom:1px solid var(--color-border);background:var(--color-surface-selected)}
  .cell{display:grid;gap:2px;min-width:0;overflow-wrap:anywhere}
  .cell small{color:var(--color-ink-muted);font-size:var(--font-small)}
  .asset a{font-weight:650;color:var(--color-ink)}
  .latest{font-weight:700;font-variant-numeric:tabular-nums}
  .finding{font-weight:650}
  .primary-reason{font-weight:650}
  .reason-detail{display:-webkit-box;-webkit-line-clamp:2;line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
  .cell small.issue{color:var(--color-caution-ink)}
  .bar{display:flex;height:10px;border-radius:2px;overflow:hidden;background:var(--color-surface-selected);max-width:10rem}
  .bar i{display:block;height:100%}
  svg{display:block;width:100%;max-width:10rem;height:28px}
  svg path{fill:none;stroke:var(--color-action);stroke-width:1.5;vector-effect:non-scaling-stroke}
  @media(max-width:760px){
    .row{grid-template-columns:1fr;gap:var(--space-2)}
    .columns{display:none}
    .cell[data-label]::before{content:attr(data-label);font-size:var(--font-small);color:var(--color-ink-muted);font-weight:650}
  }
</style>
