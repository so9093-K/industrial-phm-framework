<script lang="ts">
  import { onMount, tick } from "svelte";
  import { assetLabel, readMonitor, type Asset, type Snapshot } from "./monitor";
  import { readWriteSession } from "./session";
  import {loadModelBindings} from "./model-evidence";
  import { PRIMARY_PAGES, PAGE_INFO, TAB_INFO, assetUrl, parseRoute, reviewFocus, routeUrl, systemSection, systemUrl, type Route } from "./routes";
  import AssetList from "./components/AssetList.svelte";
  import MonitorAttention from "./components/MonitorAttention.svelte";
  import ReviewEntry from "./components/ReviewEntry.svelte";
  import { UNCHECKED, type AssetChecks } from "./monitor-attention";
  import { readPublicDatasets } from "./public-datasets";
  import AssetWorkspace from "./components/AssetWorkspace.svelte";
  import PageHeading from "./components/PageHeading.svelte";
  import AnalysisGuide from "./components/AnalysisGuide.svelte";
  import StatusNotice from "./components/StatusNotice.svelte";
  import ReviewQueue from "./components/ReviewQueue.svelte";
  import InvestigationRecords from "./components/InvestigationRecords.svelte";
  import OperationsPage from "./components/OperationsPage.svelte";
  type LoadState = "loading" | "ready" | "empty" | "failed";
  let route: Route = $state(parseRoute(location.search));
  let focus = $state(reviewFocus(location.search));
  let section = $state(systemSection(location.search));
  let loadState: LoadState = $state("loading");
  let error = $state("");
  let quietError = $state("");
  let snapshot: Snapshot | null = $state(null);
  let writable: boolean | null = $state(null);
  let permissionState: "checking" | "ready" | "failed" = $state("checking");
  let permissionController: AbortController | null = null;
  // 관측 현황은 확인 사실을 계속 다시 읽고(MonitorAttention), 설비·신호 목록은 열 때 한 번 읽는다.
  let checks: AssetChecks = $state(UNCHECKED);
  // 모니터링 화면(설비 칸 줄 + 고른 설비의 중심 화면). 설비를 고르지 않았으면 첫 설비를 열고 주소에 남긴다.
  const monitoring = $derived(route.page === "monitor" || route.page === "assets");
  function monitorHref(assetId: string): string {
    return routeUrl({page: "monitor", assetId, tab: "summary", method: null, data: null});
  }
  $effect(() => {
    const first = snapshot?.assets[0]?.assetId;
    if (!monitoring || route.assetId || !first) return;
    const url = new URL(location.href);
    url.searchParams.set("monitor_asset", first);
    history.replaceState(history.state, "", url);
    route = parseRoute(location.search);
  });
  // An empty workspace offers the public datasets prepared in the data folder, when there are any.
  let publicCount = $state(0);
  $effect(() => {
    if (loadState !== "empty") return;
    const request = new AbortController();
    void readPublicDatasets(request.signal).then((found) => {
      if (!request.signal.aborted) publicCount = found.items.length;
    }).catch(() => {});
    return () => request.abort();
  });
  let controller: AbortController | null = null;
  let quietController: AbortController | null = null;
  let snapshotRead = 0;
  const selected: Asset | undefined = $derived.by(
    () => snapshot?.assets.find((asset: Asset) => asset.assetId === route.assetId));
  const documentTitle = $derived.by(() =>
    (route.page === "assets" || route.page === "monitor") && route.assetId
      ? TAB_INFO[route.tab] + " · " + assetLabel(snapshot?.assets ?? [], route.assetId) + " · Industrial PHM"
      : PAGE_INFO[route.page].label + " · Industrial PHM");

  let topnav: HTMLElement | null = $state(null);
  // The menu row scrolls on a phone; keep the current page's entry in view.
  $effect(() => {
    route.page;
    topnav?.querySelector<HTMLElement>('[aria-current="page"]')?.scrollIntoView({block: "nearest", inline: "nearest"});
  });

  async function navigate(url: string) {
    const before = route;
    const destination = new URL(url, location.href);
    history.pushState(history.state, "", destination.pathname + destination.search + destination.hash);
    route = parseRoute(location.search);
    focus = reviewFocus(location.search);
    section = systemSection(location.search);
    // A save on another page (e.g. a CSV just stored) may not have reached this list yet;
    // a page change or an asset the list does not know reads it again.
    if (before.page !== route.page || (route.assetId && !snapshot?.assets.some((item) => item.assetId === route.assetId)))
      void quietRefresh();
    // A new page moves focus to its content. Asset changes restore the select
    // after its keyed workspace is replaced, instead of leaving focus on the body.
    if (before.page !== route.page) {
      await tick();
      // Hash navigation on the current page keeps native scrolling; focus still starts at main.
      const part = location.hash ? document.getElementById(location.hash.slice(1)) : null;
      document.getElementById("main")?.focus({preventScroll: part !== null});
      part?.scrollIntoView({block: "start"});
    }
  }
  async function selectAsset(assetId: string) {
    if (assetId === route.assetId) return;
    await navigate(assetUrl(location.href, assetId));
    await tick();
    document.querySelector<HTMLSelectElement>("[data-asset-switch]")?.focus();
  }
  function assetHref(assetId: string): string {
    return routeUrl({page: "assets", assetId, tab: "summary", method: null, data: null});
  }
  // 모니터링으로 돌아오면 마지막에 보던 설비·변화 그대로 연다.
  let lastMonitorUrl = $state("");
  $effect(() => {
    route;
    if (route.page === "monitor" || route.page === "assets") lastMonitorUrl = location.pathname + location.search;
  });
  function pageHref(page: Route["page"]): string {
    if (page === "monitor" && lastMonitorUrl) return lastMonitorUrl;
    return routeUrl({page, assetId: page === "assets" ? route.assetId : "", tab: "summary", method: null, data: null});
  }

  async function refresh() {
    const read = ++snapshotRead;
    controller?.abort();
    quietController?.abort();
    const pending = new AbortController();
    controller = pending;
    loadState = "loading";
    error = "";
    quietError = "";
    snapshot = null;
    try {
      const requested=new URLSearchParams(location.search).get("model_binding");
      if(route.page==="assets"&&!route.assetId&&requested){
        const bindings=await loadModelBindings(null,pending.signal);
        if(pending.signal.aborted)return;
        const matched=bindings.find(binding=>binding.bindingId===requested);
        if(!matched)throw new Error("북마크의 적용 모델을 찾을 수 없습니다. 다른 설비로 대신하지 않습니다.");
        route={...route,assetId:matched.assetId};
        const url=new URL(location.href);url.searchParams.set("monitor_asset",matched.assetId);
        history.replaceState(history.state,"",url);
      }
      const result = await readMonitor(pending.signal);
      if (pending.signal.aborted || read !== snapshotRead) return;
      snapshot = result;
      loadState = result.assets.length ? "ready" : "empty";
    } catch (cause: unknown) {
      if (pending.signal.aborted) return;
      error = cause instanceof Error ? cause.message : "관측 정보를 읽지 못했습니다.";
      loadState = "failed";
    }
  }

  /** Retain last verified facts, but never present a failed background read as current.
   * The generation and abort guard prevent a late response from replacing newer facts. */
  async function quietRefresh() {
    if (loadState !== "ready" && loadState !== "empty") return;
    const read = ++snapshotRead;
    quietController?.abort();
    const pending = new AbortController();
    quietController = pending;
    try {
      const result = await readMonitor(pending.signal);
      if (pending.signal.aborted || read !== snapshotRead) return;
      if (loadState === "ready" || loadState === "empty") {
        snapshot = result;
        loadState = result.assets.length ? "ready" : "empty";
        quietError = "";
      }
    } catch (cause: unknown) {
      if (pending.signal.aborted || read !== snapshotRead) return;
      quietError = cause instanceof Error ? cause.message : "설비 목록을 다시 읽지 못했습니다.";
    }
  }

  async function checkPermission() {
    permissionController?.abort();
    const pending = new AbortController();
    permissionController = pending;
    writable = null;
    permissionState = "checking";
    try {
      const session = await readWriteSession(pending.signal);
      if (pending.signal.aborted) return;
      writable = session.writable;
      permissionState = "ready";
    } catch {
      if (pending.signal.aborted) return;
      // A failed capability read never becomes a writable session.
      writable = null;
      permissionState = "failed";
    }
  }

  function observed(at: string | null): string {
    if (!at) return "기록 없음";
    const date = new Date(at);
    return Number.isNaN(date.getTime())
      ? "시각 해석 불가"
      : date.toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
  }

  onMount(() => {
    const restore = async () => {
      const before = route;
      route = parseRoute(location.search); focus = reviewFocus(location.search); section = systemSection(location.search);
      if (before.page !== route.page || (route.assetId && !snapshot?.assets.some((item) => item.assetId === route.assetId)))
        void quietRefresh();
      // History navigation can replace the focused node without going through
      // navigate(). Restore focus to the new content or to the new asset picker.
      const nextPage = route.page, nextAsset = route.assetId;
      if (before.page !== nextPage || (nextPage === "assets" && before.assetId !== nextAsset)) {
        await tick();
        if (route.page !== nextPage || route.assetId !== nextAsset) return;
        if (before.page !== nextPage) document.getElementById("main")?.focus();
        else document.querySelector<HTMLSelectElement>("[data-asset-switch]")?.focus();
      }
    };
    // Same-document links switch screens without reloading the asset list.
    const follow = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey
        || event.shiftKey || event.altKey) return;
      const link = (event.target as Element | null)?.closest?.("a");
      if (!link || link.target || link.hasAttribute("download")) return;
      const url = new URL(link.href, location.href);
      if (url.origin !== location.origin || url.pathname !== "/web/") return;
      if (url.hash && url.pathname + url.search === location.pathname + location.search) return;
      event.preventDefault();
      if (url.pathname + url.search !== location.pathname + location.search) void navigate(url.pathname + url.search + url.hash);
    };
    void checkPermission();
    window.addEventListener("popstate", restore);
    window.addEventListener("hashchange", restore);
    document.addEventListener("click", follow);
    void refresh();
    return () => {
      controller?.abort();
      quietController?.abort();
      permissionController?.abort();
      window.removeEventListener("popstate", restore);
      window.removeEventListener("hashchange", restore);
      document.removeEventListener("click", follow);
    };
  });
</script>

<svelte:head>
  <title>{documentTitle}</title>
</svelte:head>

<a class="skip" href="#main">본문으로 건너뛰기</a>
<header class="topbar">
  <div class="topbar-inner">
    <a class="brand" href="/web/">Industrial PHM</a>
    <nav class="topnav" aria-label="업무 메뉴" bind:this={topnav}>
      {#each PRIMARY_PAGES as page (page)}
        <a href={pageHref(page)} aria-current={route.page === page || (page === "monitor" && route.page === "assets") ? "page" : undefined}>
          {PAGE_INFO[page].label}
        </a>
      {/each}
    </nav>
    <div class="topbar-side">
      {#if permissionState === "checking"}
        <span class="mode" role="status">작업 권한 확인 중</span>
      {:else if permissionState === "failed"}
        <span class="mode" role="status">읽기 전용 · 권한 확인 실패</span>
        <button type="button" class="ui-button" onclick={() => void checkPermission()}>권한 다시 확인</button>
      {:else if writable === true}
        <span class="mode" role="status">변경 가능</span>
      {:else}
        <span class="mode" role="status">보기 전용</span>
      {/if}
    </div>
  </div>
</header>

<main id="main" tabindex="-1">
  {#if quietError && (loadState === "ready" || loadState === "empty")}
    <StatusNotice kind="uncertain" title="설비 목록 갱신 실패"
      message={"이전 조회 시점의 목록만 표시합니다. 새로운 데이터를 확인하지 못했습니다. " + quietError}
      actionLabel="다시 시도" onAction={() => void quietRefresh()} />
  {/if}
  {#if route.page === "system"}
    <PageHeading title={PAGE_INFO.system.label} description={PAGE_INFO.system.description}
      loading={loadState === "loading"} onRefresh={() => void refresh()} />
    <OperationsPage {snapshot} storeState={loadState} storeError={error} writable={writable === true} {section} onChanged={quietRefresh} />
  {:else if loadState === "loading"}
    <StatusNotice message="설비 목록을 불러오고 있습니다." />
  {:else if loadState === "failed"}
    <StatusNotice
      title="설비 목록을 불러오지 못했습니다"
      message={error + " 데이터가 없다는 뜻은 아닙니다."}
      kind="failure"
      actionLabel="다시 시도"
      onAction={() => void refresh()}
    />
    {#if route.page === "maintenance"}
      <PageHeading title={PAGE_INFO.maintenance.label} description="관측 요약을 읽지 못했습니다. 설비 ID를 지정하면 해당 설비의 저장된 검토 기록을 별도로 조회할 수 있습니다."
        loading={false} onRefresh={() => void refresh()} />
      {#key route.assetId + "\n" + (focus.captureId ?? "") + "\n" + (focus.findingId ?? "")}
        <ReviewQueue snapshot={null} writable={writable === true} focusAssetId={route.assetId}
          focusCaptureId={focus.captureId} focusFindingId={focus.findingId} />
      {/key}
    {/if}
  {:else if snapshot}
    {#if monitoring && loadState !== "empty" && snapshot.assets.length}
      {#if snapshot.systemReadUncertain}
        <StatusNotice kind="uncertain" message="일부 저장소나 수집 상태를 확인하지 못했습니다. 보이는 내용이 전부가 아닐 수 있습니다." />
      {/if}
      {#if snapshot.truncated}<StatusNotice kind="uncertain" message="설비가 많아 일부만 표시합니다." />{/if}
      {#if checks.state === "partial" || checks.state === "failed"}
        <StatusNotice kind="uncertain" message={checks.state === "failed" ? "모델·수신 확인 항목을 읽지 못했습니다. 설비 칸의 모델 결과와 확인 항목이 빠져 있습니다."
          : "모델·수신 확인 항목을 일부만 읽었습니다. 설비 칸에는 읽은 항목만 있습니다."} />
      {/if}
      <AssetList assets={snapshot.assets} {observed} href={monitorHref} selected={selected?.assetId ?? ""} {checks}
        checkedAt={observed(snapshot.assessedAt)} />
      {#if selected}
        {#key selected.assetId}
          <AssetWorkspace asset={selected} assets={snapshot.assets} {route} {observed} onSelectAsset={selectAsset} />
        {/key}
      {:else if route.assetId}
        <StatusNotice kind="uncertain" title="선택한 설비가 이번 목록에 없습니다"
          message="목록이 일부만 조회됐거나 데이터가 바뀌었을 수 있습니다. 다른 설비의 결과로 대신 보여 주지 않습니다." />
      {/if}
      <div class="monitor-footer">
        <ReviewEntry compact/>
        <details id="operations" class="ui-panel monitor-operations"><summary>운영 확인 항목{snapshot.operationsAttention?.items.length?" · "+snapshot.operationsAttention.items.length+"건":" · 없음"}</summary>
          <MonitorAttention {snapshot} onTick={quietRefresh} onChecks={(read) => checks = read} />
        </details>
      </div>
    {:else}
      <PageHeading title={PAGE_INFO[route.page].label} description={PAGE_INFO[route.page].description}
        meta={route.page === "monitor" ? "목록 확인 시각 · " + observed(snapshot.assessedAt) : ""}
        compact={route.page==="monitor"}
        actionHref={route.page==="monitor"&&snapshot.assets.length?systemUrl("connections"):undefined}
        actionLabel="데이터 가져오기"
        loading={false} onRefresh={() => void refresh()} />
      {#if route.page !== "monitor"}<p class="meta">목록 확인 시각 · {observed(snapshot.assessedAt)}</p>{/if}
      {#if snapshot.systemReadUncertain}
        <StatusNotice kind="uncertain" message="일부 저장소나 수집 상태를 확인하지 못했습니다. 보이는 내용이 전부가 아닐 수 있습니다." />
      {/if}
      {#if snapshot.truncated}
        <StatusNotice kind="uncertain" message="설비가 많아 일부만 표시합니다." />
      {/if}
      {#if (route.page === "monitor" || route.page === "assets") && loadState === "empty"}
        <!-- A first visit starts with how to get data in, not with panels about data that is not there. -->
        <section class="ui-panel start" aria-labelledby="start-title">
          <h2 id="start-title">{snapshot.systemReadUncertain ? "표시할 설비가 없습니다" : "설비 데이터 분석을 시작하세요"}</h2>
          <p>{snapshot.systemReadUncertain ? "설비 목록을 확인하지 못했습니다. 데이터가 없다는 뜻은 아닙니다." : "아직 연결된 데이터가 없습니다."}
            측정 기록을 가져오면 주요 변화와 신호 추세를 살펴볼 수 있습니다.</p>
          <nav class="start-actions" aria-label="데이터로 시작하는 방법">
            <a class="start-choice primary" href={systemUrl("connections")} aria-labelledby="csv-entry" aria-describedby="csv-entry-note"><strong id="csv-entry">CSV 파일로 시작하기</strong><span id="csv-entry-note">과거 측정 기록을 저장하고 해당 설비의 분석을 시작합니다.</span></a>
            <a class="start-choice" href={systemUrl("connections")+"#opcua-connect"} aria-labelledby="opcua-entry" aria-describedby="opcua-entry-note"><strong id="opcua-entry">설비 데이터 수집 연결</strong><span id="opcua-entry-note">이 컴퓨터의 OPC UA 서버를 연결해 측정값을 받습니다.</span></a>
            <a class="start-choice" href={systemUrl("connections")+"#public-datasets"} aria-labelledby="public-entry" aria-describedby="public-entry-note"><strong id="public-entry">{publicCount?"공개 실측 데이터로 시작하기 ("+publicCount+"개)":"공개 실측 데이터 준비 방법"}</strong><span id="public-entry-note">공개된 설비 전력·베어링 진동 기록으로 분석을 살펴봅니다.</span></a>
          </nav>
          <details class="start-guide"><summary>가능한 분석과 필요한 데이터 보기</summary><AnalysisGuide /></details>
        </section>
      {/if}
      {#if route.page === "maintenance"}
        {#key route.assetId + "\n" + (focus.captureId ?? "") + "\n" + (focus.findingId ?? "")}
          <ReviewQueue {snapshot} writable={writable === true} focusAssetId={route.assetId}
            focusCaptureId={focus.captureId} focusFindingId={focus.findingId} />
        {/key}
      {:else if route.page === "investigations"}
        <InvestigationRecords {snapshot} writable={writable === true} assetId={route.assetId} />

      {:else if loadState === "empty"}
        <!-- Monitor and the asset list share the start panel above. -->
      {:else}
        <!-- 모니터링(설비 칸 줄 + 중심 화면)은 위에서 그린다. -->
      {/if}
      {#if monitoring && snapshot.operationsAttention?.items.length}
        <details id="operations" class="ui-panel monitor-operations"><summary>운영 확인 항목 · {snapshot.operationsAttention.items.length}건</summary>
          <MonitorAttention {snapshot} onTick={quietRefresh} onChecks={(read) => checks = read} />
        </details>
      {/if}
    {/if}
  {/if}
</main>

<style>
  .monitor-footer{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:start;gap:var(--space-2) var(--space-4);border-top:1px solid var(--color-border);margin-top:var(--space-4)}.monitor-footer:has(details[open]){display:grid}.monitor-footer :global(.review-entry){margin-block:var(--space-3)}
  .start-guide>summary { cursor:pointer; padding-block:var(--space-3); color:var(--color-action); font-weight:650; }
  .monitor-operations { padding:0; border:0; border-radius:0; background:transparent; }
  .monitor-operations>summary {
    cursor: pointer; padding-block: var(--space-3); font-size:var(--font-small); font-weight: 650; color: var(--color-action);
  }
</style>
