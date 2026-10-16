<script lang="ts">
  import { onMount } from "svelte";
  import { readMonitor, type Asset, type Snapshot } from "./monitor";

  type LoadState = "loading" | "ready" | "empty" | "failed";
  let loadState: LoadState = $state("loading");
  let error = $state("");
  let snapshot: Snapshot | null = $state(null);
  let selectedId = $state(new URLSearchParams(location.search).get("monitor_asset") ?? "");
  let controller: AbortController | null = null;

  let selected: Asset | undefined = $derived(snapshot?.assets.find((asset) => asset.assetId === selectedId));

  function selectAsset(assetId: string) {
    selectedId = assetId;
    const url = new URL(location.href);
    url.searchParams.set("monitor_asset", assetId);
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
    return Number.isNaN(date.getTime()) ? "관측 시각 해석 불가" : date.toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
  }

  function detailUrl(assetId: string): string {
    return "/web/?monitor_asset=" + encodeURIComponent(assetId) + "#signals";
  }

  onMount(() => {
    void refresh();
    return () => controller?.abort();
  });
</script>

<svelte:head>
  <title>Industrial PHM · 관측 현황 구조 검증</title>
</svelte:head>

<a class="skip" href="#main">본문으로 건너뛰기</a>
<div class="shell">
  <aside class="sidebar" aria-label="검증 화면 정보">
    <div class="brand">Industrial PHM <small>Operations / UI 실험</small></div>
    <nav aria-label="화면 바로가기">
      <a href="/web/">현재 운영 화면</a>
      <a href="/web-next/" aria-current="page">새 관측 화면 검증</a>
    </nav>
    <p class="note">독립 읽기 전용 화면입니다. 새 분석·판정 기능이 아닙니다.</p>
  </aside>
  <main id="main" tabindex="-1">
    <header class="heading">
      <div>
        <p class="eyebrow">관측 · 사실 확인</p>
        <h1>설비 관측 현황</h1>
        <p class="support">마지막으로 기록된 관측과 출처의 상태를 구분해서 확인합니다.</p>
      </div>
      <button type="button" onclick={() => void refresh()} disabled={loadState === "loading"}>다시 불러오기</button>
    </header>

    {#if loadState === "loading"}
      <p class="notice" role="status">저장된 관측을 확인하는 중입니다.</p>
    {:else if loadState === "failed"}
      <section class="notice failure" role="alert">
        <h2>조회 결과를 확인할 수 없습니다</h2>
        <p>{error} 데이터 없음이나 설비 이상으로 판단하지 않습니다.</p>
        <button type="button" onclick={() => void refresh()}>다시 시도</button>
      </section>
    {:else if snapshot}
      <p class="meta">조회 평가 시각: {observed(snapshot.assessedAt)} · API가 반환한 저장 이력 기준</p>
      {#if snapshot.systemReadUncertain}
        <p class="notice" role="status">일부 저장소·수집 근거를 확인하지 못했습니다. 조회 가능한 결과도 현재 상태를 보장하지 않습니다.</p>
      {/if}
      {#if snapshot.truncated}
        <p class="notice" role="status">설비 목록은 서버 조회 제한에 따라 일부만 표시됩니다.</p>
      {/if}
      {#if loadState === "empty"}
        <section class="notice">
          <h2>조회된 설비가 없습니다</h2>
          <p>데이터 미등록과 부분적인 읽기 실패는 서로 다른 상태입니다. 연결 상태에서 확인하세요.</p>
          <a href="/web/#connect">데이터 연결 화면 열기</a>
        </section>
      {:else}
        <div class="workspace">
          <section class="asset-list" aria-labelledby="asset-title">
            <h2 id="asset-title">조회된 설비 <span>{snapshot.assets.length}개</span></h2>
            <div class="asset-choices">
              {#each snapshot.assets as asset (asset.assetId)}
                <button
                  type="button"
                  class:active={selectedId === asset.assetId}
                  aria-pressed={selectedId === asset.assetId}
                  onclick={() => selectAsset(asset.assetId)}
                >
                  <strong>{asset.assetId}</strong>
                  <span>마지막 관측: {observed(asset.lastObservedAt)}</span>
                </button>
              {/each}
            </div>
          </section>
          <section class="detail" aria-labelledby="detail-title">
            <h2 id="detail-title">선택한 설비의 관측 사실</h2>
            {#if selected}
              <dl class="facts">
                <div><dt>설비 식별자</dt><dd>{selected.assetId}</dd></div>
                <div><dt>마지막 관측 시각</dt><dd>{observed(selected.lastObservedAt)}</dd></div>
                <div><dt>데이터 흐름 상태(서버 제공 값)</dt><dd>{selected.flow}</dd></div>
                <div><dt>확인 항목 수</dt><dd>{selected.attentionCount}</dd></div>
              </dl>
              <p class="explain">수집 상태와 설비의 정상·고장 상태는 다릅니다. 이 화면은 고장 진단이나 실시간 경보가 아닙니다.</p>
              <a class="detail-link" href={detailUrl(selected.assetId)}>원본 신호와 저장 이력 확인 →</a>
            {:else}
              <p class="notice">설비를 선택하면 마지막 관측 근거를 표시합니다.</p>
            {/if}
          </section>
        </div>
      {/if}
    {/if}
  </main>
</div>
