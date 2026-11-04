<script lang="ts">
  /** Before any data: the questions this product answers and what each needs, so a person knows
   * what to bring. Nothing here is a result; no chart or score is drawn without stored data. */
  import {GUIDE_ORDER, METHOD, NEEDS, QUESTION} from "../capabilities";
</script>

<section class="guide" aria-labelledby="guide-title">
  <h3 id="guide-title">데이터를 연결하면 알아볼 수 있는 것</h3>
  <ul>
    {#each GUIDE_ORDER as id (id)}
      <li><strong>{QUESTION[id]}</strong><span>{METHOD[id]}</span><span class="needs">필요한 데이터 · {NEEDS[id]}</span></li>
    {/each}
  </ul>
  <p class="context">결과는 계산한 값과 근거로 보여 주고, 고장 원인을 판정하지 않습니다. 결과와 전망은 근거와 함께 검토 기록으로 남겨
    담당자가 확인·종료할 수 있습니다.</p>
</section>

<style>
  .guide { display: grid; gap: var(--space-3); min-width: 0; }
  h3 { margin: 0; font-size: var(--font-body); }
  ul { list-style: none; margin: 0; padding: 0; display: grid; }
  li { display: grid; grid-template-columns: minmax(12rem, 22rem) minmax(6rem, 12rem) minmax(0, 1fr); gap: var(--space-1) var(--space-3);
    padding: var(--space-3) 0; border-bottom: 1px solid var(--color-border); min-width: 0; overflow-wrap: anywhere; }
  li span { color: var(--color-ink-muted); font-size: var(--font-small); }
  .context { margin: 0; color: var(--color-ink-muted); font-size: var(--font-small); overflow-wrap: anywhere; }
  @media (max-width: 720px) { li { grid-template-columns: minmax(0, 1fr); } }
</style>
