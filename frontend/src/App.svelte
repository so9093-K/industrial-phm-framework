<script lang="ts">
  import { onMount } from "svelte";
  import { readMonitor, type Asset, type Snapshot } from "./monitor";
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

  type LoadState = "loading" | "ready" | "empty" | "failed";
  let loadState: LoadState = $state("loading");
  let error = $state("");
  let snapshot: Snapshot | null = $state(null);
  const task = new URLSearchParams(location.search).get("view");
  const signalView = task === "signals";
  const departuresView = task === "departures";
  const comparisonView = task === "compare";
  const projectionView = task === "projection";
  const relationView = task === "relation";
  const reviewsView = task === "reviews";
  const spectrumView = task === "spectrum";
  let selectedId = $state(new URLSearchParams(location.search).get("monitor_asset") ?? "");
  let controller: AbortController | null = null;
  let selected: Asset | undefined = $derived.by(
    () => snapshot?.assets.find((asset: Asset) => asset.assetId === selectedId),
  );

  function selectAsset(assetId: string) {
    const previousAssetId = selectedId;
    selectedId = assetId;
    const url = new URL(location.href);
    url.searchParams.set("monitor_asset", assetId);
    if (assetId !== previousAssetId) url.searchParams.delete("monitor_channel");
    if (assetId !== previousAssetId) url.searchParams.delete("departure_baseline");
    if (assetId !== previousAssetId) for (const key of ["compare_a", "compare_b", "projection_horizon", "projection_management", "projection_end"]) url.searchParams.delete(key);
    history.replaceState(history.state, "", url);
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
      if (!result.assets.some((asset) => asset.assetId === selectedId)) {
        if (!selectedId && result.assets.length) selectAsset(result.assets[0].assetId);
        else if (selectedId) selectedId = "";
      }
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

  function nextUrl(view: "overview" | "signals" | "departures" | "compare" | "projection" | "relation" | "reviews" | "spectrum"): string {
    const url = new URL("/web-next/", location.origin);
    if (view !== "overview") url.searchParams.set("view", view);
    if (selectedId) url.searchParams.set("monitor_asset", selectedId);
    const channel = new URLSearchParams(location.search).get("monitor_channel");
    if (channel && view !== "overview") url.searchParams.set("monitor_channel", channel);
    return url.pathname + url.search;
  }

  onMount(() => {
    void refresh();
    return () => controller?.abort();
  });
</script>

<svelte:head>
  <title>Industrial PHM · {spectrumView ? "획득 원본 PSD" : reviewsView ? "검토 작업함" : relationView ? "신호 관계" : projectionView ? "버전 연계 전망" : comparisonView ? "두 구간 비교" : departuresView ? "기준 이탈 조사" : signalView ? "저장 신호 탐색" : "관측 현황"} 구조 검증</title>
</svelte:head>

<a class="skip" href="#main">본문으로 건너뛰기</a>
<div class="shell">
  <aside class="sidebar" aria-label="검증 화면 정보">
    <div class="brand">Industrial PHM <small>Operations / UI 실험</small></div>
    <nav aria-label="화면 바로가기">
      <a href="/web/">현재 운영 화면</a>
      <a href={nextUrl("overview")} aria-current={!signalView && !departuresView && !comparisonView && !projectionView && !relationView && !reviewsView && !spectrumView ? "page" : undefined}>새 관측 화면 검증</a>
      <a href={nextUrl("signals")} aria-current={signalView ? "page" : undefined}>저장 신호 탐색</a>
      <a href={nextUrl("departures")} aria-current={departuresView ? "page" : undefined}>기준 구간 이탈 조사</a>
      <a href={nextUrl("compare")} aria-current={comparisonView ? "page" : undefined}>두 기간의 측정 비교</a>
      <a href={nextUrl("projection")} aria-current={projectionView ? "page" : undefined}>조건부 상태 전망</a>
      <a href={nextUrl("relation")} aria-current={relationView ? "page" : undefined}>동일 시각 신호 관계</a>
      <a href={nextUrl("reviews")} aria-current={reviewsView ? "page" : undefined}>사람 검토 기록</a>
      <a href={nextUrl("spectrum")} aria-current={spectrumView ? "page" : undefined}>획득 원본 파형 PSD</a>
    </nav>
    <p class="note">독립 읽기 전용 화면입니다. 새 분석·판정 기능이 아닙니다.</p>
  </aside>
  <main id="main" tabindex="-1">
    <PageHeading
      eyebrow={spectrumView ? "획득 회차 · 원본 주파수" : reviewsView ? "검토 · 근거 일치 확인" : relationView ? "설비 조사 · 신호 관계" : projectionView ? "설비 전망 · 계산 근거" : comparisonView ? "설비 조사 · 구간 A/B" : departuresView ? "설비 조사 · 모델 없는 변화" : signalView ? "설비 조사 · 저장된 측정" : "관측 · 사실 확인"}
      title={spectrumView ? "획득 원본 파형 PSD 비교" : reviewsView ? "사람 검토 기록" : relationView ? "동일 시각 신호 관계 조사" : projectionView ? "조건부 상태 전망 검토" : comparisonView ? "두 기간의 측정 비교" : departuresView ? "기준 구간 이탈 조사" : signalView ? "설비 신호 탐색" : "설비 관측 현황"}
      description={spectrumView ? "검증된 파형 원본으로부터 서버가 계산한 Welch PSD만 비교합니다." : reviewsView ? "저장된 Finding과 정확히 연결된 AnalysisRun·Evidence를 확인합니다." : relationView ? "정확히 같은 출처·시각에 기록된 두 신호의 관측 짝을 비교합니다." : projectionView ? "같은 측정 버전일 때만 미래 신호 예측과 사용자 입력 기준 도달 전망을 함께 표시합니다." : comparisonView ? "측정 근거가 같은 두 기간의 대표값·결측·품질을 비교합니다. 구간 A는 검증된 정상 범위가 아닙니다." : departuresView ? "고른 신호가 선택한 기록 구간에서 얼마나 달라졌는지 탐색합니다. 설비 고장 진단이 아닙니다." : signalView ? "선택한 신호의 원본 의미·시간 구간·품질을 구분해서 확인합니다." : "마지막으로 기록된 관측과 출처의 상태를 구분해서 확인합니다."}
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
          {#if spectrumView && selected}
            {#key selected.assetId}
              <AcquisitionSpectrum assetId={selected.assetId} />
            {/key}
          {:else if reviewsView && selected}
            <ReviewInboxView inbox={snapshot.reviewInbox} assetId={selected.assetId} />
          {:else if relationView && selected}
            {#key selected.assetId}
              <RelationExplorer assetId={selected.assetId} />
            {/key}
          {:else if projectionView && selected}
            {#key selected.assetId}
              <ProjectionExplorer assetId={selected.assetId} />
            {/key}
          {:else if comparisonView && selected}
            {#key selected.assetId}
              <PeriodComparison assetId={selected.assetId} />
            {/key}
          {:else if departuresView && selected}
            {#key selected.assetId}
              <DepartureExplorer assetId={selected.assetId} />
            {/key}
          {:else if signalView && selected}
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
