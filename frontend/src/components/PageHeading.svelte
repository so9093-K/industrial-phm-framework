<script lang="ts">
  type Props = {
    title: string;
    description: string;
    meta?: string;
    loading?: boolean;
    onRefresh?: () => void;
  };
  let { title, description, meta = "", loading = false, onRefresh }: Props = $props();
</script>

<header class="heading">
  <div>
    <h1>{title}</h1>
    <p class="description">{description}</p>
    {#if meta}<p class="meta">{meta}</p>{/if}
  </div>
  {#if onRefresh}
    <button class="ui-button" type="button" onclick={onRefresh} disabled={loading}>
      다시 불러오기
    </button>
  {/if}
</header>

<style>
  .heading { display: flex; gap: var(--space-6); justify-content: space-between; align-items: start; }
  .description { color: var(--color-ink-muted); margin:var(--space-2) 0; }
  .meta { color:var(--color-ink-muted); font-size:var(--font-small); margin:0; }
  @media (max-width: 440px) { .heading { flex-direction: column; } }
</style>
