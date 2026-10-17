<script lang="ts">
  import {onMount, untrack} from "svelte";
  import type {Snapshot} from "../monitor";
  import {readSources, type Sources} from "../operations-status";
  import {systemUrl, type SystemSection} from "../routes";
  import ConnectionList from "./ConnectionList.svelte";
  import ConnectionRegistration from "./ConnectionRegistration.svelte";
  import CsvStart from "./CsvStart.svelte";
  import SampleWorkspace from "./SampleWorkspace.svelte";
  import SystemStatus from "./SystemStatus.svelte";

  /** 운영 관리: connect data and move each connection forward, or check that the local
   * services and stores work. The two parts share one address with a section. */
  type Props = {
    snapshot: Snapshot | null; storeState: "loading" | "ready" | "empty" | "failed"; storeError: string;
    writable: boolean; section: SystemSection;
    onChanged?: () => Promise<void>;
  };
  let {snapshot, storeState, storeError, writable, section, onChanged}: Props = $props();
  let sources: Sources | null = $state(null);
  let sourceState: "loading" | "ready" | "failed" = $state("loading");
  // Analyses run here count at once; the monitor snapshot catches up on the next read.
  let analyzedHere: string[] = $state([]);
  let request: AbortController | null = null;
  const analyzed = $derived(new Set([...(snapshot?.analyses.records.map((item) => item.sourceId) ?? []), ...analyzedHere]));
  const SECTIONS: {id: SystemSection; label: string}[] = [{id: "connections", label: "데이터 연결"}, {id: "status", label: "시스템 상태"}];

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
  onMount(() => { void reload(); return () => request?.abort(); });
</script>

<nav class="sections" aria-label="운영 관리">
  {#each SECTIONS as item (item.id)}
    <a href={systemUrl(item.id)} aria-current={section === item.id ? "page" : undefined}>{item.label}</a>
  {/each}
</nav>

{#if section === "connections"}
  <CsvStart {writable} onSaved={reload} />
  <ConnectionList {sources} loadState={sourceState} {writable} {analyzed} onReload={reload}
    onAnalyzed={(sourceId) => analyzedHere = [...analyzedHere, sourceId]} />
  <ConnectionRegistration {writable} onRegistered={reload} />
  <SampleWorkspace {writable} />
{:else}
  <SystemStatus {snapshot} {storeState} {storeError} />
{/if}

<style>
  .sections { display: inline-flex; flex-wrap: wrap; gap: var(--space-1); margin-block: var(--space-2) var(--space-4);
    padding: var(--space-1); border: 1px solid var(--color-border); border-radius: var(--radius-control); background: var(--color-surface); }
  .sections a { padding: var(--space-2) var(--space-4); border-radius: var(--radius-control); color: var(--color-ink); text-decoration: none; font-weight: 650; }
  .sections a[aria-current="page"] { background: var(--color-surface-selected); color: var(--color-action); }
</style>
