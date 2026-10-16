<script lang="ts">
  type Props = {
    eyebrow: string;
    title: string;
    description: string;
    loading: boolean;
    onRefresh: () => void;
  };
  let { eyebrow, title, description, loading, onRefresh }: Props = $props();
</script>

<header class="heading">
  <div>
    <p class="eyebrow">{eyebrow}</p>
    <h1>{title}</h1>
    <p class="description">{description}</p>
  </div>
  <button class="ui-button ui-button-primary" type="button" onclick={onRefresh} disabled={loading}>
    다시 불러오기
  </button>
</header>

<style>
  .heading { display: flex; gap: var(--space-6); justify-content: space-between; align-items: start; }
  .eyebrow { color: var(--color-ink-muted); font-weight: 700; }
  .description { color: var(--color-ink-muted); }
  @media (max-width: 440px) { .heading { flex-direction: column; } }
</style>
