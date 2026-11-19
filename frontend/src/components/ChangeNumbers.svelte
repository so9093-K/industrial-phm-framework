<script lang="ts">
  import {changeNumbers, type ChangeFacts, type ChangeNumber} from "../change-story";
  /** 변화 전후의 두 숫자와, 변화가 기록 끝까지 이어졌으면 마지막 값. 숫자마다 무엇의 값인지 위에,
   * 얼마나 달라졌는지 아래에 적는다. 표 안(compact)에서는 이름을 짧게 쓰고 숫자만 둔다. */
  let {facts, fallback, compact=false, latest=null, spanCaption=null}: {facts: ChangeFacts; fallback: string; compact?:boolean;
    latest?: ChangeNumber | null; spanCaption?: string | null} = $props();
  const numbers = $derived(changeNumbers(facts, spanCaption));
</script>
{#if numbers}
  <dl class="change-values" class:compact class:with-latest={!!latest}>
    <div><dt title={numbers.before.caption}>{compact?"기록 처음 30%":numbers.before.caption}</dt><dd>{numbers.before.value}</dd>{#if numbers.before.note && !compact}<dd class="note">{numbers.before.note}</dd>{/if}</div>
    <span class="arrow" aria-hidden="true">→</span>
    <div><dt title={numbers.after.caption}>{compact?"변화 구간":numbers.after.caption}</dt><dd>{numbers.after.value}</dd>{#if numbers.after.note && !compact}<dd class="note">{numbers.after.note}</dd>{/if}</div>
    {#if latest}<span class="arrow" aria-hidden="true">→</span>
      <div><dt>{latest.caption}</dt><dd class="latest">{latest.value}</dd>{#if latest.note && !compact}<dd class="note">{latest.note}</dd>{/if}</div>{/if}
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
