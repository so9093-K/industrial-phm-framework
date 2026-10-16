<script lang="ts">
  export type NoticeKind = "information" | "uncertain" | "failure";
  type Props = {
    message: string;
    title?: string;
    kind?: NoticeKind;
    actionLabel?: string;
    actionHref?: string;
    onAction?: () => void;
  };
  let {
    message, title = "", kind = "information", actionLabel, actionHref, onAction,
  }: Props = $props();
</script>

<section
  class="notice ui-panel"
  class:uncertain={kind === "uncertain"}
  class:failure={kind === "failure"}
  role={kind === "failure" ? "alert" : "status"}
  aria-atomic="true"
>
  {#if title}<h2>{title}</h2>{/if}
  <p>{message}</p>
  {#if actionLabel && actionHref}
    <a class="ui-link-primary" href={actionHref}>{actionLabel}</a>
  {:else if actionLabel && onAction}
    <button class="ui-button ui-button-primary" type="button" onclick={onAction}>{actionLabel}</button>
  {/if}
</section>

<style>
  .notice { margin-block: var(--space-4); }
  .notice p { margin-bottom: 0; }
  .notice a, .notice button { margin-top: var(--space-4); }
  .uncertain {
    border-inline-start: 4px solid var(--color-uncertain-border);
    background: var(--color-uncertain-surface);
  }
  .failure {
    border-inline-start: 4px solid var(--color-failure-border);
    background: var(--color-failure-surface);
    color: var(--color-failure-ink);
  }
</style>
