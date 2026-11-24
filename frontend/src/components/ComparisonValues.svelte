<script lang="ts">
  let {caption, names, a, b, note = null}: {
    caption: string; names: {a: string; b: string}; a: string; b: string; note?: string | null;
  } = $props();
</script>

<div class="comparison-values">
  <p>{caption}</p>
  <dl aria-label={caption}>
    <div><dt>{names.a}</dt><dd>{a}</dd></div>
    <div><dt>{names.b}</dt><dd>{b}</dd></div>
  </dl>
  {#if note}<p class="note">{note}</p>{/if}
</div>

<style>
  .comparison-values { display: grid; gap: 6px; }
  p { margin: 0; color: var(--color-ink-muted); font-size: var(--font-small); }
  dl { display: flex; flex-wrap: wrap; gap: 8px 24px; margin: 0; }
  dl > div + div { border-left: 1px solid var(--color-border); padding-inline-start: 24px; }
  dt { color: var(--color-ink-muted); font-size: var(--font-label); }
  dd { margin: 0; font-size: var(--font-result); font-weight: 700; line-height: 1.25; font-variant-numeric: tabular-nums; }
  dl > div + div dd { color: var(--color-action); }
</style>
