<script lang="ts">
  import type {Snippet} from "svelte";
  import {measure, type Tick} from "../chart-axis";

  /** Value labels to the left of a stretched chart: the ticks sit at the chart's own heights,
   * so they line up with the grid lines drawn inside the SVG. */
  let {ticks, height, unit, children, footer}: {ticks: Tick[]; height: number; unit: string | null; children: Snippet;
    footer?: Snippet} = $props();
  const labels = $derived(ticks.map((tick) => ({...tick, text: measure(tick.value, unit)})));
  const widest = $derived(labels.reduce((best, item) => item.text.length > best.length ? item.text : best, ""));
</script>

<div class="plotted">
  <div class="labels" aria-hidden="true">
    <span class="sizer">{widest}</span>
    {#each labels as tick (tick.value)}<span class="tick" style={"top:" + (tick.y / height) * 100 + "%"}>{tick.text}</span>{/each}
  </div>
  <div class="area">{@render children()}</div>
  {#if footer}<div class="footer">{@render footer()}</div>{/if}
</div>

<style>
  .plotted { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: var(--space-2); align-items: stretch; }
  .labels { position: relative; font-size: 12px; color: var(--color-ink-muted); font-variant-numeric: tabular-nums; }
  .sizer { visibility: hidden; display: block; height: 0; overflow: hidden; white-space: nowrap; }
  .tick { position: absolute; right: 0; transform: translateY(-50%); white-space: nowrap; line-height: 1; }
  .area, .footer { min-width: 0; }
  .footer { grid-column: 2; }
  .area :global(svg) { display: block; margin: 0; }
</style>
