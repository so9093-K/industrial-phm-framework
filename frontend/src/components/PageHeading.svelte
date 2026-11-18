<script lang="ts">
  type Props = {
    title: string;
    description: string;
    meta?: string;
    loading?: boolean;
    onRefresh?: () => void;
    compact?:boolean; actionHref?:string; actionLabel?:string;
  };
  let { title, description, meta = "", loading = false, onRefresh, compact=false, actionHref, actionLabel }: Props = $props();
</script>

<header class="heading" class:compact>
  <div>
    <h1>{title}</h1>
    <p class="description">{description}</p>
    {#if meta && !compact}<p class="meta">{meta}</p>{/if}
  </div>
  <div class="heading-actions">
  {#if actionHref && actionLabel}<a class="ui-button" href={actionHref}>{actionLabel}</a>{/if}
  {#if onRefresh}
    <button class="ui-button" type="button" onclick={onRefresh} disabled={loading}>
      다시 불러오기
    </button>
  {/if}
    {#if compact && meta}<p class="meta">{meta}</p>{/if}
  </div>
</header>

<style>
  .heading { display: flex; gap: var(--space-6); justify-content: space-between; align-items: start; }
  .heading-actions{display:flex;flex-wrap:wrap;justify-content:end;gap:var(--space-2);align-items:center}.heading-actions a{text-decoration:none}.heading-actions .meta{flex-basis:100%;text-align:right}.compact{align-items:center;margin-bottom:var(--space-4)}.compact h1{font-size:1.8rem}.compact .description{margin:var(--space-1) 0 0}.compact .ui-button{padding:var(--space-2) var(--space-3)}
  .description { color: var(--color-ink-muted); margin:var(--space-2) 0; }
  .meta { color:var(--color-ink-muted); font-size:var(--font-small); margin:0; }
  @media (max-width: 440px) { .heading { flex-direction: column; } }
</style>
