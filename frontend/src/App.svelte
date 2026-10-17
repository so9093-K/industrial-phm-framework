<script lang="ts">
  import { onMount, tick } from "svelte";
  import { readMonitor, type Asset, type Snapshot } from "./monitor";
  import { readPermission } from "./outlook-briefings";
  import { PAGES, PAGE_INFO, TAB_INFO, assetUrl, canonicalUrl, parseRoute, reviewFocus, routeUrl, systemSection, systemUrl, type Route } from "./routes";
  import AssetList from "./components/AssetList.svelte";
  import AssetWorkspace from "./components/AssetWorkspace.svelte";
  import PageHeading from "./components/PageHeading.svelte";
  import StatusNotice from "./components/StatusNotice.svelte";
  import ReviewQueue from "./components/ReviewQueue.svelte";
  import InvestigationRecords from "./components/InvestigationRecords.svelte";
  import OperationsPage from "./components/OperationsPage.svelte";

  type LoadState = "loading" | "ready" | "empty" | "failed";
  if (parseRoute(location.search).legacy) {
    history.replaceState(history.state, "", canonicalUrl(location.search));
  }
  let route: Route = $state(parseRoute(location.search).route);
  let focus = $state(reviewFocus(location.search));
  let section = $state(systemSection(location.search));
  let loadState: LoadState = $state("loading");
  let error = $state("");
  let snapshot: Snapshot | null = $state(null);
  let writable: boolean | null = $state(null);
  let controller: AbortController | null = null;
  const selected: Asset | undefined = $derived.by(
    () => snapshot?.assets.find((asset: Asset) => asset.assetId === route.assetId));
  const documentTitle = $derived(
    route.page === "assets" && route.assetId
      ? TAB_INFO[route.tab] + " · " + route.assetId + " · Industrial PHM"
      : PAGE_INFO[route.page].label + " · Industrial PHM");

  async function navigate(url: string) {
    const before = route;
    history.pushState(history.state, "", url);
    route = parseRoute(location.search).route;
    focus = reviewFocus(location.search);
    section = systemSection(location.search);
    // A new page moves focus to its content. A tab switch, or choosing another asset with
    // the keyboard in its select, keeps focus where the user is.
    if (before.page !== route.page) {
      await tick();
      document.getElementById("main")?.focus();
    }
  }
  function selectAsset(assetId: string) {
    if (assetId !== route.assetId) void navigate(assetUrl(location.href, assetId));
  }
  function assetHref(assetId: string): string {
    return routeUrl({page: "assets", assetId, tab: "summary", method: null, data: null});
  }
  function pageHref(page: Route["page"]): string {
    return routeUrl({page, assetId: page === "assets" ? route.assetId : "", tab: "summary", method: null, data: null});
  }

  async function refresh() {
    controller?.abort();
    const pending = new AbortController();
    controller = pending;
    loadState = "loading";
    error = "";
    snapshot = null;
    try {
      const result = await readMonitor(pending.signal);
      if (pending.signal.aborted) return;
      snapshot = result;
      loadState = result.assets.length ? "ready" : "empty";
    } catch (cause: unknown) {
      if (pending.signal.aborted) return;
      error = cause instanceof Error ? cause.message : "관측 정보를 읽지 못했습니다.";
      loadState = "failed";
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
    const restore = () => {
      route = parseRoute(location.search).route; focus = reviewFocus(location.search); section = systemSection(location.search);
    };
    // Same-document links switch screens without reloading the asset list.
    const follow = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey
        || event.shiftKey || event.altKey) return;
      const link = (event.target as Element | null)?.closest?.("a");
      if (!link || link.target || link.hasAttribute("download")) return;
      const url = new URL(link.href, location.href);
      if (url.origin !== location.origin || url.pathname !== "/web-next/") return;
      event.preventDefault();
      if (url.pathname + url.search !== location.pathname + location.search) void navigate(url.pathname + url.search);
    };
    const permission = new AbortController();
    void readPermission(permission.signal).then((allowed) => {
      if (!permission.signal.aborted) writable = allowed;
    }).catch(() => {});
    window.addEventListener("popstate", restore);
    document.addEventListener("click", follow);
    void refresh();
    return () => {
      controller?.abort();
      permission.abort();
      window.removeEventListener("popstate", restore);
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
    <a class="brand" href="/web-next/">Industrial PHM</a>
    <nav class="topnav" aria-label="업무 메뉴">
      {#each PAGES as page (page)}
        <a href={pageHref(page)} aria-current={route.page === page ? "page" : undefined}>
          {PAGE_INFO[page].label}
        </a>
      {/each}
    </nav>
    <div class="topbar-side">
      {#if writable === true}<span class="mode">운영 중 · 기록 가능</span>
      {:else if writable === false}<span class="mode">보기 전용</span>{/if}
      <a class="legacy" href="/web/">이전 화면</a>
    </div>
  </div>
</header>

<main id="main" tabindex="-1">
  {#if route.page === "system"}
    <PageHeading title={PAGE_INFO.system.label} description={PAGE_INFO.system.description}
      loading={loadState === "loading"} onRefresh={() => void refresh()} />
    <OperationsPage {snapshot} storeState={loadState} storeError={error} writable={writable === true} {section} />
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
      {#if route.page === "maintenance"}
        <ReviewQueue {snapshot} writable={writable === true} focusAssetId={route.assetId}
          focusCaptureId={focus.captureId} focusFindingId={focus.findingId} />
      {:else if route.page === "investigations"}
        <InvestigationRecords {snapshot} writable={writable === true} assetId={route.assetId} />

      {:else if loadState === "empty"}
        <StatusNotice
          title="등록된 설비가 없습니다"
          message="아직 연결된 데이터가 없거나 일부 저장소를 읽지 못했을 수 있습니다."
          actionLabel="데이터 연결하기"
          actionHref={systemUrl("connections")}
        />
      {:else}
        {#if route.page === "assets" && route.assetId}
          <StatusNotice kind="uncertain" title="선택한 설비가 이번 목록에 없습니다"
            message="목록이 일부만 조회됐거나 데이터가 바뀌었을 수 있습니다. 다른 설비의 결과로 대신 보여 주지 않습니다." />
        {/if}
        <AssetList assets={snapshot.assets} {observed} href={assetHref} />
      {/if}
    {/if}
  {/if}
</main>
