<script lang="ts">
  import {onMount, untrack} from "svelte";
  import {routeUrl} from "../routes";
  import {assetLabel, type Snapshot} from "../monitor";
  import type {Evidence} from "../reviews";
  import {captureUrl, readCaptures, CaptureNotFound, type Capture} from "../outlook-captures";
  import {seriesName} from "../series-names";
  import {findingUrl, readFindingReviews, type FindingReview} from "../finding-reviews";
  import {latestDecision, DECISION_LABEL} from "../review-writes";
  import {filterReviewItems, selectReviewItem, selectReviewAssets} from "../review-selection";
  import StatusNotice from "./StatusNotice.svelte";
  import FindingReviewDetail from "./FindingReviewDetail.svelte";
  import OutlookReviewDetail from "./OutlookReviewDetail.svelte";

  type Props = {
    snapshot: Snapshot | null; writable: boolean;
    focusAssetId: string; focusCaptureId: string | null; focusFindingId: string | null;
  };
  let {snapshot, writable, focusAssetId, focusCaptureId, focusFindingId}: Props = $props();
  type Status = "open" | "acknowledged" | "closed";
  type Item =
    | {kind: "outlook"; key: string; assetId: string; status: Status; at: string; title: string; label: string; href: string; capture: Capture}
    | {kind: "analysis"; key: string; assetId: string; status: Status; at: string; title: string; label: string; href: string;
      review: FindingReview; linked: Evidence[] | null};
  const ASSET_LIMIT = 20;
  const STATUS: Record<Status, string> = {open: "검토 대기", acknowledged: "확인함", closed: "검토 종료"};
  // What the item was last judged to need, shown beside its status.
  const judged = (item: Item) => latestDecision(item.kind === "outlook" ? item.capture.review.events : item.review.events);
  const ANALYSIS = {phase: "3상 불평형 분석", file: "파일 특징 분석"};
  let captures: Capture[] = $state([]);
  // Display names of the captured series, looked up once each; the ID shows until then.
  let seriesNames: Record<string, string> = $state({});
  $effect(() => {
    for (const capture of captures) {
      const {assetId, kind, series} = capture.outlook, key = assetId + "\n" + kind + "\n" + series;
      if (key in untrack(() => seriesNames)) continue;
      void seriesName(assetId, kind, series)
        .then((name) => { seriesNames = {...seriesNames, [key]: name}; })
        .catch(() => { /* A missing display name must not hide a verified review. */ });
    }
  });
  let findings: FindingReview[] = $state([]);
  let loadState: "loading" | "ready" = $state("loading");
  let failedAssets: string[] = $state([]);
  let missingFocus = $state(false);
  let olderFindingFocus = $state(false);
  let truncatedFindingAssets: Record<string, boolean> = $state({});
  let moreAvailable = $state(false);
  let scopeAssetId = $state(untrack(() => focusAssetId));
  let ignoreFocus = $state(false);
  let captureCursors: Record<string, string> = $state({});
  let loadingMore = $state(false);
  let historyProblem = $state("");
  let hiddenFindings = $state(false);
  let loadedAssets = $state(0);
  let partialAssetScope = $state(false);
  // A direct link opens with every status so its subject is visible; later links keep the filter.
  let statusFilter: Status | "all" = $state(untrack(() => focusCaptureId || focusFindingId) ? "all" : "open");
  let typeFilter: "all" | "analysis" | "outlook" = $state("all");
  // The item someone just acted on stays open even when its new status leaves the filter.
  let keptKey: string | null = $state(null);

  const clock = (at: string) => new Date(at).toLocaleString("ko-KR", {timeZone: "Asia/Seoul"});
  // Stored analysis evidence comes from the same monitor snapshot, matched by asset, run
  // and evidence ID; without it the review is still shown, never next to another record.
  const evidenceFor = (review: FindingReview): Evidence[] | null => {
    if (!snapshot?.analyses.available) return null;
    const found = snapshot.analyses.records.filter((item) => item.assetId === review.assetId
      && item.runId === review.runId && review.evidenceIds.includes(item.evidenceId)).map((item): Evidence => ({
      runId: item.runId, evidenceId: item.evidenceId, assetId: item.assetId, sourceId: item.sourceId,
      pointId: item.pointId, capabilityId: item.capabilityId, kind: item.kind, completedAt: item.completedAt,
      quality: item.quality,
    }));
    return found.length || !snapshot.analyses.truncated ? found : null;
  };
  const items = $derived.by((): Item[] => {
    const analysis: Item[] = findings.map((review) => {
      const linked = review.subject === "analysis" ? evidenceFor(review) : null;
      const kinds = [...new Set((linked ?? []).map((item) => ANALYSIS[item.kind]))].join(" · ");
      return {
        kind: "analysis", key: "finding:" + review.findingId, assetId: review.assetId, status: review.status,
        at: review.events.at(-1)?.recordedAt ?? review.observedAt,
        title: assetLabel(snapshot?.assets ?? [], review.assetId) + " · " + (review.subject === "model" ? "이상 탐지 모델 결과" : kinds || "분석 결과"),
        label: review.subject === "model" ? "분석 결과 · 이상 탐지 모델" : "분석 결과",
        href: findingUrl(review.assetId, review.findingId), review, linked,
      };
    });
    const outlooks: Item[] = captures.map((capture) => ({
      kind: "outlook", key: "capture:" + capture.id, assetId: capture.outlook.assetId,
      status: capture.review.status, at: capture.capturedAt,
      title: assetLabel(snapshot?.assets ?? [], capture.outlook.assetId) + " · "
        + (seriesNames[capture.outlook.assetId + "\n" + capture.outlook.kind + "\n" + capture.outlook.series] ?? capture.outlook.series) + " 전망",
      label: "검토 요청한 전망",
      href: captureUrl(capture.outlook.assetId, capture.id), capture,
    }));
    return [...analysis, ...outlooks].sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
  });
  const counts = $derived({
    open: items.filter((item) => item.status === "open").length,
    acknowledged: items.filter((item) => item.status === "acknowledged").length,
  });
  const shown = $derived(filterReviewItems(items, statusFilter, typeFilter));
  const selected = $derived(selectReviewItem(
    shown,
    ignoreFocus || !focusAssetId ? null
      : {assetId: focusAssetId, key: focusCaptureId ? "capture:" + focusCaptureId
        : focusFindingId ? "finding:" + focusFindingId : ""},
    keptKey,
  ));

  function replaceCapture(updated: Capture) {
    captures = captures.map((item) => item.id === updated.id ? updated : item);
    keptKey = "capture:" + updated.id;
    statusFilter = "all";
  }
  function replaceFinding(updated: FindingReview) {
    findings = findings.map((item) => item.findingId === updated.findingId ? updated : item);
    keptKey = "finding:" + updated.findingId;
    statusFilter = "all";
  }
  function openAssetScope(event: SubmitEvent) {
    event.preventDefault();
    const id = scopeAssetId.trim();
    if (!id) return;
    location.assign(routeUrl({page: "maintenance", assetId: id, tab: "summary", method: null, data: null}));
  }

  let olderRequest: AbortController | null = null;
  async function loadOlderCaptures() {
    if (loadingMore) return;
    const [assetId, before] = Object.entries(captureCursors)[0] ?? [];
    if (!assetId || !before) return;
    loadingMore = true; historyProblem = "";
    const request = new AbortController(); olderRequest = request;
    try {
      const page = await readCaptures(assetId, {before}, request.signal);
      if (request.signal.aborted) return;
      captures = [...captures, ...page.captures.filter((item) => !captures.some((prior) => prior.id === item.id))];
      const next = {...captureCursors};
      if (page.nextBefore) next[assetId] = page.nextBefore;
      else delete next[assetId];
      captureCursors = next;
      moreAvailable = hiddenFindings || Object.keys(next).length > 0;
    } catch {
      if (!request.signal.aborted) historyProblem = "이전 전망을 읽지 못했습니다. 현재 목록은 그대로 유지됩니다.";
    } finally {
      if (!request.signal.aborted) loadingMore = false;
    }
  }

  onMount(() => {
    const request = new AbortController();
    // A direct asset route reads its exact owner; a general queue is bounded.
    const scope = selectReviewAssets([
      ...(snapshot?.assets.map((asset) => asset.assetId) ?? []),
      ...(snapshot?.reviewInbox.reviews.map((review) => review.assetId) ?? []),
      ...(snapshot?.analyses.records.map((item) => item.assetId) ?? []),
    ], focusAssetId, ASSET_LIMIT);
    const assets = scope.assets;
    partialAssetScope = scope.partial || Boolean(snapshot?.truncated);
    // An identity-bearing bookmark without its owning asset is not a review subject.
    if ((focusCaptureId || focusFindingId) && !focusAssetId) missingFocus = true;
    const failed = (assetId: string) => {
      if (!request.signal.aborted && !failedAssets.includes(assetId)) failedAssets = [...failedAssets, assetId];
    };
    void Promise.all(assets.map(async (assetId) => {
      const [outlooks, reviews] = await Promise.all([
        readCaptures(assetId, {}, request.signal).then((page) => {
          if (page.nextBefore) {
            moreAvailable = true;
            captureCursors = {...captureCursors, [assetId]: page.nextBefore};
          }
          return page.captures;
        }).catch(() => { failed(assetId); return []; }),
        readFindingReviews(assetId, request.signal).then((page) => {
          if (page.truncated) {
            moreAvailable = true; hiddenFindings = true;
            truncatedFindingAssets = {...truncatedFindingAssets, [assetId]: true};
          }
          return page.items;
        }).catch(() => { failed(assetId); return []; }),
      ]);
      return {outlooks, reviews};
    })).then(async (pages) => {
      if (request.signal.aborted) return;
      const loaded = pages.flatMap((page) => page.outlooks);
      // A direct link to an older request is read by its exact identity.
      if (focusCaptureId && focusAssetId && !loaded.some((item) =>
        item.id === focusCaptureId && item.outlook.assetId === focusAssetId)) {
        try {
          loaded.push(...(await readCaptures(focusAssetId, {captureId: focusCaptureId}, request.signal)).captures);
        } catch (cause: unknown) {
          if (!request.signal.aborted && cause instanceof CaptureNotFound) missingFocus = true;
          else failed(focusAssetId);
        }
      }
      if (request.signal.aborted) return;
      captures = loaded;
      findings = pages.flatMap((page) => page.reviews);
      loadedAssets = assets.length;
      if (focusFindingId && !failedAssets.includes(focusAssetId)
        && !findings.some((item) => item.findingId === focusFindingId)) {
        if (truncatedFindingAssets[focusAssetId]) olderFindingFocus = true;
        else missingFocus = true;
      }
      loadState = "ready";
    });
    return () => { request.abort(); olderRequest?.abort(); };
  });
</script>

<div class="queue-layout">
  <section class="ui-panel queue" aria-labelledby="queue-title">
    <h2 id="queue-title">검토함</h2>
    {#if snapshot === null || partialAssetScope}
      {#if snapshot === null}
        <StatusNotice kind="uncertain" message="관측 요약을 읽지 못해 전체 검토 목록은 알 수 없습니다. 지정한 설비의 검토 기록만 따로 확인합니다." />
      {:else}
        <StatusNotice kind="uncertain" message="설비 목록이 일부만 조회됐습니다. 찾는 설비가 보이지 않으면 설비 ID로 직접 조회할 수 있습니다." />
      {/if}
      <form onsubmit={openAssetScope} class="scope-form">
        <label for="review-scope">검토할 설비 ID</label>
        <input id="review-scope" value={scopeAssetId} oninput={(event) => scopeAssetId = event.currentTarget.value} maxlength="128" required placeholder="설비 ID 입력" />
        <button class="ui-button ui-button-primary" type="submit" disabled={!scopeAssetId.trim()}>이 설비의 검토 열기</button>
      </form>
    {/if}
    <div class="filters" role="group" aria-label="검토 상태">
      {#each [["open", "검토 대기 " + counts.open + " (조회됨)"], ["acknowledged", "확인함 " + counts.acknowledged + " (조회됨)"], ["closed", "검토 종료"], ["all", "전체"]] as [value, label] (value)}
        <button type="button" class="chip" aria-pressed={statusFilter === value}
          onclick={() => { statusFilter = value as Status | "all"; keptKey = null; ignoreFocus = true; }}>{label}</button>
      {/each}
    </div>
    <label class="type">종류
      <select value={typeFilter} onchange={(event) => { typeFilter = event.currentTarget.value as typeof typeFilter; keptKey = null; ignoreFocus = true; }}>
        <option value="all">전체</option><option value="analysis">분석 결과</option><option value="outlook">검토 요청한 전망</option>
      </select>
    </label>
    {#if loadState === "loading"}
      <StatusNotice message="검토 목록을 불러오고 있습니다." />
    {:else}
      {#if failedAssets.length}
        <StatusNotice kind="uncertain" message={"다음 설비의 검토 항목을 불러오지 못했습니다: " + failedAssets.join(", ") + ". 검토가 없다는 뜻은 아닙니다."}
          actionLabel="검토 목록 다시 읽기" onAction={() => location.reload()} />
      {/if}
      <p class="context">{focusAssetId ? "선택한 설비 1곳" : "설비 " + loadedAssets + "곳"}의 검토 기록 조회를 시도했습니다.
        {#if partialAssetScope || hiddenFindings || moreAvailable}
          전체 검토 건수는 아닙니다. 설비당 분석 검토는 최근 최대 100건이며, 전망은 한 번에 20건씩 읽습니다.
        {:else if failedAssets.length} 일부 조회가 실패해 실제 건수보다 적을 수 있습니다.
        {/if}
      </p>
      {#if hiddenFindings}<StatusNotice kind="uncertain" message="일부 분석 검토 기록은 조회 범위 밖에 있습니다. 목록에서 찾지 못했다고 기록이 없다는 뜻은 아닙니다." />{/if}
      {#if shown.length}
        <ul class="items">
          {#each shown as item (item.key)}
            <li><a href={item.href} aria-current={selected?.key === item.key ? "true" : undefined}>
              <strong>{item.title}</strong>
              <span>{item.label} · {STATUS[item.status]}{judged(item) ? " · " + DECISION_LABEL[judged(item)!] : ""} · {clock(item.at)}</span>
            </a></li>
          {/each}
        </ul>
      {:else}
        <p class="context">{snapshot === null && !focusAssetId ? "위에서 검토할 설비 ID를 입력하세요. 전체 설비 목록을 조회하지 못한 상태입니다." : failedAssets.length || hiddenFindings || partialAssetScope ? "현재 확인된 범위에서 조건에 맞는 검토 항목이 없습니다. 전체 기록이 없다는 뜻은 아닙니다." : "이 조건에 맞는 검토 항목이 없습니다."}</p>
      {/if}
      {#if Object.keys(captureCursors).length}
        <button type="button" class="ui-button" disabled={loadingMore} onclick={() => void loadOlderCaptures()}>
          {loadingMore ? "이전 전망 불러오는 중" : "이전 전망 더 보기"}
        </button>
      {/if}
      {#if historyProblem}<StatusNotice kind="uncertain" message={historyProblem} actionLabel="다시 불러오기" onAction={() => void loadOlderCaptures()} />{/if}
    {/if}
  </section>

  <section class="ui-panel detail-panel" aria-label="고른 검토 항목">
    {#if loadState === "loading"}
      <StatusNotice message="검토 항목을 불러오고 있습니다." />
    {:else if missingFocus && !ignoreFocus}
      <StatusNotice kind="uncertain" title="검토 항목을 찾을 수 없습니다"
        message="이 설비에서 해당 검토 항목을 찾을 수 없습니다. 다른 설비의 기록으로 대신 보여 주지 않습니다." />
    {:else if olderFindingFocus && !ignoreFocus}
      <StatusNotice kind="uncertain" title="검토 기록이 이번 조회 범위 밖에 있습니다"
        message="분석 검토 목록은 설비당 최대 100건만 제공합니다. 더 오래된 기록을 찾지 못한 것이 삭제됐다는 뜻은 아닙니다." />
    {:else if !selected && (focusCaptureId || focusFindingId) && !ignoreFocus
      && failedAssets.includes(focusAssetId)}
      <StatusNotice kind="uncertain" title="요청한 검토 기록을 확인하지 못했습니다"
        message="이 설비의 조회에 실패했습니다. 기록이 없다고 판단하지 않습니다."
        actionLabel="다시 불러오기" onAction={() => location.reload()} />
    {:else if !selected}
      <p class="context">왼쪽에서 검토 항목을 고르세요.</p>
    {:else if selected.kind === "outlook"}
      {#key selected.capture.id}
        <OutlookReviewDetail capture={selected.capture} {writable} onUpdated={replaceCapture} />
      {/key}
    {:else}
      {#key selected.review.findingId}
        <FindingReviewDetail review={selected.review} title={selected.title} linked={selected.linked} {writable}
          onUpdated={replaceFinding} />
      {/key}
    {/if}
  </section>
</div>

<style>
  .scope-form { display: grid; gap: var(--space-2); }
  .scope-form input { font: inherit; min-width: 0; min-height: 44px; padding: var(--space-2); border: 1px solid var(--color-border); border-radius: var(--radius-control); }
  .scope-form button { justify-self: start; }
  .queue-layout { display: flex; flex-wrap: wrap; gap: var(--space-4); align-items: flex-start; }
  .queue { flex: 1 1 300px; max-width: 420px; min-width: 0; display: flex; flex-direction: column; gap: var(--space-3); }
  .detail-panel { flex: 999 1 520px; min-width: 0; }
  .filters { display: flex; flex-wrap: wrap; gap: var(--space-2); }
  .chip { font: inherit; font-size: var(--font-small); min-height: 40px; padding: var(--space-2) var(--space-3);
    border: 1px solid var(--color-border); border-radius: 999px; background: var(--color-surface); color: var(--color-ink); }
  .chip[aria-pressed="true"] { border-color: var(--color-action); background: var(--color-surface-selected); color: var(--color-action); font-weight: 700; }
  .type { display: grid; gap: var(--space-1); font-size: var(--font-small); font-weight: 700; }
  .type select { font: inherit; font-weight: 400; min-height: 40px; padding: var(--space-2) var(--space-3);
    border: 1px solid var(--color-border); border-radius: var(--radius-control); background: var(--color-surface); color: var(--color-ink); }
  .items { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-2); }
  .items a { display: grid; gap: var(--space-1); padding: var(--space-3); border: 1px solid var(--color-border);
    border-radius: var(--radius-control); color: var(--color-ink); text-decoration: none; overflow-wrap: anywhere; }
  .items a[aria-current="true"] { border: 2px solid var(--color-action); background: var(--color-surface-selected); }
  .items span { color: var(--color-ink-muted); font-size: var(--font-small); }
  .context { color: var(--color-ink-muted); overflow-wrap: anywhere; }
</style>
