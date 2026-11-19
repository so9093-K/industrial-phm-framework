<script lang="ts">
  import {untrack} from "svelte";
  import {elapsedText} from "../time-axis";
  import {assetLabel, assetOptionLabel, flowLabel, type Asset} from "../monitor";
  import {defaultAnomalyMethod, defaultKind, kindsOf, methodsFor, readAssetData, type AssetData} from "../asset-data";
  import {readCapabilities, type Capabilities} from "../capabilities";
  import {
    DATA_INFO, METHOD_INFO, TAB_INFO, routeUrl, tabSelectionUrl, usesDataKind,
    type DataKind, type Method, type Route, type Tab,
  } from "../routes";
  import StatusNotice from "./StatusNotice.svelte";
  import AssetSummary from "./AssetSummary.svelte";
  import SignalExplorer from "./SignalExplorer.svelte";
  import VibrationSignals from "./VibrationSignals.svelte";
  import DepartureExplorer from "./DepartureExplorer.svelte";
  import ModelRunEvidence from "./ModelRunEvidence.svelte";
  import PeriodComparison from "./PeriodComparison.svelte";
  import AcquisitionFeatureProfile from "./AcquisitionFeatureProfile.svelte";
  import RelationExplorer from "./RelationExplorer.svelte";
  import AcquisitionRelation from "./AcquisitionRelation.svelte";
  import AcquisitionSpectrum from "./AcquisitionSpectrum.svelte";
  import ElectricalCondition from "./ElectricalCondition.svelte";
  import ProjectionExplorer from "./ProjectionExplorer.svelte";
  import AcquisitionOutlook from "./AcquisitionOutlook.svelte";
  import {readPublicDatasets, unfinishedImports, type UnfinishedImport} from "../public-datasets";
  import {systemUrl} from "../routes";

  type Props = {
    asset: Asset;
    assets: Asset[];
    route: Route;
    observed: (at: string | null) => string;
    onSelectAsset: (assetId: string) => void;
  };
  let {asset, assets, route, observed, onSelectAsset}: Props = $props();
  let data: AssetData | null = $state(null);
  let dataState: "loading" | "ready" | "failed" = $state("loading");
  let capabilities: Capabilities | null = $state(null);
  let capabilityState: "loading" | "ready" | "failed" = $state("loading");
  // Every analysis of an asset whose import has not finished reads only what was stored so far.
  let unfinished: UnfinishedImport | null = $state(null);
  $effect(() => {
    const id = asset.assetId, request = new AbortController();
    unfinished = null;
    void readPublicDatasets(request.signal)
      .then((datasets) => { if (id === asset.assetId) unfinished = unfinishedImports(datasets).get(id) ?? null; })
      .catch(() => {});
    return () => request.abort();
  });

  // Mixed inputs require an explicit measurement kind, never a hidden default.
  // A tab opens on an answer: the anomaly tab shows model scores when a model has results (or is
  // waiting for them), else the model-free baseline departures of a stored history.
  const anomalyDefault = $derived(defaultAnomalyMethod(capabilities, data));
  const method: Method | null = $derived(route.method ?? (route.tab === "change"
    ? methodsFor("change", data, capabilities, route.data ?? defaultKind(data))[0] ?? "compare"
    : route.tab === "anomaly" ? anomalyDefault : null));
  // Mixed inputs stay an explicit choice, but do not offer the wrong source
  // for a method the server cannot execute on that source kind.
  const eligibleKinds = $derived(kindsOf(data).filter(option =>
    route.tab !== "change" || method === null ||
      methodsFor(route.tab, data, capabilities, option).includes(method)));
  const kind: DataKind | null = $derived(
    usesDataKind(route.tab, method) ? route.data ?? defaultKind(data) ?? (eligibleKinds.length === 1 ? eligibleKinds[0] : null) : null);
  const chooseKind = $derived(
    usesDataKind(route.tab, method) && kind === null && kindsOf(data).length > 1);
  const methods = $derived(methodsFor(route.tab, data, capabilities, kind));
  const needsCapability = $derived(route.tab === "anomaly" || route.tab === "change");
  const noAvailableChange = $derived(route.tab === "change" && methods.length === 0);
  const waitingForDefault = $derived((dataState === "loading" || (needsCapability && capabilityState === "loading"))
    && route.tab !== "summary");
  const unsupportedSelection = $derived.by(() => {
    const state: "loading" | "ready" | "failed" = dataState;
    const current: AssetData | null = data;
    if (state !== "ready" || current === null) return false;
    return (route.method !== null && !methods.includes(route.method))
      || (route.data !== null && usesDataKind(route.tab, method)
        && !kindsOf(current).includes(route.data));
  });
  // 모니터링(중심) 화면은 설비마다 한 번 읽은 데이터로 계속 떠 있다. 분석 서랍을 열 때 다시 읽는 데이터는
  // 서랍에만 쓰고, 중심 화면의 계산을 다시 시작하지 않는다.
  let summaryData: AssetData | null = $state(null);
  let summaryState: "loading" | "ready" | "failed" = $state("loading");
  $effect(() => {
    const state: "loading" | "ready" | "failed" = dataState, current: AssetData | null = data;
    untrack(() => {
      if (state === "ready" && summaryData === null) {summaryData = current; summaryState = "ready";}
      else if (state === "failed" && summaryData === null) summaryState = "failed";
    });
  });
  // 설비 한 줄 소개는 서랍이 데이터를 다시 읽는 동안에도 처음 읽은 값으로 둔다.
  const known = $derived.by((): AssetData | null => { const fresh: AssetData | null = data, first: AssetData | null = summaryData; return fresh ?? first; });
  const facts = $derived.by(() => {
    const read: AssetData | null = known;
    if (!read) return "";
    const parts: string[] = [];
    if (read.history) parts.push("시계열 신호 " + read.history.signals + "개");
    if (read.vibration) parts.push("진동 측정 " + read.vibration.measurements + "회");
    return parts.join(" · ");
  });

  function at(tab: Tab, nextMethod: Method | null = null, nextKind: DataKind | null = null): string {
    return routeUrl({page: "assets", assetId: asset.assetId, tab, method: nextMethod, data: nextKind});
  }
  function retainSelection(event: MouseEvent) {
    const link = event.currentTarget as HTMLAnchorElement;
    link.href = tabSelectionUrl(link.href, location.href);
  }
  const drawerOpen = $derived(route.tab !== "summary");
  const drawerTitle = $derived(route.tab === "change" || route.tab === "anomaly"
    ? (method ? METHOD_INFO[method] : TAB_INFO[route.tab]) : TAB_INFO[route.tab]);
  let backLink: HTMLAnchorElement | null = $state(null);
  let drawer: HTMLElement | null = $state(null);
  // 서랍은 앱 상단 메뉴 아래에서 시작해, 다른 메뉴로 가는 길을 가리지 않는다.
  let drawerTop = $state(0);
  $effect(() => {
    if (!drawerOpen) return;
    const place = () => drawerTop = Math.max(0, document.querySelector(".topbar")?.getBoundingClientRect().bottom ?? 0);
    place();
    window.addEventListener("scroll", place, {passive: true});
    return () => window.removeEventListener("scroll", place);
  });
  $effect(() => {
    if (!drawerOpen) return;
    drawer?.focus({preventScroll: true});
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") backLink?.click(); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  });
  let dataRequest: AbortController | null = null;
  let capabilityRequest: AbortController | null = null;
  function reloadCapability() {
    capabilityRequest?.abort();
    const request = new AbortController(); capabilityRequest = request;
    capabilities = null; capabilityState = "loading";
    void readCapabilities(asset.assetId, request.signal).then(value => {
      if (!request.signal.aborted) {capabilities = value; capabilityState = "ready";}
    }).catch(() => {if (!request.signal.aborted) capabilityState = "failed";});
  }
  function reloadData() {
    dataRequest?.abort();
    const request = new AbortController(); dataRequest = request;
    data = null; dataState = "loading";
    void readAssetData(asset.assetId, request.signal).then((value) => {
      if (request.signal.aborted) return;
      data = value; dataState = "ready";
    }).catch(() => { if (!request.signal.aborted) dataState = "failed"; });
  }
  // A first model analysis or a new receipt can make another task available
  // while this asset remains open. Re-read input facts when entering a tab.
  $effect(() => {
    route.tab;
    reloadData();
    return () => dataRequest?.abort();
  });
  // A tab change reuses this component; fetch only for analysis selection, not
  // for every signal view or summary (which owns its separate options read).
  $effect(() => {
    route.tab;
    if (!needsCapability) return;
    reloadCapability();
    return () => capabilityRequest?.abort();
  });
</script>

<div class="workspace-asset" aria-busy={dataState === "loading"}>
  <div class="head">
    <div class="title">
      <h1>{assetLabel(assets, asset.assetId)}</h1>
      <!-- 한 줄: 어떤 기록인지와 시간을 어떻게 읽는지. 마지막 측정의 위치는 요약의 숫자가 말한다. -->
      <p class="meta">{#if !asset.lastObservedAt && known?.vibration}{flowLabel(asset.flow)}{facts ? " · " + facts : ""} · {known.vibration.timing
        ? "기록된 측정 간격 " + elapsedText(known.vibration.timing.periodSeconds) : "측정 간격 기록 없음(측정 회차로 표시)"} · 실제 측정 시각 기록 없음{:else}마지막 측정 {observed(asset.lastObservedAt)} · {flowLabel(asset.flow)}{facts ? " · " + facts : ""}{/if}</p>
    </div>
  </div>

  {#if unfinished}<p class="import-note" role="status">{unfinished.text}
    <a href={systemUrl("connections")}>{unfinished.running ? "진행 상황 보기" : "다시 가져오기"} →</a></p>{/if}

  {#if summaryState === "failed"}
    <StatusNotice kind="uncertain" title="설비의 데이터 종류를 확인하지 못했습니다"
      message="다시 불러오거나 다른 설비를 선택하세요."
      actionLabel="다시 불러오기" onAction={reloadData} />
  {/if}
  <!-- 중심: 이 설비의 모니터링 화면. 분석은 이 위의 서랍으로 열고, 닫으면 여기로 돌아온다. -->
  <div class="center" inert={drawerOpen}>
    <AssetSummary {asset} data={summaryData} dataState={summaryState} {observed} />
  </div>

  {#if drawerOpen}
  <a class="drawer-backdrop" style:top={drawerTop + "px"} href={at("summary")} onclick={retainSelection} aria-label="모니터링으로 돌아가기" tabindex="-1"></a>
  <section class="drawer" style:top={drawerTop + "px"} aria-labelledby="drawer-title" tabindex="-1" bind:this={drawer}>
    <header class="drawer-head">
      <a class="back" href={at("summary")} bind:this={backLink} onclick={retainSelection}>← 모니터링</a>
      <h2 id="drawer-title">{drawerTitle}</h2>
      {#if dataState === "ready" && (!needsCapability || capabilityState === "ready") && !chooseKind && (methods.length || kind)}
        <div class="choices">
          <!-- Shown once the asset's data is known, so a method it cannot use never flashes up. -->
          {#if methods.length > 1}
            <nav class="segmented" aria-label="분석 방법">
              {#each methods as option (option)}
                <a href={at(route.tab, option, usesDataKind(route.tab, option) ? kind : null)}
                  onclick={retainSelection} onauxclick={retainSelection} oncontextmenu={retainSelection}
                  aria-current={method === option ? "true" : undefined}>{METHOD_INFO[option]}</a>
              {/each}
            </nav>
          {/if}
          {#if kind && kindsOf(data).length > 1}
            <nav class="segmented" aria-label="데이터 종류">
              {#each eligibleKinds as option (option)}
                <a href={at(route.tab, method, option)} onclick={retainSelection} onauxclick={retainSelection} oncontextmenu={retainSelection}
                  aria-current={kind === option ? "true" : undefined}>{DATA_INFO[option]}</a>
              {/each}
            </nav>
          {/if}
        </div>
      {/if}
    </header>
    <div class="drawer-body">
  {#if dataState === "failed"}
    <StatusNotice kind="uncertain" title="설비의 데이터 종류를 확인하지 못했습니다"
      message="다시 불러오거나 다른 설비를 선택하세요."
      actionLabel="다시 불러오기" onAction={reloadData} />
  {:else if needsCapability && capabilityState === "failed"}
    <StatusNotice kind="uncertain" title="분석 가능 여부를 확인하지 못했습니다"
      message="서버의 분석 조건을 다시 확인하세요."
      actionLabel="다시 확인" onAction={reloadCapability} />
  {:else if waitingForDefault}
    <StatusNotice message="분석 가능한 항목을 확인하고 있습니다." />
  {:else if unsupportedSelection}
    <StatusNotice kind="uncertain" title="선택한 분석을 이 데이터에서 사용할 수 없습니다"
      message="지원하는 분석 방법을 선택하세요."
      actionLabel="모니터링으로 돌아가기" actionHref={at("summary")} />
  {:else if kindsOf(data).length === 0 && !(route.tab === "anomaly" && method === "model")}
    <StatusNotice kind="uncertain" title="분석할 저장 데이터가 없습니다"
      message="측정이 아직 없거나 분석에 필요한 데이터가 준비되지 않았습니다."
      actionLabel="모니터링으로 돌아가기" actionHref={at("summary")} />
  {:else if noAvailableChange}
    <StatusNotice kind="uncertain" title="현재 입력에서 가능한 변화 분석이 없습니다"
      message="측정 구간·채널·진동 분석 결과 또는 3상 입력 조건을 확인하세요."
      actionLabel="모니터링으로 돌아가기" actionHref={at("summary")} />
  {:else if chooseKind}
    <section class="task-chooser ui-panel" aria-labelledby="task-source-title">
      <h2 id="task-source-title">분석할 데이터 선택</h2>
      <ul>
        {#each eligibleKinds as option (option)}
          <li><a href={at(route.tab, method, option)} onclick={retainSelection}
            onauxclick={retainSelection} oncontextmenu={retainSelection}>{DATA_INFO[option]}으로 확인 →</a></li>
        {/each}
      </ul>
    </section>
  {:else}
    {#key asset.assetId + ":" + route.tab + ":" + method + ":" + kind}
      {#if route.tab === "signals"}
        {#if data?.history || !data?.vibration}<SignalExplorer assetId={asset.assetId} />{/if}
        {#if data?.vibration}<VibrationSignals assetId={asset.assetId} />{/if}
      {:else if route.tab === "anomaly" && method === "baseline"}
        <DepartureExplorer assetId={asset.assetId} />
      {:else if route.tab === "anomaly"}
        <ModelRunEvidence assetId={asset.assetId} timing={data?.vibration?.timing ?? null}
          measurements={data?.vibration ? {first: data.vibration.first, last: data.vibration.last} : null} />
      {:else if route.tab === "change" && method === "spectrum"}
        <AcquisitionSpectrum assetId={asset.assetId} timing={data?.vibration?.timing ?? null} />
      {:else if route.tab === "change" && method === "electrical"}
        <ElectricalCondition assetId={asset.assetId} />
      {:else if route.tab === "change" && method === "relation" && kind === "vibration"}
        <AcquisitionRelation assetId={asset.assetId} timing={data?.vibration?.timing ?? null} />
      {:else if route.tab === "change" && method === "relation"}
        <RelationExplorer assetId={asset.assetId} />
      {:else if route.tab === "change" && kind === "vibration"}
        <AcquisitionFeatureProfile assetId={asset.assetId} timing={data?.vibration?.timing ?? null} />
      {:else if route.tab === "change"}
        <PeriodComparison assetId={asset.assetId}
          electrical={capabilities?.items.some((item) => item.id === "electrical" && item.status === "ready") ?? false} />
      {:else if route.tab === "outlook" && kind === "vibration"}
        <AcquisitionOutlook assetId={asset.assetId} />
      {:else}
        <ProjectionExplorer assetId={asset.assetId} />
      {/if}
    {/key}
  {/if}
    </div>
  </section>
  {/if}
  <details><summary>설비 식별 정보</summary><p>설비 ID: {asset.assetId}</p></details>
</div>

<style>
  /* 분석 서랍: 모니터링 화면 위에 열리고, 왼쪽에 중심 화면이 비친다. 닫으면 같은 변화로 돌아온다. */
  .drawer-backdrop{position:fixed;inset:0;background:rgb(15 30 40 / .28);z-index:40}
  .drawer{position:fixed;top:0;right:0;bottom:0;width:min(1200px,calc(100vw - 220px));background:var(--color-page,var(--color-surface-selected));
    box-shadow:-12px 0 32px rgb(15 30 40 / .22);z-index:41;overflow-y:auto;padding:var(--space-4) var(--space-6) var(--space-8);display:grid;gap:var(--space-3);align-content:start;outline:none}
  .drawer-head{display:flex;flex-wrap:wrap;align-items:center;gap:var(--space-3) var(--space-5);position:sticky;top:calc(-1 * var(--space-4));z-index:2;
    background:inherit;padding-block:var(--space-3);border-bottom:1px solid var(--color-border)}
  .drawer-head h2{margin:0;font-size:var(--font-section)}
  .drawer-head .choices{margin-left:auto}
  .back{font-weight:700;text-decoration:none;padding:var(--space-2) var(--space-3);border:1px solid var(--color-control-border);border-radius:var(--radius-control);background:var(--color-surface)}
  .back:hover{border-color:var(--color-action)}
  .drawer-body{min-width:0;display:grid;gap:var(--space-3)}
  @media(max-width:860px){.drawer{width:100vw;padding-inline:var(--space-4)}}
  .workspace-asset { display: flex; flex-direction: column; gap: var(--space-2); min-width: 0; }
  .head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-end; gap: var(--space-4); margin-top: var(--space-3); }
  .title { min-width: 0; display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-1) var(--space-3); }
  h1 { overflow-wrap: anywhere; font-size: 1.3rem; margin: 0; }
  .meta { color: var(--color-ink-muted); margin: 0; overflow-wrap: anywhere; font-size: var(--font-small); }
  .import-note { margin: var(--space-3) 0 0; padding: var(--space-3) var(--space-4); border-left: 4px solid var(--color-uncertain-border);
    background: var(--color-uncertain-surface); color: var(--color-caution-ink); font-size: var(--font-small); overflow-wrap: anywhere; }
  .task-chooser { display: grid; gap: var(--space-3); }
  .task-chooser h2 { margin: 0; }
  .task-chooser ul { display: grid; gap: var(--space-3); margin: 0; padding: 0; list-style: none; }
  .task-chooser li { display: flex; flex-wrap: wrap; gap: var(--space-2); align-items: baseline; }
  .task-chooser li a { font-weight: 650; }
  .choices { display: flex; flex-wrap: wrap; gap: var(--space-3) var(--space-6); }
  .segmented { display: flex; flex-wrap: wrap; border: 1px solid var(--color-border); border-radius: var(--radius-control); overflow: hidden; }
  .segmented a {
    min-height: 40px; display: inline-flex; align-items: center; padding: var(--space-2) var(--space-4);
    color: var(--color-ink); text-decoration: none; background: var(--color-surface);
  }
  .segmented a + a { border-left: 1px solid var(--color-border); }
  .segmented a[aria-current="true"] { background: var(--color-surface-selected); font-weight: 700; color: var(--color-action); }
</style>
