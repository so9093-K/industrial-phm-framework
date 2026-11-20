<script lang="ts">
  import type {Snippet} from "svelte";
  import TaskDialog from "./TaskDialog.svelte";
  let {title, action = null, children}: {title: string; action?:string|null; children: Snippet<[close:()=>void]>} = $props();
  let open = $state(false);
</script>
<div class="analysis-controls">
  <button type="button" class="ui-button" onclick={() => open = true}>{action??title+" 변경"}</button>
  <TaskDialog bind:open {title}><div class="fields">{@render children(()=>open=false)}</div></TaskDialog>
</div>
<style>
  .analysis-controls { display:inline-flex; align-items:center; min-width:0; }
  .fields { display:grid; gap:var(--space-3); min-width:0; }
  .fields :global(.ranges), .fields :global(.periods) { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr)); gap:var(--space-4); }
</style>
