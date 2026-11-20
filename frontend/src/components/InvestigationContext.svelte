<script lang="ts">
  import {investigationContext} from "../investigation-context";
  let {search}: {search: string} = $props();
  const context = $derived(investigationContext(search));
</script>
{#if context}<p class="origin"><span>관측에서 선택한 변화</span><strong>{context.label}</strong><span>{context.span}</span></p>{/if}
<style>
  .origin{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px var(--space-3);margin:0;font-size:var(--font-small);color:var(--color-ink-muted)}
  strong{font-weight:650;color:var(--color-ink)}
</style>
