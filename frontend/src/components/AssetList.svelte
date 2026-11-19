<script lang="ts">
  import {assetOptionLabel, type Asset} from "../monitor";
  import {noteFact, notePriority, UNCHECKED, type AssetChecks, type Note} from "../monitor-attention";
  import {changeValue} from "../record-findings";
  import {readOverview, sparkline, type OverviewRow} from "../asset-overview";
  import {onDestroy, onMount, untrack} from "svelte";
  import {readPublicDatasets, unfinishedImports, type UnfinishedImport} from "../public-datasets";
  import {systemUrl} from "../routes";
  import {readChangeReviews, type ChangeCapture} from "../change-reviews";
  import {vibrationShape} from "../vibration-findings";
  import {DECISION_LABEL, latestDecision} from "../review-writes";
  import {changeEnded, plainLabel, versusStart} from "../change-story";

  /** 모니터링 화면 맨 위의 설비 칸 줄. 칸마다 그 설비의 주요 변화 한 줄, 작은 추이, 모델의 마지막 분석 결과를 두고,
   * 누르면 아래 중심 화면이 그 설비로 바뀐다. 확인할 것이 있는 설비가 앞에 온다. */
  type Props = {
    assets: Asset[];
    observed: (at: string | null) => string;
    href: (assetId: string) => string;
    /** 지금 아래 중심 화면에 열린 설비. */
    selected?: string;
    /** 설비별 확인 항목과 적용 모델 (모니터링 화면이 계속 다시 읽는다). */
    checks?: AssetChecks;
    /** 목록을 읽은 시각. */
    checkedAt?: string;
    compact?: boolean;
  };
  let {assets, href, selected = "", checks = UNCHECKED, checkedAt = "",compact=false}: Props = $props();
  const count = (asset: Asset): number | null =>
    asset.attentionCount === null && checks.notes[asset.assetId] === undefined ? null
      : (asset.attentionCount ?? 0) + (checks.notes[asset.assetId]?.length ?? 0);
  const name = (asset: Asset) => assetOptionLabel(assets, asset.assetId);
  // 가장 중요한 확인 항목, 그다음 건수, 그다음 서버가 준 순서.
  const ordered = $derived(assets
    .map((asset, index) => ({asset, index}))
    .sort((a, b) => notePriority(checks.notes[a.asset.assetId]?.[0]) - notePriority(checks.notes[b.asset.assetId]?.[0])
      || (count(b.asset) ?? 0) - (count(a.asset) ?? 0) || a.index - b.index)
    .map(({asset}) => asset));

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

  /** 모델이 마지막으로 분석한 측정의 결과를 짧게: 몇 개 모델 중 몇 개가 기준을 넘었는지. */
  function modelShort(id: string): {text: string; over: boolean} {
    if (checks.state === "failed") return {text: "모델 상태 미확인", over: false};
    const list = checks.models[id] ?? [];
    if (!list.length) return {text: checks.state === "loading" ? "모델 확인 중" : "적용 모델 없음", over: false};
    const judged = list.filter(model => model.state === "processed" && model.analyzed?.exceeds != null);
    const over = judged.filter(model => model.analyzed!.exceeds).length;
    if (!judged.length) return {text: "모델 분석 대기", over: false};
    // 칸은 '지금' 상태라 마지막 분석 결과다. 지난 변화 구간에서의 반응은 시간축의 모델 줄이 보여 준다.
    return over ? {text: "마지막 분석 · 모델 " + judged.length + "개 중 " + over + "개 기준 초과", over: true} : {text: "마지막 분석 · 모델 기준 이하", over: false};
  }
  /** 모델 결과 밖의 확인 항목. 칸에 보이는 변화와 같은 신호의 '기록 끝' 항목은 그 변화가 이미 말한다. */
  function problems(id: string, row: OverviewRow | null): {text: string; note: Note}[] {
    const shown = row?.historyInterval;
    return (checks.notes[id] ?? []).flatMap(note => {
      if (note.kind === "departure" && shown && note.departure?.channel === shown.channel
        && (!note.departure.context || note.departure.context.key === shown.context?.key)) return [];
      const text = noteFact(note);
      return text ? [{text, note}] : [];
    });
  }
  const monthDay = (iso: string) => new Date(iso).toLocaleDateString("ko-KR", {timeZone: "Asia/Seoul", month: "long", day: "numeric"});
  /** 칸 하나의 주요 변화: 무엇이, 초기와 비교해 얼마나, 언제부터, 지금도 이어지는지. */
  function tile(row: OverviewRow | null, read: OverviewRow | "loading" | "failed" | undefined): {what: string; how: string; when: string; trace: {x: number; value: number; join?: boolean}[]} {
    if (!row) return {what: read === "failed" ? "변화를 불러오지 못함" : "변화 확인 중", how: "", when: "", trace: []};
    if (row.historyInterval) {
      const item = row.historyInterval;
      const ended = changeEnded(item.end, item.context?.record.to, item.bucketSeconds) !== null;
      const last = !ended && row.finding?.latest ? versusStart(row.finding.latest.value, item.reference, item.unit) : null;
      return {what: plainLabel(item.label), how: (versusStart(item.typical ?? item.value, item.reference, item.unit) ?? "") + (last ? " → 마지막 " + last.replace("초기의 ", "") : ""),
        when: monthDay(item.start) + "부터 · " + (ended ? monthDay(item.end) + " 끝남" : "기록 끝까지"),
        // 칸의 작은 추이는 기록 전체: 같은 운전 수준끼리 비교했으면 그 수준의 값, 아니면 구간 평균.
        trace: (item.overview ?? []).flatMap(point => {
          const value = item.overviewKind === "all" || !item.overviewKind ? point.mean : point.judged;
          return value === null ? [] : [{x: Date.parse(point.at), value, join: point.join}];
        })};
    }
    if (row.vibrationInterval) {
      const change = row.vibrationInterval.change;
      const shape = vibrationShape(change, row.finding?.latest?.position ?? null);
      const last = shape.atEnd ? versusStart(change.trace.at(-1)!.value, change.reference, change.unit) : null;
      return {what: plainLabel(change.label, change.feature), how: (versusStart(change.typical ?? change.value, change.reference, change.unit) ?? "")
          + (last ? " → 마지막 " + last.replace("초기의 ", "") : ""),
        when: change.from + "번째 측정부터 · " + (shape.atEnd ? "기록 끝까지" : change.to + "번째까지"),
        trace: change.trace.map(point => ({x: point.at, value: point.value, join: point.join}))};
    }
    return {what: row.judged ? "크게 달라진 구간 없음" : "판단할 신호 없음", how: "",
      when: row.main?.latest ? row.main.label + " " + changeValue(row.main.latest.value, row.main.unit) : "", trace: row.main?.trace ?? []};
  }
</script>

<section class="assets" class:compact aria-labelledby="asset-list-title">
  <div class="head">
    <h2 id="asset-list-title">설비 <span>{assets.length}개{checkedAt ? " · 목록 확인 " + checkedAt : ""}</span></h2>
    {#if offerBearing}<a class="bearing-entry" href={bearingHref}>{canImport?"공개 베어링 진동 기록 가져오기":"준비된 베어링 진동 기록 보기"} →</a>{/if}
  </div>
  <nav class="strip" aria-label="설비">
    {#each ordered as asset (asset.assetId)}
      {@const read = rows[asset.assetId]}
      {@const row = typeof read === "object" ? read : null}
      {@const fact = tile(row, read)}
      {@const model = modelShort(asset.assetId)}
      {@const review = reviews[asset.assetId]}
      {@const path = fact.trace.length > 1 ? sparkline(fact.trace, 120, 28) : ""}
      <a class="tile" href={href(asset.assetId)} aria-current={asset.assetId === selected ? "page" : undefined}>
        <span class="top"><strong>{name(asset)}</strong><span class="model" class:over={model.over}>{model.text}</span></span>
        <span class="what">{fact.what}{#if asset.flow==="stored-history"}<small>{"\u00a0· 저장된 기록"}</small>{/if}</span>
        {#if fact.how}<span class="how">{fact.how}</span>{/if}
        <span class="bottom"><small>{fact.when}</small>{#if path}<svg viewBox="0 0 120 28" preserveAspectRatio="none" aria-hidden="true"><path d={path}/></svg>{/if}</span>
        {#each problems(asset.assetId, row) as problem (problem.note.id)}<small class="issue">{problem.text}</small>{/each}
        {#if asset.attentionCount}<small class="issue">운영 확인 항목 {asset.attentionCount}건</small>{/if}
        {#if imports.get(asset.assetId)}<small class="issue">{imports.get(asset.assetId)!.text}</small>{/if}
        {#if review?.text && review.text !== "기록 없음"}<small>검토 · {review.text}</small>{/if}
      </a>
    {/each}
  </nav>
</section>

<style>
  .assets { display: grid; gap: var(--space-2); min-width: 0; }
  .head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: var(--space-2) var(--space-4); }
  h2 { margin: 0; font-size: var(--font-body); } h2 span { font-weight: 400; color: var(--color-ink-muted); font-size: var(--font-small); }
  .bearing-entry { font-size: var(--font-small); font-weight: 650; }
  /* 설비 칸은 가로로 이어지고, 많으면 옆으로 넘겨 본다. */
  .strip { display: flex; gap: var(--space-3); overflow-x: auto; padding-bottom: var(--space-1); }
  .tile { flex: 0 0 360px; display: grid; grid-template-columns:minmax(0,1fr) 72px;gap: 4px var(--space-2); align-content: start; padding: var(--space-2) var(--space-3); border: 1px solid var(--color-border);
    border-top: 4px solid transparent; border-radius: var(--radius-control); background: var(--color-surface); color: var(--color-ink); text-decoration: none; }
  .tile:hover { border-color: var(--color-action); }
  .compact .tile{flex-basis:300px;display:block;padding:var(--space-2) var(--space-3)}
  .compact .tile>.what,.compact .tile>.how,.compact .tile>.bottom{display:none}
  .tile[aria-current="page"] { border-top-color: var(--color-action); background: var(--color-surface-selected); }
  .top { grid-column:1/-1;display: flex; justify-content: space-between; align-items: baseline; gap: var(--space-2); }
  .top strong { font-size: var(--font-body); }
  .model { font-size: var(--font-label); color: var(--color-ink-muted); white-space: nowrap; }
  .model.over { color: var(--color-failure-ink, #b42318); font-weight: 650; }
  .what { grid-column:1;font-size: var(--font-small); overflow-wrap: anywhere; }
  .how { grid-column:1;font-size:var(--font-small);font-weight: 700; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
  .bottom { display:contents }
  .bottom small{grid-column:1/-1}.bottom svg{grid-column:2;grid-row:2/4;align-self:center;width:72px}
  small { font-size: var(--font-label); color: var(--color-ink-muted); word-break: keep-all; }
  small.issue { grid-column:1/-1;color: var(--color-caution-ink); }
  svg { width: 120px; height: 28px; flex: none; }
  svg path { fill: none; stroke: var(--color-action); stroke-width: 1.5; vector-effect: non-scaling-stroke; }
</style>
