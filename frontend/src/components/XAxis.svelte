<script lang="ts">
  import {xTicks, type XScale} from "../time-axis";

  /** Tick labels under a stretched chart whose horizontal values run from `lo` to `hi`. As many
   * labels as fit the drawn width; `note` names what the axis counts when that is not plain. */
  let {lo, hi, scale, note = ""}: {lo: number; hi: number; scale: XScale; note?: string} = $props();
  let width = $state(640);
  const ticks = $derived(xTicks(lo, hi, scale, Math.max(2, Math.min(6, Math.floor(width / 115)))));
</script>

<div class="x-axis" bind:clientWidth={width}>
  <div class="ticks" aria-hidden="true">
    {#each ticks as tick (tick.value)}
      <span style={"left:" + tick.x * 100 + "%"} class:start={tick.x < 0.06} class:end={tick.x > 0.94}>{tick.label}</span>
    {/each}
  </div>
  {#if note}<p class="note">{note}</p>{/if}
</div>

<style>
  .x-axis { min-width: 0; }
  .ticks { position: relative; height: 1.6em; font-size: 12px; color: var(--color-ink-muted); font-variant-numeric: tabular-nums; }
  .ticks span { position: absolute; top: 0; transform: translateX(-50%); white-space: nowrap; padding-top: 5px; line-height: 1.2; }
  .ticks span::before { content: ""; position: absolute; top: 0; left: 50%; height: 4px; border-left: 1px solid var(--color-border); }
  .ticks span.start { transform: none; }
  .ticks span.start::before { left: 0; }
  .ticks span.end { transform: translateX(-100%); }
  .ticks span.end::before { left: auto; right: 0; }
  .note { margin: var(--space-1) 0 0; color: var(--color-ink-muted); font-size: var(--font-small); overflow-wrap: anywhere; }
</style>
