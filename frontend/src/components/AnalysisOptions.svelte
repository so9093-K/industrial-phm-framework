<script lang="ts">
  import {onMount} from "svelte";
  import {NAME, connectPlace, fact, nothingStored, place, readCapabilities, type Capabilities, type Capability} from "../capabilities";
  import {systemUrl} from "../routes";

  /** What this asset's stored data supports: each analysis opens with the asset kept, one
   * model connection away is one link, and what the data cannot support is one quiet line. */
  type Props = {assetId: string; level?: 2 | 3 | 4};
  let {assetId, level = 2}: Props = $props();
  let capabilities: Capabilities | null = $state(null);
  let loadState: "loading" | "ready" | "failed" = $state("loading");
  const empty = $derived.by(() => {
    const current: Capabilities | null = capabilities;
    return current ? nothingStored(current) : null;
  });
  const shown = $derived.by((): Capability[] => {
    const current: Capabilities | null = capabilities;
    return current ? current.items.filter((item) => item.status !== "unavailable") : [];
  });
  const refused = $derived.by((): Capability[] => {
    const current: Capabilities | null = capabilities;
    return current ? current.items.filter((item) => item.status === "unavailable") : [];
  });
  onMount(() => {
    const request = new AbortController();
    void readCapabilities(assetId, request.signal).then((value) => {
      if (!request.signal.aborted) { capabilities = value; loadState = "ready"; }
    }).catch(() => { if (!request.signal.aborted) loadState = "failed"; });
    return () => request.abort();
  });
</script>

<section class="options" aria-labelledby={"options-" + assetId}>
  <svelte:element this={"h" + level} id={"options-" + assetId}>분석 바로가기</svelte:element>
  {#if loadState === "loading"}
    <p class="context">저장된 데이터로 할 수 있는 분석을 확인하고 있습니다.</p>
  {:else if loadState === "failed" || !capabilities}
    <p class="context">분석 항목을 확인하지 못했습니다. 각 탭에서 직접 열 수 있습니다.</p>
  {:else if empty}
    <p>{empty === "not-received" ? "등록한 데이터 연결에서 아직 저장된 측정이 없습니다." : "저장된 측정이 없습니다."}
      <a href={systemUrl("connections")}>데이터 연결하기 →</a></p>
  {:else}
    <ul>
      {#each shown as item (item.id)}
        {@const href = place(item, assetId)}
        {@const connect = connectPlace(item, assetId)}
        <li data-status={item.status} data-capability={item.id}>
          <strong>{NAME[item.id]}</strong>
          <span class="fact">{fact(item, capabilities)}</span>
          {#if item.status === "waiting" || !href}
            <em>대기</em>
          {:else if item.status === "needs-connection"}
            <a {href} aria-label={NAME[item.id] + " 모델 연결하기"}>모델 연결하기 →</a>
          {:else}
            <span class="go"><a {href} aria-label={NAME[item.id] + " 열기"}>열기 →</a>
              {#if connect}<a href={connect} aria-label={NAME[item.id] + " 모델 연결하기"}>모델 연결하기 →</a>{/if}</span>
          {/if}
        </li>
      {/each}
    </ul>
    {#if refused.length}
      <p class="refused"><strong>지금 할 수 없는 분석</strong>
        {#each refused as item (item.id)}<span>{NAME[item.id]} — {fact(item, capabilities)}</span>{/each}</p>
    {/if}
  {/if}
</section>

<style>
  .options { display: grid; gap: var(--space-3); min-width: 0; }
  h2, h3, h4 { margin: 0; }
  p { margin: 0; overflow-wrap: anywhere; }
  .context { color: var(--color-ink-muted); font-size: var(--font-small); }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 0; }
  li { display: grid; grid-template-columns: minmax(7rem, 10rem) minmax(0, 1fr) auto; gap: var(--space-1) var(--space-3);
    align-items: center; padding: var(--space-3) 0; border-bottom: 1px solid var(--color-border); min-width: 0; }
  .fact { color: var(--color-ink-muted); font-size: var(--font-small); overflow-wrap: anywhere; }
  li em { font-style: normal; color: var(--color-ink-muted); font-size: var(--font-small); }
  li a { font-weight: 650; white-space: nowrap; }
  .go { display: flex; flex-wrap: wrap; gap: var(--space-1) var(--space-3); justify-content: flex-end; }
  .refused { display: flex; flex-wrap: wrap; gap: var(--space-1) var(--space-3); color: var(--color-ink-muted); font-size: var(--font-small); }
  .refused strong { color: var(--color-ink); }
  @media (max-width: 640px) {
    li { grid-template-columns: minmax(0, 1fr) auto; }
    li > strong { grid-column: 1; grid-row: 1; }
    li > a, li > em, .go { grid-column: 2; grid-row: 1; }
    .fact { grid-column: 1 / -1; grid-row: 2; }
  }
</style>
