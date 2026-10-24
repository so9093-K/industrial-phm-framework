<script lang="ts">
  import {measurementLabel,elapsedText} from "../time-axis";
  import {assetLabel, assetOptionLabel, flowLabel, type Asset} from "../monitor";
  import {defaultKind, kindsOf, methodsFor, readAssetData, type AssetData} from "../asset-data";
  import {readCapabilities, type Capabilities} from "../capabilities";
  import {
    DATA_INFO, METHOD_INFO, TAB_INFO, TABS, routeUrl, tabSelectionUrl, usesDataKind,
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

  // Every asset starts from the same task. The user chooses an anomaly method;
  // mixed inputs require an explicit measurement kind, never a hidden default.
  const method: Method | null = $derived(route.method ?? (route.tab === "change"
    ? methodsFor("change", data, capabilities, route.data ?? defaultKind(data))[0] ?? "compare" : null));
  const kind: DataKind | null = $derived(
    usesDataKind(route.tab, method) ? route.data ?? defaultKind(data) : null);
  const chooseAnomaly = $derived(route.tab === "anomaly" && route.method === null);
  const chooseKind = $derived(
    usesDataKind(route.tab, method) && kind === null && kindsOf(data).length > 1);
  const methods = $derived(methodsFor(route.tab, data, capabilities, kind));
  // Mixed inputs stay an explicit choice, but do not offer the wrong source
  // for a method the server cannot execute on that source kind.
  const eligibleKinds = $derived(kindsOf(data).filter(option =>
    route.tab !== "change" || method === null ||
      methodsFor(route.tab, data, capabilities, option).includes(method)));
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
  const facts = $derived.by(() => {
    if (!data) return "";
    const parts: string[] = [];
    if (data.history) parts.push("시계열 신호 " + data.history.signals + "개");
    if (data.vibration) parts.push("진동 측정 " + data.vibration.measurements + "회");
    return parts.join(" · ");
  });

  function at(tab: Tab, nextMethod: Method | null = null, nextKind: DataKind | null = null): string {
    return routeUrl({page: "assets", assetId: asset.assetId, tab, method: nextMethod, data: nextKind});
  }
  function retainSelection(event: MouseEvent) {
    const link = event.currentTarget as HTMLAnchorElement;
    link.href = tabSelectionUrl(link.href, location.href);
  }
  let tabBar: HTMLElement | null = $state(null);
  // On a phone the tab row scrolls; keep the current tab in view when it changes.
  $effect(() => {
    route.tab;
    tabBar?.querySelector<HTMLElement>('[aria-current="page"]')?.scrollIntoView({block: "nearest", inline: "nearest"});
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
  <nav class="crumbs" aria-label="현재 위치">
    <a href={routeUrl({page: "assets", assetId: "", tab: "summary", method: null, data: null})}>설비·신호</a>
    <span aria-hidden="true">›</span> <span>{assetLabel(assets, asset.assetId)}</span>
  </nav>
  <div class="head">
    <div class="title">
      <h1>{assetLabel(assets, asset.assetId)}</h1>
      <p class="meta">{!asset.lastObservedAt && data?.vibration ? "최근 " + measurementLabel(data.vibration.last,data.vibration.timing?.periodSeconds) : "마지막 측정 " + observed(asset.lastObservedAt)} · {flowLabel(asset.flow)}{facts ? " · " + facts : ""}</p>
      {#if !asset.lastObservedAt && data?.vibration}<p class="meta">{data.vibration.timing ? "시간 기준 · 기록된 측정 간격 " + elapsedText(data.vibration.timing.periodSeconds) : "측정 간격 기록 없음 · 측정 회차로 표시"} · 실제 측정 시각 기록 없음</p>{/if}
    </div>
    {#if assets.length > 1}
      <label class="switch-asset">다른 설비
        <select data-asset-switch value={asset.assetId} onchange={(event) => onSelectAsset(event.currentTarget.value)}>
          {#each assets as option (option.assetId)}<option value={option.assetId}>{assetOptionLabel(assets, option.assetId)}</option>{/each}
        </select>
      </label>
    {/if}
  </div>

  <details><summary>설비 식별 정보</summary><p>설비 ID: {asset.assetId}</p></details>

  <nav class="tabs" aria-label="설비 화면" bind:this={tabBar}>
    {#each TABS as tab (tab)}
      <a href={at(tab)} onclick={retainSelection} onauxclick={retainSelection} oncontextmenu={retainSelection}
        aria-current={route.tab === tab ? "page" : undefined}>{TAB_INFO[tab]}</a>
    {/each}
  </nav>
  <p class="tabs-hint">다른 설비 화면은 탭을 가로로 밀어 확인하세요.</p>

  {#if dataState === "ready" && (!needsCapability || capabilityState === "ready")
    && !chooseAnomaly && !chooseKind && (methods.length || kind)}
    <div class="choices">
      <!-- Shown once the asset's data is known, so a method it cannot use never flashes up. -->
      {#if methods.length > 1}
        <nav class="segmented" aria-label="분석 방법">
          {#each methods as option (option)}
            <a href={at(route.tab, option, usesDataKind(route.tab, option) ? kind : null)}
              onclick={retainSelection} onauxclick={retainSelection} oncontextmenu={retainSelection}
              aria-current={method === option ? "true" : undefined}>{METHOD_INFO[option]}{option === "electrical" ? " · 입력 조건 확인" : ""}</a>
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
      {:else if kind}
        <p class="only-kind">데이터 · {DATA_INFO[kind]}</p>
      {/if}
    </div>
  {/if}

  {#if dataState === "failed"}
    <StatusNotice kind="uncertain" title="설비의 데이터 종류를 확인하지 못했습니다"
      message="분석 방법을 추측해 보여 주지 않습니다. 다시 조회하거나 다른 설비를 선택하세요."
      actionLabel="다시 불러오기" onAction={reloadData} />
    {#if route.tab === "summary"}<AssetSummary {asset} {data} {dataState} {observed} />{/if}
  {:else if needsCapability && capabilityState === "failed" && route.tab !== "summary"}
    <StatusNotice kind="uncertain" title="분석 가능 여부를 확인하지 못했습니다"
      message="서버의 분석 조건을 확인하지 못했습니다. 가능한 분석을 추측하지 않습니다."
      actionLabel="다시 확인" onAction={reloadCapability} />
  {:else if waitingForDefault}
    <StatusNotice message="분석 가능한 항목을 확인하고 있습니다." />
  {:else if unsupportedSelection}
    <StatusNotice kind="uncertain" title="선택한 분석을 이 데이터에서 사용할 수 없습니다"
      message="지원하는 분석 방법을 선택하세요. 다른 데이터의 결과로 대체하지 않습니다."
      actionLabel="설비 요약 보기" actionHref={at("summary")} />
  {:else if route.tab !== "summary" && kindsOf(data).length === 0
    && !(route.tab === "anomaly" && (chooseAnomaly || method === "model"))}
    <StatusNotice kind="uncertain" title="분석할 저장 데이터가 없습니다"
      message="측정이 아직 없거나 분석에 필요한 데이터가 준비되지 않았습니다. 다른 종류로 대체해 보여 주지 않습니다."
      actionLabel="설비 요약 보기" actionHref={at("summary")} />
  {:else if noAvailableChange}
    <StatusNotice kind="uncertain" title="현재 입력에서 가능한 변화 분석이 없습니다"
      message="측정 구간·채널·진동 분석 결과 또는 3상 입력 조건을 확인하세요."
      actionLabel="설비 요약 보기" actionHref={at("summary")} />
  {:else if chooseAnomaly}
    <section class="task-chooser ui-panel" aria-labelledby="task-anomaly-title">
      <h2 id="task-anomaly-title">무엇이 평소와 달라졌나요?</h2>
      <p class="context">모델 점수는 연결된 모델과 분석 결과가 있어야 표시됩니다.</p>
      <ul>
        {#each methods as option (option)}
          <li><a href={at("anomaly", option)} onclick={retainSelection}
            onauxclick={retainSelection} oncontextmenu={retainSelection}>{METHOD_INFO[option]} 확인 →</a>
            <span class="context">{option === "baseline" ? "저장된 시계열의 기준 구간과 변화 비교" : "모델 분석 결과 또는 연결 상태 확인"}</span>
          </li>
        {/each}
      </ul>
    </section>
  {:else if chooseKind}
    <section class="task-chooser ui-panel" aria-labelledby="task-source-title">
      <h2 id="task-source-title">어떤 측정 근거로 확인할까요?</h2>
      <p class="context">분석할 측정 종류를 선택하세요.</p>
      <ul>
        {#each eligibleKinds as option (option)}
          <li><a href={at(route.tab, method, option)} onclick={retainSelection}
            onauxclick={retainSelection} oncontextmenu={retainSelection}>{DATA_INFO[option]}으로 확인 →</a></li>
        {/each}
      </ul>
    </section>
  {:else}
    {#key asset.assetId + ":" + route.tab + ":" + method + ":" + kind}
      {#if route.tab === "summary"}
        <AssetSummary {asset} {data} {dataState} {observed} />
      {:else if route.tab === "signals"}
        {#if data?.history || !data?.vibration}<SignalExplorer assetId={asset.assetId} />{/if}
        {#if data?.vibration}<VibrationSignals assetId={asset.assetId} />{/if}
      {:else if route.tab === "anomaly" && method === "baseline"}
        <DepartureExplorer assetId={asset.assetId} />
      {:else if route.tab === "anomaly"}
        <ModelRunEvidence assetId={asset.assetId} timing={data?.vibration?.timing ?? null} />
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
        <PeriodComparison assetId={asset.assetId} />
      {:else if route.tab === "outlook" && kind === "vibration"}
        <AcquisitionOutlook assetId={asset.assetId} />
      {:else}
        <ProjectionExplorer assetId={asset.assetId} />
      {/if}
    {/key}
  {/if}
</div>

<style>
  .workspace-asset { display: flex; flex-direction: column; gap: var(--space-4); min-width: 0; }
  .crumbs { font-size: var(--font-small); color: var(--color-ink-muted); display: flex; gap: var(--space-2); flex-wrap: wrap; }
  .head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-end; gap: var(--space-4); }
  .title { min-width: 0; }
  h1 { overflow-wrap: anywhere; }
  .meta { color: var(--color-ink-muted); margin: var(--space-1) 0 0; overflow-wrap: anywhere; }
  .switch-asset { display: grid; gap: var(--space-1); font-size: var(--font-small); font-weight: 700; }
  .switch-asset select {
    font: inherit; font-weight: 400; min-height: 44px; padding: var(--space-2) var(--space-3);
    border: 1px solid var(--color-border); border-radius: var(--radius-control);
    background: var(--color-surface); color: var(--color-ink);
  }
  .tabs { display: flex; flex-wrap: wrap; gap: var(--space-1); border-bottom: 1px solid var(--color-border); }
  .tabs-hint { display: none; margin: 0; color: var(--color-ink-muted); font-size: var(--font-small); }
  .task-chooser { display: grid; gap: var(--space-3); }
  .task-chooser h2, .task-chooser p { margin: 0; }
  .task-chooser ul { display: grid; gap: var(--space-3); margin: 0; padding: 0; list-style: none; }
  .task-chooser li { display: flex; flex-wrap: wrap; gap: var(--space-2); align-items: baseline; }
  .task-chooser li a { font-weight: 650; }
  .task-chooser .context { color: var(--color-ink-muted); font-size: var(--font-small); }
  /* One row of tabs that scrolls sideways on a phone, so the fifth tab is not on its own line. */
  @media (max-width: 560px) {
    .tabs { flex-wrap: nowrap; overflow-x: auto; scrollbar-width: thin; }
    .tabs a { flex: none; }
    .tabs-hint { display: block; }
  }
  .tabs a {
    padding: var(--space-3) var(--space-4); color: var(--color-ink-muted); text-decoration: none;
    border-bottom: 3px solid transparent; margin-bottom: -1px;
  }
  .tabs a[aria-current="page"] { color: var(--color-ink); font-weight: 700; border-bottom-color: var(--color-action); }
  .choices { display: flex; flex-wrap: wrap; gap: var(--space-3) var(--space-6); }
  .segmented { display: flex; flex-wrap: wrap; border: 1px solid var(--color-border); border-radius: var(--radius-control); overflow: hidden; }
  .segmented a {
    min-height: 40px; display: inline-flex; align-items: center; padding: var(--space-2) var(--space-4);
    color: var(--color-ink); text-decoration: none; background: var(--color-surface);
  }
  .segmented a + a { border-left: 1px solid var(--color-border); }
  .only-kind { margin: 0; align-self: center; color: var(--color-ink-muted); font-size: var(--font-small); }
  .segmented a[aria-current="true"] { background: var(--color-surface-selected); font-weight: 700; color: var(--color-action); }
</style>
