<script lang="ts">
  import {onMount} from "svelte";
  import {assetLabel, assetOptionLabel, flowLabel, type Asset} from "../monitor";
  import {defaultKind, kindsOf, readAssetData, type AssetData} from "../asset-data";
  import {
    DATA_INFO, METHOD_INFO, TAB_INFO, TABS, methodsOf, routeUrl, usesDataKind,
    type DataKind, type Method, type Route, type Tab,
  } from "../routes";
  import StatusNotice from "./StatusNotice.svelte";
  import AssetSummary from "./AssetSummary.svelte";
  import SignalExplorer from "./SignalExplorer.svelte";
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

  // An explicit choice in the address wins; otherwise the asset's own data decides.
  const method: Method | null = $derived.by(() => {
    if (route.method) return route.method;
    if (route.tab === "anomaly") return data && !data.vibration && data.history ? "baseline" : "model";
    if (route.tab === "change") return "compare";
    return null;
  });
  const kind: DataKind | null = $derived(
    usesDataKind(route.tab, method) ? route.data ?? defaultKind(data) : null);
  const waitingForDefault = $derived(dataState === "loading" && (
    (route.tab === "anomaly" && !route.method) || (usesDataKind(route.tab, method) && !route.data)));
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
  onMount(() => {
    const request = new AbortController();
    void readAssetData(asset.assetId, request.signal).then((value) => {
      if (request.signal.aborted) return;
      data = value; dataState = "ready";
    }).catch(() => { if (!request.signal.aborted) dataState = "failed"; });
    return () => request.abort();
  });
</script>

<div class="workspace-asset">
  <nav class="crumbs" aria-label="현재 위치">
    <a href={routeUrl({page: "assets", assetId: "", tab: "summary", method: null, data: null})}>설비·신호</a>
    <span aria-hidden="true">›</span> <span>{assetLabel(assets, asset.assetId)}</span>
  </nav>
  <div class="head">
    <div class="title">
      <h1>{assetLabel(assets, asset.assetId)}</h1>
      <p class="meta">{!asset.lastObservedAt && data?.vibration ? "마지막 측정 순서 #" + data.vibration.last : "마지막 측정 " + observed(asset.lastObservedAt)} · {flowLabel(asset.flow)}{facts ? " · " + facts : ""}</p>
    </div>
    {#if assets.length > 1}
      <label class="switch-asset">다른 설비
        <select value={asset.assetId} onchange={(event) => onSelectAsset(event.currentTarget.value)}>
          {#each assets as option (option.assetId)}<option value={option.assetId}>{assetOptionLabel(assets, option.assetId)}</option>{/each}
        </select>
      </label>
    {/if}
  </div>

  <details><summary>설비 식별 정보</summary><p>설비 ID: {asset.assetId}</p></details>

  <nav class="tabs" aria-label="설비 화면">
    {#each TABS as tab (tab)}
      <a href={at(tab)} aria-current={route.tab === tab ? "page" : undefined}>{TAB_INFO[tab]}</a>
    {/each}
  </nav>

  {#if methodsOf(route.tab).length || kind}
    <div class="choices">
      {#if methodsOf(route.tab).length}
        <nav class="segmented" aria-label="분석 방법">
          {#each methodsOf(route.tab) as option (option)}
            <a href={at(route.tab, option, usesDataKind(route.tab, option) ? kind : null)}
              aria-current={method === option ? "true" : undefined}>{METHOD_INFO[option]}</a>
          {/each}
        </nav>
      {/if}
      {#if kind && kindsOf(data).length > 1}
        <nav class="segmented" aria-label="데이터 종류">
          {#each kindsOf(data) as option (option)}
            <a href={at(route.tab, method, option)} aria-current={kind === option ? "true" : undefined}>{DATA_INFO[option]}</a>
          {/each}
        </nav>
      {:else if kind}
        <p class="only-kind">데이터 · {DATA_INFO[kind]}</p>
      {/if}
    </div>
  {/if}

  {#if waitingForDefault}
    <StatusNotice message="이 설비가 가진 데이터 종류를 확인하고 있습니다." />
  {:else}
    {#key asset.assetId + ":" + route.tab + ":" + method + ":" + kind}
      {#if route.tab === "summary"}
        <AssetSummary {asset} {data} {dataState} {observed} />
      {:else if route.tab === "signals"}
        <SignalExplorer assetId={asset.assetId} />
      {:else if route.tab === "anomaly" && method === "baseline"}
        <DepartureExplorer assetId={asset.assetId} />
      {:else if route.tab === "anomaly"}
        <ModelRunEvidence assetId={asset.assetId} />
      {:else if route.tab === "change" && method === "spectrum"}
        <AcquisitionSpectrum assetId={asset.assetId} />
      {:else if route.tab === "change" && method === "electrical"}
        <ElectricalCondition assetId={asset.assetId} />
      {:else if route.tab === "change" && method === "relation" && kind === "vibration"}
        <AcquisitionRelation assetId={asset.assetId} />
      {:else if route.tab === "change" && method === "relation"}
        <RelationExplorer assetId={asset.assetId} />
      {:else if route.tab === "change" && kind === "vibration"}
        <AcquisitionFeatureProfile assetId={asset.assetId} />
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
