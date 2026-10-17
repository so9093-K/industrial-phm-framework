<script lang="ts">
  import {onMount, untrack} from "svelte";
  import type {Snapshot} from "../monitor";
  import type {Evidence} from "../reviews";
  import {captureUrl, readCaptures, CaptureNotFound, type Capture} from "../outlook-captures";
  import {findingUrl, readFindingReviews, type FindingReview} from "../finding-reviews";
  import StatusNotice from "./StatusNotice.svelte";
  import FindingReviewDetail from "./FindingReviewDetail.svelte";
  import OutlookReviewDetail from "./OutlookReviewDetail.svelte";

  type Props = {
    snapshot: Snapshot; writable: boolean;
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
  const ANALYSIS = {phase: "3상 불평형 분석", file: "파일 특징 분석"};
  let captures: Capture[] = $state([]);
  let findings: FindingReview[] = $state([]);
  let loadState: "loading" | "ready" = $state("loading");
  let failedAssets: string[] = $state([]);
  let missingFocus = $state(false);
  let moreAvailable = $state(false);
  // A direct link opens with every status so its subject is visible; later links keep the filter.
  let statusFilter: Status | "all" = $state(untrack(() => focusCaptureId || focusFindingId) ? "all" : "open");
  let typeFilter: "all" | "analysis" | "outlook" = $state("all");
  // The item someone just acted on stays open even when its new status leaves the filter.
  let keptKey: string | null = $state(null);

  const clock = (at: string) => new Date(at).toLocaleString("ko-KR", {timeZone: "Asia/Seoul"});
  // Stored analysis evidence comes from the same monitor snapshot; without it the
  // review is still shown, but never next to another record's evidence.
  const evidenceFor = (review: FindingReview): Evidence[] | null => {
    if (!snapshot.reviewInbox.available) return null;
    const inbox = snapshot.reviewInbox.reviews.find((item) =>
      item.findingId === review.findingId && item.assetId === review.assetId && item.runId === review.runId);
    return inbox ? inbox.linked : snapshot.reviewInbox.evidenceComplete ? [] : null;
  };
  const items = $derived.by((): Item[] => {
    const analysis: Item[] = findings.map((review) => {
      const linked = review.subject === "analysis" ? evidenceFor(review) : null;
      const kinds = [...new Set((linked ?? []).map((item) => ANALYSIS[item.kind]))].join(" · ");
      return {
        kind: "analysis", key: "finding:" + review.findingId, assetId: review.assetId, status: review.status,
        at: review.events.at(-1)?.recordedAt ?? review.observedAt,
        title: review.assetId + " · " + (review.subject === "model" ? "이상 탐지 모델 결과" : kinds || "분석 결과"),
        label: review.subject === "model" ? "분석 결과 · 이상 탐지 모델" : "분석 결과",
        href: findingUrl(review.assetId, review.findingId), review, linked,
      };
    });
    const outlooks: Item[] = captures.map((capture) => ({
      kind: "outlook", key: "capture:" + capture.id, assetId: capture.outlook.assetId,
      status: capture.review.status, at: capture.capturedAt,
      title: capture.outlook.assetId + " · " + capture.outlook.series + " 전망", label: "검토 요청한 전망",
      href: captureUrl(capture.outlook.assetId, capture.id), capture,
    }));
    return [...analysis, ...outlooks].sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
  });
  const counts = $derived({
    open: items.filter((item) => item.status === "open").length,
    acknowledged: items.filter((item) => item.status === "acknowledged").length,
  });
  const shown = $derived(items.filter((item) =>
    (statusFilter === "all" || item.status === statusFilter) && (typeFilter === "all" || item.kind === typeFilter)));
  const selected = $derived.by((): Item | undefined => {
    if (focusCaptureId) return items.find((item) => item.kind === "outlook" && item.capture.id === focusCaptureId);
    if (focusFindingId) return items.find((item) => item.kind === "analysis" && item.review.findingId === focusFindingId
      && (!focusAssetId || item.assetId === focusAssetId));
    return items.find((item) => item.key === keptKey) ?? shown[0];
  });

  function replaceCapture(updated: Capture) {
    captures = captures.map((item) => item.id === updated.id ? updated : item);
    keptKey = "capture:" + updated.id;
  }
  function replaceFinding(updated: FindingReview) {
    findings = findings.map((item) => item.findingId === updated.findingId ? updated : item);
    keptKey = "finding:" + updated.findingId;
  }
  onMount(() => {
    const request = new AbortController();
    const assets = snapshot.assets.slice(0, ASSET_LIMIT).map((asset) => asset.assetId);
    if (focusAssetId && !assets.includes(focusAssetId)) assets.push(focusAssetId);
    const failed = (assetId: string) => {
      if (!request.signal.aborted && !failedAssets.includes(assetId)) failedAssets = [...failedAssets, assetId];
    };
    void Promise.all(assets.map(async (assetId) => {
      const [outlooks, reviews] = await Promise.all([
        readCaptures(assetId, {}, request.signal).then((page) => {
          if (page.nextBefore) moreAvailable = true;
          return page.captures;
        }).catch(() => { failed(assetId); return []; }),
        readFindingReviews(assetId, request.signal).then((page) => {
          if (page.truncated) moreAvailable = true;
          return page.items;
        }).catch(() => { failed(assetId); return []; }),
      ]);
      return {outlooks, reviews};
    })).then(async (pages) => {
      if (request.signal.aborted) return;
      const loaded = pages.flatMap((page) => page.outlooks);
      // A direct link to an older request is read by its exact identity.
      if (focusCaptureId && focusAssetId && !loaded.some((item) => item.id === focusCaptureId)) {
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
      if (focusFindingId && !failedAssets.includes(focusAssetId)
        && !findings.some((item) => item.findingId === focusFindingId)) missingFocus = true;
      loadState = "ready";
    });
    return () => request.abort();
  });
</script>

<div class="queue-layout">
  <section class="ui-panel queue" aria-labelledby="queue-title">
    <h2 id="queue-title">검토함</h2>
    <div class="filters" role="group" aria-label="검토 상태">
      {#each [["open", "검토 대기 " + counts.open], ["acknowledged", "확인함 " + counts.acknowledged], ["closed", "검토 종료"], ["all", "전체"]] as [value, label] (value)}
        <button type="button" class="chip" aria-pressed={statusFilter === value}
          onclick={() => { statusFilter = value as Status | "all"; keptKey = null; }}>{label}</button>
      {/each}
    </div>
    <label class="type">종류
      <select value={typeFilter} onchange={(event) => { typeFilter = event.currentTarget.value as typeof typeFilter; keptKey = null; }}>
        <option value="all">전체</option><option value="analysis">분석 결과</option><option value="outlook">검토 요청한 전망</option>
      </select>
    </label>
    {#if loadState === "loading"}
      <StatusNotice message="검토 목록을 불러오고 있습니다." />
    {:else}
      {#if failedAssets.length}
        <StatusNotice kind="uncertain" message={"다음 설비의 검토 항목을 불러오지 못했습니다: " + failedAssets.join(", ") + ". 검토가 없다는 뜻은 아닙니다."} />
      {/if}
      {#if snapshot.assets.length > ASSET_LIMIT || moreAvailable}
        <p class="context">설비는 {ASSET_LIMIT}곳까지, 설비마다 최근 검토 요청한 전망 20건과 분석 결과 검토 100건까지 보여 줍니다.</p>
      {/if}
      {#if shown.length}
        <ul class="items">
          {#each shown as item (item.key)}
            <li><a href={item.href} aria-current={selected?.key === item.key ? "true" : undefined}>
              <strong>{item.title}</strong>
              <span>{item.label} · {STATUS[item.status]} · {clock(item.at)}</span>
            </a></li>
          {/each}
        </ul>
      {:else}
        <p class="context">이 조건에 맞는 검토 항목이 없습니다.</p>
      {/if}
    {/if}
  </section>

  <section class="ui-panel detail-panel" aria-label="고른 검토 항목">
    {#if loadState === "loading"}
      <StatusNotice message="검토 항목을 불러오고 있습니다." />
    {:else if missingFocus}
      <StatusNotice kind="uncertain" title="검토 항목을 찾을 수 없습니다"
        message="이 설비에서 해당 검토 항목을 찾을 수 없습니다. 다른 설비의 기록으로 대신 보여 주지 않습니다." />
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
