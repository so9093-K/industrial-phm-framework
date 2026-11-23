<script lang="ts">
  import {onMount, untrack} from "svelte";
  import type {Snapshot} from "../monitor";
  import {readSources, type Sources} from "../operations-status";
  import {systemUrl, type SystemSection} from "../routes";
  import ConnectionList from "./ConnectionList.svelte";
  import ConnectionRegistration from "./ConnectionRegistration.svelte";
  import CsvStart from "./CsvStart.svelte";
  import PublicDatasets from "./PublicDatasets.svelte";
  import SystemStatus from "./SystemStatus.svelte";

  /** 운영 관리: connect data and move each connection forward, or check that the local
   * services and stores work. The two parts share one address with a section. */
  type Props = {
    snapshot: Snapshot | null; storeState: "loading" | "ready" | "empty" | "failed"; storeError: string;
    writable: boolean; section: SystemSection;
    onChanged?: () => Promise<void>;
    onFileSelected?:(selected:boolean)=>void;
  };
  let {snapshot, storeState, storeError, writable, section, onChanged,onFileSelected}: Props = $props();
  let sources: Sources | null = $state(null);
  let sourceState: "loading" | "ready" | "failed" = $state("loading");
  // Analyses run here count at once; the monitor snapshot catches up on the next read.
  let analyzedHere: string[] = $state([]);
  let request: AbortController | null = null;
  const analyzed = $derived(new Set([...(snapshot?.analyses.records.map((item) => item.sourceId) ?? []), ...analyzedHere]));
  const SECTIONS: {id: SystemSection; label: string}[] = [{id: "connections", label: "데이터 연결"}, {id: "status", label: "시스템 상태"}];
  // 데이터를 가져오는 방법은 한 번에 하나만 펼친다. 고르던 파일과 입력은 다른 방법을 보는 동안에도 남는다.
  type Way = "csv" | "public" | "other";
  const WAYS: {id: Way; label: string; note: string; hash: string}[] = [
    {id: "csv", label: "CSV 파일", note: "내 컴퓨터의 측정 기록 파일", hash: ""},
    {id: "public", label: "공개 실측 데이터", note: "AI-Hub 전력 · XJTU-SY 진동", hash: "#public-datasets"},
    {id: "other", label: "자동으로 데이터 받기", note: "OPC UA · 서버의 CSV 파일", hash: "#other-connect"},
  ];
  const wayOf = (hash: string): Way => hash === "#public-datasets" ? "public" : hash === "#opcua-connect" || hash === "#other-connect" ? "other" : "csv";
  let csvSelected=$state(false);
  let way: Way = $state(wayOf(location.hash));
  $effect(()=>onFileSelected?.(section==="connections"&&way==="csv"&&csvSelected));
  function choose(next: Way) {
    way = next;
    // 주소에 남겨 두면 새로 고침이나 공유한 주소도 같은 방법으로 열린다.
    history.replaceState(history.state, "", location.pathname + location.search + (WAYS.find((item) => item.id === next)?.hash ?? ""));
  }

  async function reload() {
    request?.abort();
    const pending = new AbortController(); request = pending;
    sourceState = "loading";
    try {
      const value = await readSources(pending.signal);
      if (!pending.signal.aborted) { sources = value; sourceState = "ready"; await onChanged?.(); }
    } catch {
      if (!pending.signal.aborted) sourceState = "failed";
    }
  }
  let previous = untrack(() => storeState);
  $effect(() => {
    const current = storeState;
    if (current === "loading" && previous !== "loading") untrack(() => void reload());
    previous = current;
  });
  onMount(() => {
    void reload();
    const follow = () => way = wayOf(location.hash);
    window.addEventListener("hashchange", follow);
    return () => { request?.abort(); window.removeEventListener("hashchange", follow); };
  });
</script>

<nav class="sections" class:compact={way==="csv"&&csvSelected} aria-label="운영 관리">
  {#each SECTIONS as item (item.id)}
    <a href={systemUrl(item.id)} aria-current={section === item.id ? "page" : undefined}>{item.label}</a>
  {/each}
</nav>

{#if section === "connections"}
  <section class="ui-panel ways" class:compact={way==="csv"&&csvSelected} aria-labelledby="ways-title">
    <h2 id="ways-title">데이터 가져오기</h2>
    <div class="way-list" role="group" aria-label="데이터를 가져오는 방법">
      {#each WAYS as item (item.id)}
        <button type="button" aria-pressed={way === item.id} onclick={() => choose(item.id)}>
          <strong>{item.label}</strong><span>{item.note}</span></button>
      {/each}
    </div>
  </section>
  <div hidden={way !== "csv"}><CsvStart {writable} onSaved={reload} onFileSelected={selected=>csvSelected=selected} /></div>
  <div hidden={way !== "public"}><PublicDatasets {writable} onImported={reload} /></div>
  <div hidden={way !== "other"}><ConnectionRegistration {writable} onRegistered={reload} /></div>
  {#if way!=="csv"||!csvSelected}<ConnectionList {sources} loadState={sourceState} {writable} {analyzed} onReload={reload}
    onAnalyzed={(sourceId) => analyzedHere = [...analyzedHere, sourceId]} />{/if}
{:else}
  <SystemStatus {snapshot} {storeState} {storeError} />
{/if}

<style>
  .sections.compact{margin-block:0 8px;padding:2px}.sections.compact a{padding:4px 10px;font-size:var(--font-label)}
  .sections { display: inline-flex; flex-wrap: wrap; gap: var(--space-1); margin-block: var(--space-2) var(--space-4);
    padding: var(--space-1); border: 1px solid var(--color-border); border-radius: var(--radius-control); background: var(--color-surface); }
  .sections a { padding: var(--space-2) var(--space-4); border-radius: var(--radius-control); color: var(--color-ink); text-decoration: none; font-weight: 650; }
  .sections a[aria-current="page"] { background: var(--color-surface-selected); color: var(--color-action); }
  .ways.compact{padding-block:var(--space-2)}
  .ways.compact h2,.ways.compact button span{display:none}
  .ways.compact button{padding-block:var(--space-2);min-height:36px}
  .ways h2 { margin: 0 0 var(--space-3); }
  .way-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); gap: var(--space-3); }
  .way-list button { display: grid; gap: var(--space-1); text-align: left; padding: var(--space-3) var(--space-4); min-height: 44px;
    border: 1px solid var(--color-control-border); border-radius: var(--radius-control); background: var(--color-surface); color: var(--color-ink); }
  .way-list button span { font-size: var(--font-small); color: var(--color-ink-muted); }
  .way-list button[aria-pressed="true"] { border-color: var(--color-action); box-shadow: inset 0 0 0 1px var(--color-action); background: var(--color-surface-selected); }
  .way-list button[aria-pressed="true"] strong { color: var(--color-action); }
  .way-list button:hover { border-color: var(--color-action); }
</style>
