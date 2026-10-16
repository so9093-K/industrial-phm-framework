<script lang="ts">
  import { onMount } from "svelte";
  import { readMonitor, type Asset, type Snapshot } from "./monitor";
  import { VIEWS, VIEW_INFO, parseRoute, viewUrl, assetUrl, type View } from "./routes";
  import AssetSelector from "./components/AssetSelector.svelte";
  import ObservationDetails from "./components/ObservationDetails.svelte";
  import PageHeading from "./components/PageHeading.svelte";
  import StatusNotice from "./components/StatusNotice.svelte";
  import SignalExplorer from "./components/SignalExplorer.svelte";
  import DepartureExplorer from "./components/DepartureExplorer.svelte";
  import PeriodComparison from "./components/PeriodComparison.svelte";
  import ProjectionExplorer from "./components/ProjectionExplorer.svelte";
  import RelationExplorer from "./components/RelationExplorer.svelte";
  import ReviewInboxView from "./components/ReviewInbox.svelte";
  import AcquisitionSpectrum from "./components/AcquisitionSpectrum.svelte";
  import AcquisitionFeatureProfile from "./components/AcquisitionFeatureProfile.svelte";

  type LoadState = "loading" | "ready" | "empty" | "failed";
  let loadState: LoadState = $state("loading");
  let error = $state("");
  let snapshot: Snapshot | null = $state(null);
  let view: View = $state(parseRoute(location.search).view);
  let selectedId = $state(parseRoute(location.search).assetId);
  const viewInfo = $derived(VIEW_INFO[view]);
  let controller: AbortController | null = null;
  let selected: Asset | undefined = $derived.by(
    () => snapshot?.assets.find((asset: Asset) => asset.assetId === selectedId),
  );

  function selectAsset(assetId: string) {
    if (assetId === selectedId) return;
    const firstSelection = !selectedId;
    const url = assetUrl(location.href, assetId);
    selectedId = assetId;
    if (firstSelection) history.replaceState(history.state, "", url);
    else history.pushState(history.state, "", url);
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
      if (!selectedId && result.assets.length) selectAsset(result.assets[0].assetId);
    } catch (cause: unknown) {
      if (pending.signal.aborted) return;
      error = cause instanceof Error ? cause.message : "관측 정보를 읽지 못했습니다.";
      loadState = "failed";
    }
  }

  function observed(at: string | null): string {
    if (!at) return "마지막 관측 시각 없음";
    const date = new Date(at);
    return Number.isNaN(date.getTime())
      ? "관측 시각 해석 불가"
      : date.toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
  }

  function detailUrl(assetId: string): string {
    return "/web/?monitor_asset=" + encodeURIComponent(assetId) + "#signals";
  }

  function nextUrl(target: View): string {
    return viewUrl(target, selectedId, new URLSearchParams(location.search).get("monitor_channel"));
  }

  onMount(() => {
    const restore = () => {
      const route = parseRoute(location.search);
      view = route.view;
      selectedId = route.assetId;
    };
    window.addEventListener("popstate", restore);
    void refresh();
    return () => {
      controller?.abort();
      window.removeEventListener("popstate", restore);
    };
  });
</script>

<svelte:head>
  <title>Industrial PHM · {viewInfo.document} 구조 검증</title>
</svelte:head>

<a class="skip" href="#main">본문으로 건너뛰기</a>
<div class="shell">
  <aside class="sidebar" aria-label="검증 화면 정보">
    <div class="brand">Industrial PHM <small>Operations / UI 실험</small></div>
    <nav aria-label="화면 바로가기">
      <a href="/web/">현재 운영 화면</a>
      {#each VIEWS as target (target)}
        <a href={nextUrl(target)} aria-current={view === target ? "page" : undefined}>
          {VIEW_INFO[target].navigation}
        </a>
      {/each}
    </nav>
    <p class="note">독립 읽기 전용 화면입니다. 새 분석·판정 기능이 아닙니다.</p>
  </aside>
  <main id="main" tabindex="-1">
    <PageHeading
      eyebrow={viewInfo.eyebrow}
      title={viewInfo.title}
      description={viewInfo.description}
      loading={loadState === "loading"}
      onRefresh={() => void refresh()}
    />

    {#if loadState === "loading"}
      <StatusNotice message="저장된 관측을 확인하는 중입니다." />
    {:else if loadState === "failed"}
      <StatusNotice
        title="조회 결과를 확인할 수 없습니다"
        message={error + " 데이터 없음이나 설비 이상으로 판단하지 않습니다."}
        kind="failure"
        actionLabel="다시 시도"
        onAction={() => void refresh()}
      />
    {:else if snapshot}
      <p class="meta">조회 평가 시각: {observed(snapshot.assessedAt)} · API가 반환한 저장 이력 기준</p>
      {#if snapshot.systemReadUncertain}
        <StatusNotice kind="uncertain" message="일부 저장소·수집 근거를 확인하지 못했습니다. 조회 가능한 결과도 현재 상태를 보장하지 않습니다." />
      {/if}
      {#if snapshot.truncated}
        <StatusNotice kind="uncertain" message="설비 목록은 서버 조회 제한에 따라 일부만 표시됩니다." />
      {/if}
      {#if loadState === "empty"}
        <StatusNotice
          title="조회된 설비가 없습니다"
          message="데이터 미등록과 부분적인 읽기 실패는 서로 다른 상태입니다. 연결 상태에서 확인하세요."
          actionLabel="데이터 연결 화면 열기"
          actionHref="/web/#connect"
        />
      {:else}
        <div class="workspace">
          <AssetSelector assets={snapshot.assets} {selectedId} onSelect={selectAsset} {observed} />
          {#if !selected}
            <StatusNotice kind="uncertain" title="선택한 설비가 이번 조회에 없습니다"
              message="이 설비의 저장 근거를 확인할 수 없습니다. 서버의 제한된 목록 또는 데이터 변경 가능성이 있으며, 다른 설비의 결과로 대체하지 않습니다." />
          {/if}
          {#if view === "features" && selected}
            {#key selected.assetId}
              <AcquisitionFeatureProfile assetId={selected.assetId} />
            {/key}
          {:else if view === "spectrum" && selected}
            {#key selected.assetId}
              <AcquisitionSpectrum assetId={selected.assetId} />
            {/key}
          {:else if view === "reviews" && selected}
            <ReviewInboxView inbox={snapshot.reviewInbox} assetId={selected.assetId} />
          {:else if view === "relation" && selected}
            {#key selected.assetId}
              <RelationExplorer assetId={selected.assetId} />
            {/key}
          {:else if view === "projection" && selected}
            {#key selected.assetId}
              <ProjectionExplorer assetId={selected.assetId} />
            {/key}
          {:else if view === "compare" && selected}
            {#key selected.assetId}
              <PeriodComparison assetId={selected.assetId} />
            {/key}
          {:else if view === "departures" && selected}
            {#key selected.assetId}
              <DepartureExplorer assetId={selected.assetId} />
            {/key}
          {:else if view === "signals" && selected}
            {#key selected.assetId}
              <SignalExplorer assetId={selected.assetId} />
            {/key}
          {:else}
            <ObservationDetails asset={selected} {observed} {detailUrl} />
          {/if}
        </div>
      {/if}
    {/if}
  </main>
</div>
