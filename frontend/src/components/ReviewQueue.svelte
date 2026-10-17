<script lang="ts">
  import {onMount, untrack} from "svelte";
  import type {Snapshot} from "../monitor";
  import type {Review} from "../reviews";
  import {captureUrl, readCaptures, CaptureNotFound, type Capture} from "../outlook-captures";
  import {assetTabUrl} from "../routes";
  import StatusNotice from "./StatusNotice.svelte";
  import OutlookReviewDetail from "./OutlookReviewDetail.svelte";

  type Props = {
    snapshot: Snapshot; writable: boolean;
    focusAssetId: string; focusCaptureId: string | null; focusFindingId: string | null;
  };
  let {snapshot, writable, focusAssetId, focusCaptureId, focusFindingId}: Props = $props();
  type Status = "open" | "acknowledged" | "closed";
  type Item =
    | {kind: "outlook"; key: string; assetId: string; status: Status; at: string; title: string; href: string; capture: Capture}
    | {kind: "analysis"; key: string; assetId: string; status: Status; at: string | null; title: string; href: string; review: Review};
  const ASSET_LIMIT = 20;
  const STATUS: Record<Status, string> = {open: "검토 대기", acknowledged: "확인함", closed: "검토 종료"};
  const ANALYSIS = {phase: "3상 불평형 분석", file: "파일 특징 분석"};
  let captures: Capture[] = $state([]);
  let loadState: "loading" | "ready" = $state("loading");
  let failedAssets: string[] = $state([]);
  let missingFocus = $state(false);
  let moreAvailable = $state(false);
  // A direct link opens with every status so its subject is visible; later links keep the filter.
  let statusFilter: Status | "all" = $state(untrack(() => focusCaptureId || focusFindingId) ? "all" : "open");
  let typeFilter: "all" | "analysis" | "outlook" = $state("all");

  const clock = (at: string | null) => at ? new Date(at).toLocaleString("ko-KR", {timeZone: "Asia/Seoul"}) : "시각 기록 없음";
  const findingUrl = (review: Review) => "/web-next/?" + new URLSearchParams({page: "maintenance",
    monitor_asset: review.assetId, finding_id: review.findingId});
  const items = $derived.by((): Item[] => {
    const analysis: Item[] = (snapshot.reviewInbox.available ? snapshot.reviewInbox.reviews : []).map((review) => ({
      kind: "analysis", key: "finding:" + review.findingId, assetId: review.assetId, status: review.status,
      at: review.linked.map((item) => item.completedAt).filter((at): at is string => !!at).sort().at(-1) ?? null,
      title: review.assetId + " · " + ([...new Set(review.linked.map((item) => ANALYSIS[item.kind]))].join(" · ") || "분석 결과"),
      href: findingUrl(review), review,
    }));
    const outlooks: Item[] = captures.map((capture) => ({
      kind: "outlook", key: "capture:" + capture.id, assetId: capture.outlook.assetId,
      status: capture.review.status, at: capture.capturedAt,
      title: capture.outlook.assetId + " · " + capture.outlook.series + " 전망",
      href: captureUrl(capture.outlook.assetId, capture.id), capture,
    }));
    return [...analysis, ...outlooks].sort((a, b) => (b.at ?? "").localeCompare(a.at ?? ""));
  });
  const counts = $derived({
    open: items.filter((item) => item.status === "open").length,
    acknowledged: items.filter((item) => item.status === "acknowledged").length,
  });
  const shown = $derived(items.filter((item) =>
    (statusFilter === "all" || item.status === statusFilter) && (typeFilter === "all" || item.kind === typeFilter)));
  const selected = $derived.by((): Item | undefined => {
    if (focusCaptureId) return items.find((item) => item.kind === "outlook" && item.capture.id === focusCaptureId);
    if (focusFindingId) return items.find((item) => item.kind === "analysis" && item.review.findingId === focusFindingId);
    return shown[0];
  });

  function replace(updated: Capture) {
    captures = captures.map((item) => item.id === updated.id ? updated : item);
  }
  onMount(() => {
    const request = new AbortController();
    const assets = snapshot.assets.slice(0, ASSET_LIMIT);
    void Promise.all(assets.map(async (asset) => {
      try {
        const page = await readCaptures(asset.assetId, {}, request.signal);
        if (page.nextBefore) moreAvailable = true;
        return page.captures;
      } catch {
        if (!request.signal.aborted) failedAssets = [...failedAssets, asset.assetId];
        return [];
      }
    })).then(async (pages) => {
      if (request.signal.aborted) return;
      const loaded = pages.flat();
      // A direct link to an older request is read by its exact identity.
      if (focusCaptureId && focusAssetId && !loaded.some((item) => item.id === focusCaptureId)) {
        try {
          loaded.push(...(await readCaptures(focusAssetId, {captureId: focusCaptureId}, request.signal)).captures);
        } catch (cause: unknown) {
          if (!request.signal.aborted && cause instanceof CaptureNotFound) missingFocus = true;
          else if (!request.signal.aborted) failedAssets = [...failedAssets, focusAssetId];
        }
      }
      if (request.signal.aborted) return;
      captures = loaded;
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
          onclick={() => statusFilter = value as Status | "all"}>{label}</button>
      {/each}
    </div>
    <label class="type">종류
      <select value={typeFilter} onchange={(event) => typeFilter = event.currentTarget.value as typeof typeFilter}>
        <option value="all">전체</option><option value="analysis">분석 결과</option><option value="outlook">검토 요청한 전망</option>
      </select>
    </label>
    {#if loadState === "loading"}
      <StatusNotice message="검토 목록을 불러오고 있습니다." />
    {:else}
      {#if !snapshot.reviewInbox.available}
        <StatusNotice kind="uncertain" message="이번 조회에 분석 결과 검토 목록이 없습니다. 검토가 없다는 뜻은 아닙니다." />
      {:else if snapshot.reviewInbox.partial}
        <StatusNotice kind="uncertain" message="분석 결과 검토가 일부만 조회됐습니다. 보이지 않는 기록을 종료된 것으로 보지 마세요." />
      {/if}
      {#if failedAssets.length}
        <StatusNotice kind="uncertain" message={"다음 설비의 검토 요청을 불러오지 못했습니다: " + failedAssets.join(", ") + ". 요청이 없다는 뜻은 아닙니다."} />
      {/if}
      {#if snapshot.assets.length > ASSET_LIMIT || moreAvailable}
        <p class="context">설비는 {ASSET_LIMIT}곳까지, 설비마다 최근 검토 요청 20건까지 보여 줍니다.</p>
      {/if}
      {#if shown.length}
        <ul class="items">
          {#each shown as item (item.key)}
            <li><a href={item.href} aria-current={selected?.key === item.key ? "true" : undefined}>
              <strong>{item.title}</strong>
              <span>{item.kind === "outlook" ? "검토 요청한 전망" : "분석 결과"} · {STATUS[item.status]} · {clock(item.at)}</span>
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
      <StatusNotice kind="uncertain" title="검토 요청을 찾을 수 없습니다"
        message="이 설비에서 해당 검토 요청을 찾을 수 없습니다. 다른 설비의 기록으로 대신 보여 주지 않습니다." />
    {:else if !selected}
      <p class="context">왼쪽에서 검토 항목을 고르세요.</p>
    {:else if selected.kind === "outlook"}
      {#key selected.capture.id}
        <OutlookReviewDetail capture={selected.capture} {writable} onUpdated={replace} />
      {/key}
    {:else}
      {@const review = selected.review}
      <article class="analysis">
        <div class="head"><h2>{selected.title}</h2><span class="badge">{STATUS[review.status]}</span></div>
        <ul class="evidence">
          {#each review.linked as evidence (evidence.evidenceId)}
            <li>{ANALYSIS[evidence.kind]} · 데이터 출처 {evidence.sourceId} · 측정 위치 {evidence.pointId ?? "미확인"}
              · 원본 품질 {evidence.quality ?? "미확인"} · 분석 {clock(evidence.completedAt)}</li>
          {/each}
          {#each review.missing as evidenceId (evidenceId)}
            <li>분석 근거 {evidenceId}를 이번 목록에서 찾지 못했습니다. 조회 제한이나 오류일 수 있어 다른 근거로 대신하지 않습니다.</li>
          {/each}
        </ul>
        <p class="context">분석 결과의 메모·확인·종료는 아직 이전 화면에서 기록합니다.</p>
        <p class="links">
          <a href={"/web/?monitor_asset=" + encodeURIComponent(review.assetId) + "#evidence"}>이전 화면에서 메모·확인·종료하기 →</a>
          <a href={assetTabUrl(review.assetId, "summary")}>설비 보기 →</a>
        </p>
        <details>
          <summary>기술 상세</summary>
          <dl>
            <div><dt>확인할 항목</dt><dd>{review.findingId}</dd></div>
            <div><dt>분석 실행</dt><dd>{review.runId}</dd></div>
            <div><dt>분석 근거</dt><dd>{review.evidenceIds.join(", ")}</dd></div>
          </dl>
        </details>
      </article>
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
  .head { display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--space-2); align-items: center; }
  .head h2 { margin: 0; overflow-wrap: anywhere; }
  .badge { font-weight: 700; border: 1px solid var(--color-ink); border-radius: 999px; padding: 2px var(--space-3); font-size: var(--font-small); }
  .evidence { padding-inline-start: var(--space-5); color: var(--color-ink-muted); }
  .evidence li { overflow-wrap: anywhere; }
  .links { display: flex; flex-wrap: wrap; gap: var(--space-4); }
  summary { cursor: pointer; font-weight: 650; color: var(--color-action); padding-block: var(--space-2); }
  dl { display: grid; gap: var(--space-2); margin: var(--space-2) 0; }
  dt { color: var(--color-ink-muted); font-size: var(--font-small); }
  dd { margin: 0; font-family: ui-monospace, monospace; overflow-wrap: anywhere; }
</style>
