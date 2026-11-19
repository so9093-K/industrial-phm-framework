<script lang="ts">
  import type {ModelRug} from "../model-context";
  /** 변화 그래프 바로 아래, 같은 가로축에 모델마다 기준을 넘은 측정을 한 줄씩 긋는다. 측정값이 바뀐 때와
   * 모델이 반응한 때, 모델끼리 반응이 다른지를 문장 없이 그래프에서 견줄 수 있게 한다. */
  let {rugs, lo, hi}: {rugs: ModelRug[]; lo: number; hi: number} = $props();
  const x = (at: number) => (at - lo) / Math.max(hi - lo, 1e-9) * 600;
  const inside = (list: number[]) => list.filter(at => at >= lo && at <= hi);
</script>

{#if rugs.length}
<div class="rugs" aria-label="모델별 기준 초과 위치">
  {#each rugs as rug (rug.label)}
    <div class="rug">
      <span class="label">{rug.label}</span>
      <svg viewBox="0 0 600 12" preserveAspectRatio="none" role="img" aria-label={rug.label}>
        <line x1="0" x2="600" y1="6" y2="6" class="base"/>
        {#each inside(rug.analyzed) as at, i (i)}<line x1={x(at)} x2={x(at)} y1="4" y2="8" class="seen"/>{/each}
        {#each inside(rug.exceeded) as at, i (i)}<line x1={x(at)} x2={x(at)} y1="0" y2="12" class="over"/>{/each}
      </svg>
    </div>
  {/each}
  <p class="key"><i class="over"></i>모델 기준 초과 <i class="seen"></i>기준 이하</p>
</div>
{/if}

<style>
  .rugs { display: grid; gap: var(--space-2); margin-top: var(--space-3); }
  .rug { display: grid; gap: 2px; }
  .label { font-size: var(--font-small); color: var(--color-ink); }
  svg { display: block; width: 100%; height: 12px; }
  .base { stroke: var(--color-border); stroke-width: 1; vector-effect: non-scaling-stroke; }
  .seen { stroke: var(--color-ink-muted); stroke-opacity: .45; stroke-width: 1; vector-effect: non-scaling-stroke; }
  .over { stroke: var(--color-failure-ink, #b42318); stroke-width: 2; vector-effect: non-scaling-stroke; }
  .key { margin: 0; font-size: var(--font-label); color: var(--color-ink-muted); display: flex; gap: var(--space-3); align-items: center; }
  .key i { display: inline-block; width: 2px; height: 10px; margin-right: 4px; vertical-align: middle; }
  .key i.over { background: var(--color-failure-ink, #b42318); }
  .key i.seen { background: var(--color-ink-muted); opacity: .45; }
</style>
