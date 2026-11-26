<script lang="ts">
  import {onMount, untrack} from "svelte";
  import {routeUrl} from "../routes";
  import {assetLabel, type Snapshot} from "../monitor";
  import type {Evidence} from "../reviews";
  import {captureUrl, readCaptures, CaptureNotFound, type Capture} from "../outlook-captures";
  import {seriesName} from "../series-names";
  import {findingUrl, readFindingReview, readFindingReviews, type FindingReview} from "../finding-reviews";
  import {latestDecision, DECISION_LABEL} from "../review-writes";
  import {filterReviewItems, firstGroup, GROUP_LABEL, REVIEW_GROUPS, reviewGroup, selectReviewItem, type ReviewGroup} from "../review-selection";
  import {readReviewAssetIndex} from "../review-index";
  import StatusNotice from "./StatusNotice.svelte";
  import FindingReviewDetail from "./FindingReviewDetail.svelte";
  import OutlookReviewDetail from "./OutlookReviewDetail.svelte";
  import ChangeCaptureDetail from "./ChangeCaptureDetail.svelte";
  import {readChangeReviews,changeCaptureUrl,type ChangeCapture} from "../change-reviews";

  type Props = {
    snapshot: Snapshot | null; writable: boolean;
    focusAssetId: string; focusCaptureId: string | null; focusFindingId: string | null;
  };
  let {snapshot, writable, focusAssetId, focusCaptureId, focusFindingId}: Props = $props();
  type Status = "open" | "acknowledged" | "closed";
  type Item =
    | {kind:"change";key:string;assetId:string;status:Status;at:string;title:string;label:string;href:string;change:ChangeCapture}
    | {kind: "outlook"; key: string; assetId: string; status: Status; at: string; title: string; label: string; href: string; capture: Capture}
    | {kind: "analysis"; key: string; assetId: string; status: Status; at: string; title: string; label: string; href: string;
      review: FindingReview; linked: Evidence[] | null};
  const eventsOf = (item: Item) => item.kind === "outlook" ? item.capture.review.events : item.kind === "change" ? item.change.review.events : item.review.events;
  // 목록은 사람이 남긴 판단으로 나눈다. 줄마다 판단과 가장 최근 메모를 먼저 보인다.
  const judged = (item: Item) => latestDecision(eventsOf(item));
  const verdict = (item: Item) => item.status === "closed" ? "검토 종료" : judged(item) ? DECISION_LABEL[judged(item)!] : "판단 전";
  const memoOf = (item: Item) => [...eventsOf(item)].reverse().find(event => event.note.trim())?.note.trim() ?? null;
  const ANALYSIS = {phase: "3상 불평형 분석", file: "파일 특징 분석"};
  let captures: Capture[] = $state([]);
  let changes:ChangeCapture[]=$state([]),changeCursors:Record<string,string>=$state({});
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
  let truncatedFindingAssets: Record<string, boolean> = $state({});
  let moreAvailable = $state(false);
  let scopeAssetId = $state(untrack(() => focusAssetId));
  let ignoreFocus = $state(false);
  let captureCursors: Record<string, string> = $state({});
  let loadingMore = $state(false);
  let historyProblem = $state("");
  let historyKind:"outlook"|"change"=$state("outlook");
  let hiddenFindings = $state(false);
  let loadedAssets = $state(0);
  let partialAssetScope = $state(false);
  let nextAsset: string | null = $state(null);
  let loadingAssets = $state(false);
  let assetIndexProblem = $state(false);
  let assetIndexChanged = $state(false);
  let assetIndexRevision: string | null = $state(null);
  // A direct link opens with every group so its subject is visible. Otherwise the first group with work opens.
  let groupFilter: ReviewGroup | "all" | null = $state(untrack(() => focusCaptureId || focusFindingId) ? "all" : null);
  let typeFilter: "all" | "analysis" | "outlook" | "change" = $state("all");
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
      label: "전망",
      href: captureUrl(capture.outlook.assetId, capture.id), capture,
    }));
    const changed:Item[]=changes.map(change=>({kind:"change",key:"capture:"+change.id,assetId:change.assetId,
      status:change.review.status,at:change.review.events.at(-1)?.recordedAt??change.capturedAt,
      title:assetLabel(snapshot?.assets??[],change.assetId)+" · "+change.finding.label,
      label:"특이사항",href:changeCaptureUrl(change.assetId,change.id),change}));
    return [...analysis, ...outlooks,...changed].sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
  });
  const grouped = $derived(items.map((item) => ({...item, group: reviewGroup(item.status, judged(item))})));
  const counts = $derived(Object.fromEntries(REVIEW_GROUPS.map((group) => [group, grouped.filter((item) => item.group === group).length])) as Record<ReviewGroup, number>);
  const activeFilter = $derived(groupFilter ?? firstGroup(counts));
  // Counts are of what was read; say so only when that is not everything.
  const partialCounts = $derived(partialAssetScope || hiddenFindings || moreAvailable || failedAssets.length > 0);
  const countText = (count: number) => String(count) + (partialCounts ? " (불러온 범위)" : "");
  const shown = $derived(filterReviewItems(grouped, activeFilter, typeFilter));
  const selected = $derived(selectReviewItem(
    shown,
    ignoreFocus || !focusAssetId ? null
      : {assetId: focusAssetId, key: focusCaptureId ? "capture:" + focusCaptureId
        : focusFindingId ? "finding:" + focusFindingId : ""},
    keptKey,
  ));

  // 방금 판단을 바꾼 항목은 새 판단이 지금 칸을 벗어나도 보이게 둔다. 상세가 기록을 다시 읽기만 했으면
  // (판단이 그대로면) 고른 칸을 그대로 둔다.
  function keepVisible(group: ReviewGroup) {
    if (activeFilter !== "all" && activeFilter !== group) groupFilter = "all";
  }
  function replaceCapture(updated: Capture) {
    captures = captures.map((item) => item.id === updated.id ? updated : item);
    keptKey = "capture:" + updated.id;
    keepVisible(reviewGroup(updated.review.status, latestDecision(updated.review.events)));
  }
  function replaceFinding(updated: FindingReview) {
    findings = findings.map((item) => item.findingId === updated.findingId ? updated : item);
    keptKey = "finding:" + updated.findingId;
    keepVisible(reviewGroup(updated.status, latestDecision(updated.events)));
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
    loadingMore = true; historyProblem = "";historyKind="outlook";
    const request = new AbortController(); olderRequest = request;
    try {
      const page = await readCaptures(assetId, {before}, request.signal);
      if (request.signal.aborted) return;
      captures = [...captures, ...page.captures.filter((item) => !captures.some((prior) => prior.id === item.id))];
      const next = {...captureCursors};
      if (page.nextBefore) next[assetId] = page.nextBefore;
      else delete next[assetId];
      captureCursors = next;
      moreAvailable = hiddenFindings || Object.keys(next).length > 0 || Object.keys(changeCursors).length>0;
    } catch {
      if (!request.signal.aborted) historyProblem = "이전 전망을 읽지 못했습니다. 현재 목록은 그대로 유지됩니다.";
    } finally {
      if (!request.signal.aborted) loadingMore = false;
    }
  }

  let scopeRequest: AbortController | null = null;
  async function loadOlderChanges(){
    const [asset,before]=Object.entries(changeCursors)[0]??[];if(loadingMore||!asset||!before)return;
    const request=new AbortController();olderRequest=request;loadingMore=true;historyProblem="";historyKind="change";
    try{const page=await readChangeReviews(asset,request.signal,{before_id:before});if(request.signal.aborted)return;
      changes=[...changes,...page.captures.filter(row=>!changes.some(old=>old.id===row.id))];
      const next={...changeCursors};if(page.next)next[asset]=page.next;else delete next[asset];changeCursors=next;
      moreAvailable=hiddenFindings||Object.keys(captureCursors).length>0||Object.keys(next).length>0;
    }catch{if(!request.signal.aborted)historyProblem="이전 특이사항 검토를 읽지 못했습니다.";}
    finally{if(!request.signal.aborted)loadingMore=false;}
  }

  async function loadAssetReviews(assets: string[], request: AbortController): Promise<void> {
    const failed = (assetId: string) => {
      if (!request.signal.aborted && !failedAssets.includes(assetId))
        failedAssets = [...failedAssets, assetId];
    };
    const pages = await Promise.all(assets.map(async (assetId) => {
      const [outlooks, reviews, changed] = await Promise.all([
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
        readChangeReviews(assetId,request.signal).then(page=>{
          if(page.next){moreAvailable=true;changeCursors={...changeCursors,[assetId]:page.next};}
          return page.captures;
        }).catch(()=>{failed(assetId);return [];}),
      ]);
      return {outlooks, reviews, changed};
    }));
    if (request.signal.aborted) return;
    const loaded = pages.flatMap((page) => page.outlooks);
    // Direct capture links are exact, even if the capture precedes the first page.
    if (focusCaptureId && !focusCaptureId.startsWith("change-review-") && focusAssetId && !loaded.some((item) =>
      item.id === focusCaptureId && item.outlook.assetId === focusAssetId)) {
      try {
        loaded.push(...(await readCaptures(focusAssetId, {captureId: focusCaptureId}, request.signal)).captures);
      } catch (cause: unknown) {
        if (!request.signal.aborted && cause instanceof CaptureNotFound) missingFocus = true;
        else failed(focusAssetId);
      }
    }
    if (request.signal.aborted) return;
    const loadedChanges=pages.flatMap(page=>page.changed);
    if(focusCaptureId?.startsWith("change-review-")&&focusAssetId&&!loadedChanges.some(row=>row.id===focusCaptureId)){
      try{loadedChanges.push(...(await readChangeReviews(focusAssetId,request.signal,{capture_id:focusCaptureId})).captures);}
      catch{failed(focusAssetId);}
    }
    if(request.signal.aborted)return;
    changes=[...changes,...loadedChanges.filter(row=>!changes.some(old=>old.id===row.id))];
    // Exact bookmarks bypass the recent 100-finding list, just like captures.
    const foundReviews = pages.flatMap((page) => page.reviews);
    if (focusFindingId && focusAssetId && !foundReviews.some((item) => item.findingId === focusFindingId)) {
      try {
        const exact = await readFindingReview(focusAssetId, focusFindingId, request.signal);
        if (exact) foundReviews.push(exact);
        else missingFocus = true;
      } catch {
        failed(focusAssetId);
      }
    }
    if (request.signal.aborted) return;
    captures = [...captures, ...loaded.filter((item) => !captures.some((prior) => prior.id === item.id))];
    findings = [...findings, ...foundReviews.filter((item) =>
      !findings.some((prior) => prior.findingId === item.findingId))];
    loadedAssets += assets.length;
    if (focusFindingId && !failedAssets.includes(focusAssetId)
      && !findings.some((item) => item.findingId === focusFindingId)) missingFocus = true;
  }

  async function loadMoreAssets() {
    const before = nextAsset;
    if (!before || loadingAssets || !scopeRequest) return;
    loadingAssets = true; assetIndexProblem = false;
    try {
      const page = await readReviewAssetIndex(scopeRequest.signal, before);
      if (scopeRequest.signal.aborted) return;
      if (page.revision !== assetIndexRevision) {
        // A newly inserted record before this cursor could otherwise be missed.
        assetIndexChanged = true;
        partialAssetScope = true;
        nextAsset = null;
        return;
      }
      nextAsset = page.nextAfter;
      partialAssetScope = nextAsset !== null;
      await loadAssetReviews(page.assets, scopeRequest);
    } catch {
      if (!scopeRequest.signal.aborted) assetIndexProblem = true;
    } finally {
      loadingAssets = false;
    }
  }

  onMount(() => {
    const request = new AbortController(); scopeRequest = request;
    void (async () => {
      let assets: string[];
      if (focusAssetId) {
        assets = [focusAssetId]; // Exact-owner direct links never scan unrelated assets.
      } else {
        try {
          const page = await readReviewAssetIndex(request.signal);
          if (request.signal.aborted) return;
          assets = page.assets;
          assetIndexRevision = page.revision;
          nextAsset = page.nextAfter;
          partialAssetScope = nextAsset !== null;
        } catch {
          if (request.signal.aborted) return;
          // The server's review index is the only complete list; a failure is said, not
          // replaced by a partial list from elsewhere. An exact asset ID still opens directly.
          assetIndexProblem = true;
          assets = [];
        }
      }
      if ((focusCaptureId || focusFindingId) && !focusAssetId) missingFocus = true;
      await loadAssetReviews(assets, request);
      if (!request.signal.aborted) loadState = "ready";
    })().catch(() => {
      if (!request.signal.aborted) { assetIndexProblem = true; loadState = "ready"; }
    });
    return () => { request.abort(); olderRequest?.abort(); };
  });
</script>

<div class="queue-layout">
  <section class="ui-panel queue" aria-labelledby="queue-title">
    <h2 id="queue-title">검토함</h2>
    {#if snapshot === null || partialAssetScope || assetIndexProblem || assetIndexChanged}
      {#if assetIndexChanged}
        <StatusNotice kind="uncertain" message="검토 대상을 불러오는 사이 목록이 바뀌었습니다. 다시 불러와 전체 목록을 확인하세요."
          actionLabel="다시 불러오기" onAction={() => location.reload()} />
      {:else if assetIndexProblem}
        <StatusNotice kind="failure" title="검토 대상 목록을 불러오지 못했습니다"
          message="검토 다시 불러오거나 아래에 설비 ID를 넣어 그 설비의 검토를 직접 여세요."
          actionLabel="다시 불러오기" onAction={() => location.reload()} />
      {:else if partialAssetScope}
        <StatusNotice kind="uncertain" message="검토 대상 설비를 일부만 불러왔습니다. 계속 불러오거나 설비 ID로 직접 조회할 수 있습니다." />
      {:else if snapshot === null}
        <p class="context">관측 요약과 독립적으로 저장 검토 기록을 조회합니다.</p>
      {/if}
      <form onsubmit={openAssetScope} class="scope-form">
        <label for="review-scope">검토할 설비 ID</label>
        <input id="review-scope" value={scopeAssetId} oninput={(event) => scopeAssetId = event.currentTarget.value} maxlength="128" required placeholder="설비 ID 입력" />
        <button class="ui-button ui-button-primary" type="submit" disabled={!scopeAssetId.trim()}>이 설비의 검토 열기</button>
      </form>
    {/if}
    <div class="filters" role="group" aria-label="판단">
      {#each [...REVIEW_GROUPS.map((group) => [group, GROUP_LABEL[group] + " " + countText(counts[group])]), ["all", "전체"]] as [value, label] (value)}
        <button type="button" class="chip" aria-pressed={activeFilter === value}
          onclick={() => { groupFilter = value as ReviewGroup | "all"; keptKey = null; ignoreFocus = true; }}>{label}</button>
      {/each}
    </div>
    <label class="type">종류
      <select value={typeFilter} onchange={(event) => { typeFilter = event.currentTarget.value as typeof typeFilter; keptKey = null; ignoreFocus = true; }}>
        <option value="all">전체</option><option value="analysis">분석 결과</option><option value="change">특이사항</option><option value="outlook">전망</option>
      </select>
    </label>
    {#if loadState === "loading"}
      <StatusNotice message="검토 목록을 불러오고 있습니다." />
    {:else}
      {#if failedAssets.length}
        <StatusNotice kind="uncertain" message={"다음 설비의 검토 항목을 불러오지 못했습니다: " + failedAssets.join(", ") + "."}
          actionLabel="검토 목록 다시 읽기" onAction={() => location.reload()} />
      {/if}
      {#if partialCounts}
        <p class="context">{focusAssetId ? "선택한 설비 1곳" : "설비 " + loadedAssets + "곳"}의 검토 기록을 불러왔습니다.
          {#if partialAssetScope || hiddenFindings || moreAvailable}
            전체 검토 건수는 아닙니다. 설비당 분석 검토는 최근 최대 100건이며, 전망과 특이사항은 한 번에 20건씩 읽습니다.
          {:else} 일부 조회가 실패해 실제 건수보다 적을 수 있습니다.
          {/if}
        </p>
      {/if}
      {#if nextAsset}
        <button type="button" class="ui-button" disabled={loadingAssets} onclick={loadMoreAssets}>
          {loadingAssets ? "다음 설비의 검토를 읽고 있습니다." : "다음 설비의 검토 더 보기"}
        </button>
      {/if}
      {#if hiddenFindings}<StatusNotice kind="uncertain" message="일부 분석 검토 기록은 조회 범위 밖에 있습니다. 목록에서 찾지 못했다고 저장 기록이 없는 것은 아닙니다." />{/if}
      {#if shown.length}
        <ul class="items">
          {#each shown as item (item.key)}
            <li><a href={item.href} aria-current={selected?.key === item.key ? "true" : undefined}>
              <strong>{item.title}</strong>
              <span><b class:pending={verdict(item) === "판단 전"}>{verdict(item)}</b> · {item.label} · {clock(item.at)}</span>
              {#if memoOf(item)}<span class="memo" title={memoOf(item)}>메모 · {memoOf(item)}</span>{/if}
            </a></li>
          {/each}
        </ul>
      {:else if items.length || snapshot === null || assetIndexProblem || failedAssets.length || hiddenFindings || partialAssetScope}
        <!-- 남긴 판단이 아직 없으면 오른쪽이 그 사실을 한 번 말한다(같은 말을 두 칸에 두지 않는다). -->
        <p class="context">{snapshot === null && !focusAssetId ? "위에서 검토할 설비 ID를 입력하세요. 전체 설비 목록을 조회하지 못한 상태입니다." : assetIndexProblem || failedAssets.length || hiddenFindings || partialAssetScope ? "현재 확인된 범위에서 조건에 맞는 검토 항목이 없습니다. 전체 기록의 검토가 완료됐다는 뜻은 아닙니다." : "이 조건에 맞는 검토 항목이 없습니다."}</p>
      {/if}
      {#if Object.keys(captureCursors).length}
        <button type="button" class="ui-button" disabled={loadingMore} onclick={() => void loadOlderCaptures()}>
          {loadingMore ? "이전 전망 불러오는 중" : "이전 전망 더 보기"}
        </button>
      {/if}
      {#if Object.keys(changeCursors).length}<button type="button" class="ui-button" disabled={loadingMore} onclick={()=>void loadOlderChanges()}>{loadingMore?"이전 특이사항 불러오는 중":"이전 특이사항 더 보기"}</button>{/if}
      {#if historyProblem}<StatusNotice kind="uncertain" message={historyProblem} actionLabel="다시 불러오기" onAction={() => void(historyKind==="change"?loadOlderChanges():loadOlderCaptures())} />{/if}
    {/if}
  </section>

  <section class="ui-panel detail-panel" aria-label="고른 검토 항목">
    {#if loadState === "loading"}
      <StatusNotice message="검토 항목을 불러오고 있습니다." />
    {:else if missingFocus && !ignoreFocus}
      <StatusNotice kind="uncertain" title="검토 항목을 찾을 수 없습니다"
        message="이 설비에서 해당 검토 항목을 찾을 수 없습니다." />
    {:else if !selected && (focusCaptureId || focusFindingId) && !ignoreFocus
      && failedAssets.includes(focusAssetId)}
      <StatusNotice kind="uncertain" title="요청한 검토 기록을 확인하지 못했습니다"
        message="이 설비의 조회에 실패했습니다. 기록이 없다고 판단하지 않습니다."
        actionLabel="다시 불러오기" onAction={() => location.reload()} />
    {:else if !selected}
      <!-- 아무것도 없을 때는 판단이 어디서 모이는지, 고른 칸만 비었을 때는 그 칸이 비었다는 것을 말한다. -->
      <p class="context">{items.length ? "이 칸에는 검토 항목이 없습니다." : "아직 남긴 판단이 없습니다. 특이사항을 조사하고 판단을 남기면 여기에 모입니다."}</p>
    {:else if selected.kind === "change"}
      {#key selected.change.id}<ChangeCaptureDetail assetId={selected.assetId} capture={selected.change}
        onUpdated={updated=>{changes=changes.map(row=>row.id===updated.id?updated:row);keptKey="capture:"+updated.id;keepVisible(reviewGroup(updated.review.status,latestDecision(updated.review.events)));}}/>{/key}
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
  .items span b { color: var(--color-ink); font-weight: 650; }
  .items span b.pending { color: var(--color-ink-muted); font-weight: 500; }
  .items .memo { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .context { color: var(--color-ink-muted); overflow-wrap: anywhere; }
</style>
