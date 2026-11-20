<script lang="ts">
  import type {Snippet} from "svelte";
  /** Keep an opened task's draft when closed; callers can pause background work with open. */
  let {open = $bindable(false), title, children}: {open?: boolean; title: string; children: Snippet} = $props();
  let dialog: HTMLDialogElement;
  let visited = $state(false);
  const id = $props.id();
  $effect(() => {
    if (!dialog) return;
    if (open) { visited = true; if (!dialog.open) dialog.showModal(); }
    else if (dialog.open) dialog.close();
  });
</script>

<dialog bind:this={dialog} aria-labelledby={id} onclose={() => {if(!dialog.open)open = false;}} oncancel={() => open = false}>
  <header><h2 id={id}>{title}</h2><button type="button" class="ui-button" onclick={() => open = false}>닫기</button></header>
  <div class="content">{#if visited}{@render children()}{/if}</div>
</dialog>

<style>
  dialog { width: min(880px, calc(100vw - 48px)); max-height: calc(100dvh - 64px); padding: 0; border: 1px solid var(--color-border); border-radius: var(--radius-panel); background: var(--color-surface); color: var(--color-ink); box-shadow: 0 16px 64px rgb(0 0 0 / .2); }
  dialog::backdrop { background: rgb(15 35 48 / .4); }
  header { display: flex; align-items: center; justify-content: space-between; gap: var(--space-4); padding: var(--space-4) var(--space-5); border-bottom: 1px solid var(--color-border); }
  h2 { margin: 0; font-size: var(--font-section); }
  .content { padding: var(--space-5); display: grid; gap: var(--space-4); }
  @media (max-width: 600px) { dialog { width: calc(100vw - 24px); max-height: calc(100dvh - 24px); } .content { padding: var(--space-3); } }
</style>
