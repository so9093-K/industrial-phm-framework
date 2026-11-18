<script lang="ts">
  import {changeNumbers, type ChangeFacts} from "../change-story";
  /** 변화 전후의 두 숫자. 숫자마다 무엇의 값인지 위에, 얼마나 달라졌는지 아래에 적는다. */
  let {facts, fallback, compact=false}: {facts: ChangeFacts; fallback: string; compact?:boolean} = $props();
  const numbers = $derived(changeNumbers(facts));
</script>
{#if numbers}
  <dl class="change-values" class:compact>
    <div><dt title={numbers.before.caption}>{compact?"기준 기간":numbers.before.caption}</dt><dd>{numbers.before.value}</dd>{#if numbers.before.note && !compact}<dd class="note">{numbers.before.note}</dd>{/if}</div>
    <span class="arrow" aria-hidden="true">→</span>
    <div><dt title={numbers.after.caption}>{compact?"변화 구간":numbers.after.caption}</dt><dd>{numbers.after.value}</dd>{#if numbers.after.note}<dd class="note">{numbers.after.note}</dd>{/if}</div>
  </dl>
{:else}<p class="change-values plain">{fallback}</p>{/if}
<style>
  .change-values { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2) var(--space-5); margin: var(--space-2) 0; }
  .change-values > div { display: grid; gap: 2px; min-width: 0; }
  dt { font-size: var(--font-small); color: var(--color-ink-muted); }
  dd { margin: 0; font-size: clamp(1.4rem, 2.6vw, 1.85rem); font-weight: 700; line-height: 1.25; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
  dd.note { font-size: var(--font-small); font-weight: 400; color: var(--color-ink-muted); }
  .arrow { font-size: 1.5rem; color: var(--color-ink-muted); }
  .compact{gap:var(--space-1) var(--space-3)}.compact dd{font-size:1.3rem}.compact dd.note{font-size:var(--font-small)}
  .plain { font-size: 1.25rem; font-weight: 700; }
  @media (max-width: 560px) { .arrow { display: none; } }
</style>
