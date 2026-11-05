<script lang="ts">
  /** The message an analysis leads with, above its charts and tables: what changed, what it means,
   * how plain it is, and where to look next. */
  import type {AnalysisMessage} from "../analysis-messages";
  let {message, subject = null, basis = null, boundary = null}: {
    message: AnalysisMessage; subject?: string | null; basis?: string | null; boundary?: string | null;
  } = $props();
</script>

<section class="message" aria-label="이 분석에서 알 수 있는 것">
  {#if subject || basis}
    <dl class="scope">
      {#if subject}<div><dt>분석 대상</dt><dd>{subject}</dd></div>{/if}
      {#if basis}<div><dt>분석 기준</dt><dd>{basis}</dd></div>{/if}
    </dl>
  {/if}
  <p class="label">핵심 결과</p>
  <p class="headline">{message.headline}</p>
  {#if message.meaning}<p><strong>결과 해석</strong> · {message.meaning}</p>{/if}
  {#if message.certainty}<p class="certainty">{message.certainty}</p>{/if}
  {#if boundary}<details class="limits"><summary>계산 조건·해석 안내</summary><p>{boundary}</p></details>{/if}
  {#if message.next.length}
    <p class="next"><strong>다음 확인</strong>
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
  .label { font-size: var(--font-small); font-weight: 650; color: var(--color-ink-muted); }
  .scope { display: grid; gap: var(--space-2); margin: 0 0 var(--space-2); padding-bottom: var(--space-3); border-bottom: 1px solid var(--color-border); }
  .scope div { display: grid; grid-template-columns: 5rem minmax(0, 1fr); gap: var(--space-2); }
  dt { color: var(--color-ink-muted); font-size: var(--font-small); }
  dd { margin: 0; overflow-wrap: anywhere; }
  .certainty { color: var(--color-ink-muted); }
  .limits summary { cursor: pointer; color: var(--color-ink-muted); font-size: var(--font-small); }
  .next { display: flex; flex-wrap: wrap; gap: var(--space-1) var(--space-4); }
  a { color: var(--color-action); font-weight: 650; }
  @media (max-width: 480px) { .scope div { grid-template-columns: minmax(0, 1fr); gap: var(--space-1); } }
</style>
