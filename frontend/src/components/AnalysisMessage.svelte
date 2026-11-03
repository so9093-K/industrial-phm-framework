<script lang="ts">
  /** The message an analysis leads with, above its charts and tables: what changed, what it means,
   * how plain it is, and where to look next. */
  import type {AnalysisMessage} from "../analysis-messages";
  let {message}: {message: AnalysisMessage} = $props();
</script>

<section class="message" aria-label="이 분석에서 알 수 있는 것">
  <p class="headline">{message.headline}</p>
  {#if message.meaning}<p>{message.meaning}</p>{/if}
  {#if message.certainty}<p><strong>얼마나 분명한가</strong> · {message.certainty}</p>{/if}
  {#if message.next.length}
    <p class="next"><strong>다음에 볼 것</strong>
      {#each message.next as step (step.href)}<a href={step.href}>{step.label} →</a>{/each}
    </p>
  {/if}
</section>

<style>
  .message {
    display: grid; gap: var(--space-2); margin-block: var(--space-4); padding: var(--space-4);
    border-left: 4px solid var(--color-action); border-radius: var(--radius-control);
    background: var(--color-surface-selected); min-width: 0;
  }
  p { margin: 0; line-height: 1.6; overflow-wrap: anywhere; }
  .headline { font-size: var(--font-section); font-weight: 650; }
  .next { display: flex; flex-wrap: wrap; gap: var(--space-1) var(--space-4); }
  a { color: var(--color-action); font-weight: 650; }
</style>
