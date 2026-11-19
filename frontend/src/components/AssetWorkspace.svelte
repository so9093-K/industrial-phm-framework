<script lang="ts">
  import {untrack,tick} from "svelte";
  import {elapsedText} from "../time-axis";
  import {assetLabel, flowLabel, type Asset} from "../monitor";
  import {defaultAnomalyMethod, defaultKind, kindsOf, methodsFor, readAssetData, type AssetData} from "../asset-data";
  import {readCapabilities, type Capabilities} from "../capabilities";
  import {
    DATA_INFO, METHOD_INFO, TAB_INFO, routeUrl, tabSelectionUrl, usesDataKind,
    type DataKind, type Method, type Route, type Tab,
  } from "../routes";
  import StatusNotice from "./StatusNotice.svelte";
  import AssetSummary from "./AssetSummary.svelte";
  import AssetName from "./AssetName.svelte";
  import InvestigationContext from "./InvestigationContext.svelte";
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
  };
  let {asset, assets, route, observed}: Props = $props();
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
  const facts = $derived.by(() => {
    const read: AssetData | null = data;
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
  const analysisOpen = $derived(route.tab !== "summary");
  const analysisTitle = $derived(route.tab === "change" || route.tab === "anomaly"
    ? (method ? METHOD_INFO[method] : TAB_INFO[route.tab]) : TAB_INFO[route.tab]);
  const analysisTabs=$derived.by(()=>{
    const input=kind??defaultKind(data),available=methodsFor("change",data,capabilities,input);
    const rows:{label:string;tab:Tab;method:Method|null;kind:DataKind|null}[]=[];
    if(data?.history||data?.vibration)rows.push({label:"실측 신호",tab:"signals",method:null,kind:null});
    if(available.includes("compare"))rows.push({label:"기간 비교",tab:"change",method:"compare",kind:input});
    if(available.includes("relation"))rows.push({label:"신호 관계",tab:"change",method:"relation",kind:input});
    if(available.includes("spectrum"))rows.push({label:"주파수",tab:"change",method:"spectrum",kind:null});
    if(available.includes("electrical"))rows.push({label:"3상 전력",tab:"change",method:"electrical",kind:null});
    rows.push({label:"모델 반응",tab:"anomaly",method:anomalyDefault,kind:null});
    rows.push({label:"전망·예상 여유",tab:"outlook",method:null,kind:input});
    return rows;
  });
  let backLink: HTMLAnchorElement | null = $state(null);
  let analysisView: HTMLElement | null = $state(null);
  let selectedAt = $state<number | null>(null);
  $effect(() => {
    if (!analysisOpen) return;
    void tick().then(()=>analysisView?.focus({preventScroll:true}));
    const close = (event: KeyboardEvent) => { if (event.key === "Escape" && !event.defaultPrevented && !document.querySelector("dialog[open]")) backLink?.click(); };
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
  // 목록을 주기적으로 다시 읽으면 asset·route가 새 객체로 들어온다. 탭 이름(문자열)이 바뀔 때만 다시 읽어야
  // 열린 분석이 처음부터 다시 계산되지 않는다.
  const tab = $derived(route.tab);
  // A first model analysis or a new receipt can make another task available
  // while this asset remains open. Re-read input facts when entering a tab.
  $effect(() => {
    tab;
    untrack(reloadData);
    return () => dataRequest?.abort();
  });
  // Every open analysis offers the other supported views of this same phenomenon.
  $effect(() => {
    tab;
    if (tab==="summary") return;
    untrack(reloadCapability);
    return () => capabilityRequest?.abort();
  });
</script>

<div class="workspace-asset" aria-busy={dataState === "loading"}>
  <div class="head" class:visually-hidden={!analysisOpen}>
    <div class="title">
      <h1><AssetName label={assetLabel(assets, asset.assetId)}/></h1>
      <p class="meta">{#if !asset.lastObservedAt && data?.vibration}진동 기록 {data.vibration.measurements}회 · {data.vibration.timing
        ? elapsedText(data.vibration.timing.periodSeconds)+" 간격" : "측정 순서로 표시"} · 날짜·시각 미기록{:else}{flowLabel(asset.flow)} · 마지막 측정 {observed(asset.lastObservedAt)}{/if}</p>
    </div>
  </div>

  {#if unfinished}<p class="import-note" role="status">{unfinished.text}
    <a href={systemUrl("connections")}>{unfinished.running ? "진행 상황 보기" : "다시 가져오기"} →</a></p>{/if}

  {#if !analysisOpen}
    <AssetSummary {asset} {data} {dataState} {observed} bind:selectedAt />
  {:else}
  <section class="analysis-view" aria-labelledby="analysis-view-title" tabindex="-1" bind:this={analysisView}>
    <header class="analysis-view-head">
      <div class="selection-context"><a class="back" href={at("summary")} bind:this={backLink} onclick={retainSelection}>← 모니터링</a>
        {#key route.tab+":"+method+":"+kind}<InvestigationContext search={location.search}/>{/key}</div>
      <h2 id="analysis-view-title" class="visually-hidden">{analysisTitle}</h2>
      {#if dataState === "ready" && kind && kindsOf(data).length>1 && (!needsCapability || capabilityState === "ready") && !chooseKind}
        <div class="choices">
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
    <nav class="analysis-tabs" aria-label="선택한 변화의 분석">
      {#each analysisTabs as item(item.label)}
        <a href={at(item.tab,item.method,item.kind)} onclick={retainSelection}
          aria-current={route.tab===item.tab && (item.method===null||item.method===method)?"page":undefined}>{item.label}</a>
      {/each}
    </nav>
    </header>
    <div class="analysis-view-body">
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
        {#if data?.vibration}<VibrationSignals assetId={asset.assetId} selectedPosition={selectedAt} onPosition={at=>selectedAt=at}/>{/if}
      {:else if route.tab === "anomaly" && method === "baseline"}
        <DepartureExplorer assetId={asset.assetId} />
      {:else if route.tab === "anomaly"}
        <ModelRunEvidence assetId={asset.assetId} timing={data?.vibration?.timing ?? null}
          selectedPosition={data?.vibration?selectedAt:null} onPosition={at=>{if(data?.vibration)selectedAt=at;}}
          measurements={data?.vibration ? {first: data.vibration.first, last: data.vibration.last} : null} />
      {:else if route.tab === "change" && method === "spectrum"}
        <AcquisitionSpectrum assetId={asset.assetId} timing={data?.vibration?.timing ?? null} selectedPosition={selectedAt} onPosition={at=>selectedAt=at}/>
      {:else if route.tab === "change" && method === "electrical"}
        <ElectricalCondition assetId={asset.assetId} />
      {:else if route.tab === "change" && method === "relation" && kind === "vibration"}
        <AcquisitionRelation assetId={asset.assetId} timing={data?.vibration?.timing ?? null} selectedPosition={selectedAt} onPosition={at=>selectedAt=at}/>
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
  </section>
  {/if}
  <details><summary>설비·기록 상세</summary><p>{facts}</p><p>설비 ID: {asset.assetId}</p></details>
</div>

<style>
  .analysis-view{min-width:0;display:grid;gap:var(--space-3);align-content:start;outline:none}
  .analysis-view-head{display:flex;flex-wrap:wrap;align-items:center;gap:4px var(--space-3);
    padding:var(--space-2) var(--space-4);border:1px solid var(--color-border);border-radius:var(--radius-control);background:var(--color-surface)}
  .analysis-view-head h2{margin:0;font-size:var(--font-section)}
  .analysis-view-head .choices{margin-left:auto}
  .selection-context{flex-basis:100%;display:flex;align-items:baseline;flex-wrap:wrap;gap:var(--space-3);min-width:0}
  .back{font-size:var(--font-small);font-weight:650;text-decoration:none;padding:var(--space-2);color:var(--color-action)}
  .back:hover{border-color:var(--color-action)}
  .analysis-view-body{min-width:0;display:grid;gap:var(--space-3)}
  .analysis-tabs{order:0;display:flex;flex-wrap:wrap;gap:var(--space-1)}
  .analysis-tabs a{padding:var(--space-2);font-size:var(--font-small);font-weight:650;color:var(--color-ink-muted);text-decoration:none;border-bottom:3px solid transparent}
  .analysis-tabs a[aria-current="page"]{color:var(--color-action);border-bottom-color:var(--color-action)}
  .workspace-asset { display: flex; flex-direction: column; gap: var(--space-2); min-width: 0; }
  .visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0; }
  .head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-end; gap: var(--space-4); margin-top: 0; }
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
