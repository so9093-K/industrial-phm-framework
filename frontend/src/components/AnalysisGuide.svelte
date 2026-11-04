<script lang="ts">
  /** Before any data: the available analyses and what each needs, so a person knows
   * what to bring. Nothing here is a result; no chart or score is drawn without stored data. */
  import {GUIDE_ORDER, METHOD, NEEDS} from "../capabilities";
</script>

<section class="guide" aria-labelledby="guide-title">
  <h3 id="guide-title">분석 기능 및 입력 데이터</h3>
  <ul>
    {#each GUIDE_ORDER as id (id)}
      <li><strong>{METHOD[id]}</strong><span class="needs">필요한 데이터 · {NEEDS[id]}</span></li>
    {/each}
  </ul>
  <p class="context">데이터를 연결하면 신호 추이·구간 변화·이상 점수를 분석할 수 있습니다. 결과에서 비교할 기간과 측정을 선택해 상세 신호를 확인합니다.</p>
</section>

<style>
  .guide { display: grid; gap: var(--space-3); min-width: 0; }
  h3 { margin: 0; font-size: var(--font-body); }
  ul { list-style: none; margin: 0; padding: 0; display: grid; }
  li { display: grid; grid-template-columns: minmax(10rem, 16rem) minmax(0, 1fr); gap: var(--space-1) var(--space-3);
    padding: var(--space-3) 0; border-bottom: 1px solid var(--color-border); min-width: 0; overflow-wrap: anywhere; }
  li span { color: var(--color-ink-muted); font-size: var(--font-small); }
  .context { margin: 0; color: var(--color-ink-muted); font-size: var(--font-small); overflow-wrap: anywhere; }
  @media (max-width: 720px) { li { grid-template-columns: minmax(0, 1fr); } }
</style>
