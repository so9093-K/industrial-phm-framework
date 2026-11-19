<script lang="ts">
  import {assetOptionLabel, flowLabel, type Asset} from "../monitor";
  import {modelFact, noteFact, notePriority, UNCHECKED, type AssetChecks, type Note} from "../monitor-attention";
  import {bandName, changeValue, findingSpan, findingStart} from "../record-findings";
  import {equipmentKind, readOverview, type OverviewRow} from "../asset-overview";
  import {onDestroy, onMount, untrack} from "svelte";
  import {readPublicDatasets, unfinishedImports, type UnfinishedImport} from "../public-datasets";
  import {assetTabUrl, routeUrl, systemUrl} from "../routes";
  import {readChangeReviews, type ChangeCapture} from "../change-reviews";
  import {vibrationShape} from "../vibration-findings";
  import {DECISION_LABEL, latestDecision} from "../review-writes";
  import {afterChange, changeConclusion, changeEnded, latestNumber, type ChangeNumber} from "../change-story";
  import {historyRelated, vibrationRelated} from "../change-evidence";
  import ChangeInterval from "./ChangeInterval.svelte";
  import OverviewTrace from "./OverviewTrace.svelte";
  import ChangeNumbers from "./ChangeNumbers.svelte";

  /** 먼저 열어 볼 설비를 고르는 표. 한 행은 한 설비의 주요 변화·추이·모델 결과·검토 상태이고,
   * 행을 누르면 그 설비의 상태 요약(같은 변화)으로 간다. */
  type Props = {
    assets: Asset[];
    observed: (at: string | null) => string;
    href: (assetId: string) => string;
    /** 설비별 확인 항목과 적용 모델. 관측 현황은 계속 다시 읽고, 설비·신호 목록은 한 번 읽는다. */
    checks?: AssetChecks;
    /** 운영 확인 항목을 같은 화면 아래에서 펼칠 수 있으면 true. */
    operationsHere?: boolean;
  };
  let {assets, observed, href, checks = UNCHECKED, operationsHere = false}: Props = $props();
  const count = (asset: Asset): number | null =>
    asset.attentionCount === null && checks.notes[asset.assetId] === undefined ? null
      : (asset.attentionCount ?? 0) + (checks.notes[asset.assetId]?.length ?? 0);
  type Order = "attention" | "name";
  let order: Order = $state("attention");
  let kind = $state("");
  let groupByKind = $state(false);
  const name = (asset: Asset) => assetOptionLabel(assets, asset.assetId);
  const kinds = $derived([...new Set(assets.map(asset => equipmentKind(name(asset))))].sort());
  // 가장 중요한 확인 항목, 그다음 건수, 그다음 서버가 준 순서.
  const ordered = $derived(assets
    .map((asset, index) => ({asset, index}))
    .filter(({asset}) => !kind || equipmentKind(name(asset)) === kind)
    .sort((a, b) => order === "name" ? name(a.asset).localeCompare(name(b.asset), "ko")
      : notePriority(checks.notes[a.asset.assetId]?.[0]) - notePriority(checks.notes[b.asset.assetId]?.[0])
        || (count(b.asset) ?? 0) - (count(a.asset) ?? 0) || a.index - b.index)
    .map(({asset}) => asset));
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

  // 행의 변화에 남긴 검토. 변화(검토 키)가 바뀔 때만 다시 읽는다.
  let reviews: Record<string, {key: string; text: string | null}> = $state({});
  const reviewReads = new Map<string, AbortController>();
  const reviewKey = (row: OverviewRow): string | null => row.historyInterval?.reviewKey ?? row.vibrationInterval?.change.reviewKey ?? null;
  const day = (iso: string) => new Date(iso).toLocaleDateString("ko-KR", {timeZone: "Asia/Seoul", month: "long", day: "numeric"});
  function reviewText(capture: ChangeCapture | null): string {
    const events = capture?.review.events ?? [];
    if (!capture || !events.length) return "기록 없음";
    const decision = latestDecision(events);
    return (capture.review.status === "closed" ? "종료 · " : "") + (decision ? DECISION_LABEL[decision] : "메모 " + events.length + "건")
      + " · " + day(events.at(-1)!.recordedAt);
  }
  async function loadReview(id: string, key: string) {
    reviewReads.get(id)?.abort();
    const pending = new AbortController();
    reviewReads.set(id, pending);
    reviews[id] = {key, text: null};
    try {
      const page = await readChangeReviews(id, pending.signal, {finding_id: key});
      if (!pending.signal.aborted) reviews[id] = {key, text: reviewText(page.captures[0] ?? null)};
    } catch {
      if (!pending.signal.aborted) reviews[id] = {key, text: "기록을 읽지 못함"};
    }
  }
  $effect(() => {
    const keys = Object.entries(rows).flatMap(([id, read]) => {
      const key = typeof read === "object" ? reviewKey(read) : null;
      return key ? [[id, key] as const] : [];
    });
    untrack(() => { for (const [id, key] of keys) if (reviews[id]?.key !== key) void loadReview(id, key); });
  });
  onDestroy(() => {
    request.abort();
    for (const pending of inFlight.values()) pending.abort();
    for (const pending of reviewReads.values()) pending.abort();
  });

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

  const operationsHref = routeUrl({page: "monitor", assetId: "", tab: "summary", method: null, data: null}) + "#operations";
  function openOperations() {
    const panel = document.getElementById("operations");
    if (panel instanceof HTMLDetailsElement) panel.open = true;
  }
  function modelText(id: string): string | null {
    if (checks.state === "failed") return "상태를 읽지 못함";
    const list = checks.models[id] ?? [];
    if (!list.length) return checks.state === "loading" ? "확인 중" : checks.state === "ready" ? "적용 모델 없음" : null;
    return modelFact(list);
  }
  /** 모델 결과 밖의 확인 항목. 표에 보이는 변화와 같은 신호의 '기록 끝' 항목은 그 변화가 이미 말한다. */
  function problems(id: string, row: OverviewRow | null): {text: string; note: Note}[] {
    const shown = row?.historyInterval;
    return (checks.notes[id] ?? []).flatMap(note => {
      if (note.kind === "departure" && shown && note.departure?.channel === shown.channel
        && (!note.departure.context || note.departure.context.key === shown.context?.key)) return [];
      const text = noteFact(note);
      return text ? [{text, note}] : [];
    });
  }
  // 상태 요약과 같은 규칙: 변화가 기록 끝까지 이어졌으면 마지막 값을 세 번째 숫자로 둔다.
  function historyLatest(row: OverviewRow): ChangeNumber | null {
    const item = row.historyInterval!, last = row.finding?.latest;
    return last ? latestNumber("마지막 구간 평균", last.value, item.typical, item.unit) : null;
  }
  function vibrationLatest(row: OverviewRow): ChangeNumber | null {
    const change = row.vibrationInterval!.change, last = change.trace.at(-1);
    return last && change.to === row.finding?.latest?.position && last.at === change.to
      ? latestNumber("마지막 측정", last.value, change.typical, change.unit) : null;
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
      <label>정렬 <select bind:value={order}><option value="attention">확인 항목 우선</option><option value="name">이름순</option></select></label>
    </div></details>{/if}
    </div>
  </div>
  <div class="table" role="table" aria-label="설비별 주요 변화">
    <div class="columns" role="row">
      <span role="columnheader">설비</span><span role="columnheader">주요 변화</span>
      <span role="columnheader">추이</span><span role="columnheader">모델·검토</span>
    </div>
    {#each grouped as group (group.kind)}
      {#if group.kind}<div class="kind" role="row"><span role="cell" aria-colspan="4">{group.kind} · {group.rows.length}대</span></div>{/if}
      {#each group.rows as asset (asset.assetId)}
        {@const read = rows[asset.assetId]}
        {@const row = typeof read === "object" ? read : null}
        {@const review = reviews[asset.assetId]}
        {@const model = modelText(asset.assetId)}
        <div class="row" role="row">
          <div class="cell asset" role="cell">
            <a class="open" href={href(asset.assetId)}>{name(asset)}</a>
            <small>{asset.flow === "stored-history" ? "과거 저장 기록" : flowLabel(asset.flow)} · {asset.lastObservedAt ? "마지막 측정 " + observed(asset.lastObservedAt)
              : asset.lastPosition != null ? "마지막 " + asset.lastPosition + "번째 측정" : "측정 시각 정보 없음"}</small>
            {#if imports.get(asset.assetId)}
              {@const unfinished = imports.get(asset.assetId)!}
              <small class="issue import">{unfinished.text} <a class="above" href={systemUrl("connections")}>{unfinished.running ? "진행 상황 보기" : "다시 가져오기"} →</a></small>
            {/if}
          </div>
          <div class="cell" role="cell" data-label="주요 변화">
            {#if row?.historyInterval}
              {@const item = row.historyInterval}
              {@const condition = item.band != null && row.operation && item.operation?.key === row.operation.key ? bandName(row.operation.names, item.band) : null}
              {@const ended = changeEnded(item.end, item.context?.record.to, item.bucketSeconds)}
              {@const related = historyRelated(item.related)}
              <p class="headline">{changeConclusion(item, {span: ended ? findingSpan(item) : findingStart(item) + "부터 기록 끝까지", condition})}</p>
              <ChangeNumbers facts={item} latest={ended ? null : historyLatest(row)} fallback="비교 가능한 값 없음" compact/>
              {#if ended}<small>{afterChange(item.end, item.usual, item.overview ?? [], item.overviewKind ?? "all", condition) ?? ended}</small>{/if}
              {#if related}<small>함께 변한 신호 · {related}</small>{/if}
            {:else if row?.vibrationInterval}
              {@const change = row.vibrationInterval.change}
              {@const shape = vibrationShape(change, row.finding?.latest?.position ?? null)}
              {@const latest = vibrationLatest(row)}
              {@const related = vibrationRelated(change.related)}
              <p class="headline">{changeConclusion(change, {span: shape.span, jump: shape.jump})}</p>
              <ChangeNumbers facts={change} {latest} fallback="비교 가능한 값 없음" compact/>
              {#if related}<small>함께 변한 특징 · {related}</small>{/if}
            {:else if row}
              <p class="headline quiet">{row.judged ? "기록 처음 30% 대비 크게 달라진 구간 없음" : "판단할 신호 없음"}</p>
              {#if row.main?.latest}<small>마지막 저장값 · {row.main.label} <strong class="latest">{changeValue(row.main.latest.value, row.main.unit)}</strong></small>{/if}
            {:else}
              <small role="status">{read === "failed" ? "변화를 불러오지 못함" : "변화 확인 중"}</small>
              <span class="pending-actions"><a class="above" href={assetTabUrl(asset.assetId, "signals")}>신호 기록 보기 →</a>
                {#if read === "failed"}<button type="button" class="retry above" onclick={() => loadRow(asset.assetId)}>다시 확인</button>{/if}</span>
            {/if}
          </div>
          <div class="cell trace-cell" role="cell" data-label="추이">
            {#if row?.historyInterval?.trace?.length}
              <ChangeInterval finding={row.historyInterval} height={110} focus/>
            {:else if row?.vibrationInterval}
              {@const changed = row.vibrationInterval}
              <OverviewTrace main={{label: changed.change.label, unit: changed.change.unit, axis: "acquisition", periodSeconds: changed.periodSeconds, latest: null,
                trace: changed.change.trace.map(point => ({x: point.at, value: point.value, join: point.join}))}} range={changed.change} usual={changed.change.usual}
                marks={vibrationShape(changed.change, row.finding?.latest?.position ?? null).marks} height={110}/>
            {:else if row?.main}
              <OverviewTrace main={row.main} height={110}/>
            {/if}
          </div>
          <div class="cell" role="cell" data-label="모델·검토">
            <ul class="facts">
              {#if model}<li>모델 · {model}</li>{/if}
              {#if review}<li>검토 · {review.text ?? "확인 중"}</li>{/if}
              {#each problems(asset.assetId, row) as problem (problem.note.id)}
                <li class="issue">{problem.text}{#if problem.note.kind !== "departure"} <a class="above" href={problem.note.href}>{problem.note.action} →</a>{/if}</li>
              {/each}
              {#if asset.attentionCount}
                <li class="issue">운영 · 확인 항목 {asset.attentionCount}건 <a class="above" href={operationsHref} onclick={operationsHere ? openOperations : undefined}>보기 →</a></li>
              {/if}
            </ul>
          </div>
        </div>
      {/each}
    {/each}
  </div>
</section>

<style>
  .bearing-start{display:grid;gap:var(--space-1)}.bearing-start small{font-size:var(--font-label);color:var(--color-ink-muted)}
  .view-options>summary{cursor:pointer;font-size:var(--font-small);color:var(--color-action);font-weight:650;padding-block:var(--space-2)}.view-options:not(.compact)>summary{display:none}.view-options.compact[open] .filters{padding-top:var(--space-2)}
  .head-tools{display:flex;align-items:center;justify-content:end;gap:var(--space-3) var(--space-5);flex-wrap:wrap}.bearing-entry{font-size:var(--font-small);font-weight:650}
  .trace-cell :global(figure){margin:0}.trace-cell :global(figcaption){font-size:var(--font-label)}
  .head{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:var(--space-2) var(--space-4);margin-bottom:var(--space-3)}
  h2{margin:0}h2 span{font-weight:400;color:var(--color-ink-muted);font-size:var(--font-small)}
  .filters{display:flex;flex-wrap:wrap;gap:var(--space-3);font-size:var(--font-small)}
  .filters label{display:flex;align-items:center;gap:var(--space-1)}
  .table{display:grid;border-top:1px solid var(--color-border)}
  .row,.columns{display:grid;grid-template-columns:minmax(0,.8fr) minmax(0,1.6fr) minmax(0,1.25fr) minmax(0,.95fr);gap:var(--space-4);padding:var(--space-4) var(--space-2);border-bottom:1px solid var(--color-border);align-items:start;min-width:0}
  .columns{font-size:var(--font-small);color:var(--color-ink-muted);padding-block:var(--space-2)}
  /* 행 전체가 설비 이름의 링크다. 행 안의 다른 링크·버튼만 그 위에 둔다. */
  .row{position:relative}
  .row:hover{background:var(--color-surface-selected)}
  .row:has(.open:focus-visible){outline:2px solid var(--color-action);outline-offset:-2px}
  .open{font-weight:700;color:var(--color-ink);text-decoration:none}
  .open::after{content:"";position:absolute;inset:0}
  .open:focus-visible{outline:none}
  .above{position:relative;z-index:1}
  .kind{padding:var(--space-2);font-weight:650;font-size:var(--font-small);border-bottom:1px solid var(--color-border);background:var(--color-surface-selected)}
  .cell{display:grid;gap:2px;min-width:0;overflow-wrap:anywhere;word-break:keep-all;align-content:start}
  .cell small{color:var(--color-ink-muted);font-size:var(--font-small)}
  .headline{margin:0;font-weight:650}
  .headline.quiet{font-weight:400}
  .latest{font-weight:700;color:var(--color-ink);font-variant-numeric:tabular-nums}
  .facts{list-style:none;margin:0;padding:0;display:grid;gap:var(--space-2);font-size:var(--font-small)}
  .facts .issue{color:var(--color-caution-ink)}
  .pending-actions{display:flex;flex-wrap:wrap;align-items:center;gap:var(--space-2) var(--space-4);margin-top:var(--space-2);font-size:var(--font-small)}
  .group-toggle input{width:auto;margin:0}
  .retry{padding:var(--space-1) var(--space-2);border:1px solid var(--color-border);border-radius:var(--radius-control);background:var(--color-surface);color:var(--color-action);cursor:pointer}
  .issue.import{font-size:var(--font-small);color:var(--color-caution-ink)}
  .cell small.issue{color:var(--color-caution-ink)}
  @media(max-width:760px){
    .row{grid-template-columns:1fr;gap:var(--space-2)}
    .columns{display:none}
    .cell[data-label]::before{content:attr(data-label);font-size:var(--font-small);color:var(--color-ink-muted);font-weight:650}
  }
</style>
