<script lang="ts">
  import { onMount, tick } from "svelte";
  import { assetLabel, readMonitor, type Asset, type Snapshot } from "./monitor";
  import { readWriteSession, sampleReturn } from "./session";
  import {loadModelBindings} from "./model-evidence";
  import { PRIMARY_PAGES, PAGE_INFO, TAB_INFO, assetUrl, parseRoute, reviewFocus, routeUrl, systemSection, systemUrl, type Route } from "./routes";
  import AssetList from "./components/AssetList.svelte";
  import MonitorAttention from "./components/MonitorAttention.svelte";
  import { readAttention, type AttentionState } from "./monitor-attention";
  import AssetWorkspace from "./components/AssetWorkspace.svelte";
  import PageHeading from "./components/PageHeading.svelte";
  import StatusNotice from "./components/StatusNotice.svelte";
  import ReviewQueue from "./components/ReviewQueue.svelte";
  import InvestigationRecords from "./components/InvestigationRecords.svelte";
  import OperationsPage from "./components/OperationsPage.svelte";
  import Guide from "./showcase/Guide.svelte";
  import BearingGuide from "./components/BearingGuide.svelte";
  import type {DemoJourney} from "./demo-journey";
  const showcase = import.meta.env.MODE === "showcase";

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
  let example = $state(false);
  let journey: DemoJourney | null = $state(null);
  let notes: Record<string, number> = $state({});
  let notesState: AttentionState = $state("loading");
  // The asset list counts the same items as 관측 현황, read once when the list is shown.
  let listNotes: Record<string, number> = $state({});
  let listNotesState: AttentionState = $state("loading");
  let listNotesRevision = $state(0);
  $effect(() => {
    listNotesRevision;
    if (route.page !== "assets" || route.assetId) return;
    const request = new AbortController();
    listNotes = {}; listNotesState = "loading";
    void readAttention(request.signal).then((read) => {
      if (!request.signal.aborted) {listNotes = read.counts; listNotesState = read.state;}
    }).catch(() => {if (!request.signal.aborted) {listNotes = {}; listNotesState = "failed";}});
    return () => request.abort();
  });
  const returnTo = sampleReturn(location.search);
  let controller: AbortController | null = null;
  let quietController: AbortController | null = null;
  let snapshotRead = 0;
  const selected: Asset | undefined = $derived.by(
    () => snapshot?.assets.find((asset: Asset) => asset.assetId === route.assetId));
  const documentTitle = $derived.by(() =>
    route.page === "assets" && route.assetId
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
    if (returnTo) destination.searchParams.set("return_to", returnTo);
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
      // A link to a part of the new page (e.g. #sample) scrolls there; focus still starts at main.
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
  function pageHref(page: Route["page"]): string {
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
      example = session.example;
      journey = session.journey;
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
        <a href={pageHref(page)} aria-current={route.page === page ? "page" : undefined}>
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
  {#if showcase}<Guide search={new URLSearchParams({page:route.page,tab:route.tab,asset:route.assetId,method:route.method??""}).toString()} />{/if}
  {#if example && !showcase && !journey}
    <p class="example">합성 예시 데이터 · 별도 작업공간 · {writable ? "변경 내용은 예시에만 저장" : "보기 전용"}{#if returnTo}{" · "}<a href={returnTo}>내 작업공간으로 돌아가기</a>{/if}</p>
  {/if}
  {#if journey && !showcase}<BearingGuide {journey} {returnTo} writable={writable===true} search={new URLSearchParams({page:route.page,tab:route.tab,method:route.method??"",monitor_asset:route.assetId,...(new URLSearchParams(location.search).get("demo_step")==="review"?{demo_step:"review"}:{})}).toString()} />{/if}
  {#if quietError && (loadState === "ready" || loadState === "empty")}
    <StatusNotice kind="uncertain" title="설비 목록 갱신 실패"
      message={"이전 조회 시점의 목록만 표시합니다. 새로운 데이터를 확인하지 못했습니다. " + quietError}
      actionLabel="다시 시도" onAction={() => void quietRefresh()} />
  {/if}
  {#if route.page === "system"}
    <PageHeading title={PAGE_INFO.system.label} description={PAGE_INFO.system.description}
      loading={loadState === "loading"} onRefresh={() => void refresh()} />
    <OperationsPage {snapshot} storeState={loadState} storeError={error} writable={writable === true} {section} {example} {returnTo} onChanged={quietRefresh} />
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
    {#if route.page === "assets" && selected}
      {#key selected.assetId}
        <AssetWorkspace asset={selected} assets={snapshot.assets} {route} {observed}
          onSelectAsset={selectAsset} />
      {/key}
    {:else}
      <PageHeading title={PAGE_INFO[route.page].label} description={PAGE_INFO[route.page].description}
        loading={false} onRefresh={() => void refresh()} />
      <p class="meta">{observed(snapshot.assessedAt)} 기준</p>
      {#if snapshot.systemReadUncertain}
        <StatusNotice kind="uncertain" message="일부 저장소나 수집 상태를 확인하지 못했습니다. 보이는 내용이 전부가 아닐 수 있습니다." />
      {/if}
      {#if snapshot.truncated}
        <StatusNotice kind="uncertain" message="설비가 많아 일부만 표시합니다." />
      {/if}
      {#if (route.page === "monitor" || route.page === "assets") && loadState === "empty"}
        <!-- A first visit starts with how to get data in, not with panels about data that is not there. -->
        <section class="ui-panel start" aria-labelledby="start-title">
          <h2 id="start-title">{snapshot.systemReadUncertain ? "표시할 설비가 없습니다" : "아직 연결된 데이터가 없습니다"}</h2>
          <p>준비된 베어링 진동 기록과 두 모델로 변화 조사부터 검토 기록까지 따라가 보세요.
            직접 분석할 데이터는 CSV 파일로 연결합니다.</p>
          <div class="start-actions">
            <a class="ui-button ui-button-primary" href={systemUrl("connections") + "#sample"}>분석 체험하기</a>
            <a class="ui-link-primary" href={systemUrl("connections")}>CSV 파일로 시작</a>
          </div>
        </section>
      {/if}
      {#if route.page === "monitor" && (loadState !== "empty" || snapshot.operationsAttention?.items.length)}<MonitorAttention {snapshot} onTick={quietRefresh} onNotes={(counts,state) => {notes = counts; notesState = state;}} />{/if}
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
        {#if route.page === "assets" && route.assetId}
          <StatusNotice kind="uncertain" title="선택한 설비가 이번 목록에 없습니다"
            message="목록이 일부만 조회됐거나 데이터가 바뀌었을 수 있습니다. 다른 설비의 결과로 대신 보여 주지 않습니다." />
        {/if}

        {#if route.page === "assets" && (listNotesState === "partial" || listNotesState === "failed")}
          <StatusNotice kind="uncertain" message="확인 항목을 일부 읽지 못했습니다. 표시된 건수는 확인된 항목만 포함합니다."
            actionLabel="확인 항목 다시 읽기" onAction={() => listNotesRevision++} />
        {/if}
        <AssetList assets={snapshot.assets} {observed} href={assetHref} notes={route.page === "monitor" ? notes : listNotes}
          notesState={route.page === "monitor" ? notesState : listNotesState}
          reasons={route.page === "monitor"} />
      {/if}
    {/if}
  {/if}
</main>
