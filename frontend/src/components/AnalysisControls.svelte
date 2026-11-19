<script lang="ts">
  import type {Snippet} from "svelte";
  import TaskDialog from "./TaskDialog.svelte";
  let {title, summary = null, action = null, children}: {title: string; summary?: string | null; action?:string|null; children: Snippet<[close:()=>void]>} = $props();
  let open = $state(false);
</script>
<div class="analysis-controls">
  {#if summary}<p>{summary}</p>{/if}
  <button type="button" class="ui-button" onclick={() => open = true}>{action??title+" 변경"}</button>
  <TaskDialog bind:open {title}><div class="fields">{@render children(()=>open=false)}</div></TaskDialog>
</div>
<style>
  .analysis-controls { grid-column: 1 / -1; grid-row: 1; display: flex; justify-content: space-between; align-items: center; gap: var(--space-3); margin-bottom: var(--space-2); min-width: 0; }
  .analysis-controls > p { margin: 0; color: var(--color-ink-muted); font-size: var(--font-small); overflow-wrap: anywhere; }
  .analysis-controls > button { margin-left: auto; }
  .fields { display: grid; gap: var(--space-3); min-width: 0; }
  .fields :global(.ranges), .fields :global(.periods) { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr)); gap:var(--space-4); }
</style>
