<script lang="ts">
  /** One interpretation caution per screen, in the same place under the result. */
  let {message}: {message: string} = $props();
</script>

<p class="caution">
  <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line>
    <line x1="12" y1="16" x2="12.01" y2="16"></line>
  </svg>
  <span><strong>해석 주의</strong> · {message}</span>
</p>

<style>
  .caution {
    display: flex;
    gap: var(--space-3);
    align-items: flex-start;
    margin: var(--space-4) 0 0;
    padding: var(--space-3) var(--space-4);
    border-radius: var(--radius-control);
    background: var(--color-uncertain-surface);
    color: var(--color-caution-ink);
    font-size: var(--font-small);
    line-height: 1.6;
  }
  svg { flex: none; margin-top: 2px; color: var(--color-uncertain-border); }
</style>
