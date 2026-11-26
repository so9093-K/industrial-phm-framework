<script lang="ts">
  import {num} from "../format";
  import {reasonValueText, type ScoreReason} from "../score-reason";

  /** What raised one result over its threshold: one bar of shares, then a line per signal. */
  let {reason}: {reason: ScoreReason} = $props();
  const told = $derived(reason.rows.map((row) => row.name + " " + row.share + "%")
    .concat(reason.rest ? ["나머지 신호 " + reason.rest.signals + "개 " + reason.rest.share + "%"] : []).join(", "));
</script>

<section class="reason" aria-labelledby="score-reason-title">
  <h4 id="score-reason-title">점수를 올린 몫</h4>
  <div class="stack" role="img" aria-label={told}>
    {#each reason.rows as row, index (row.signal)}<span class={"part step-" + index} style:width={row.share + "%"}></span>{/each}
  </div>
  <ul>
    {#each reason.rows as row, index (row.signal)}
      <li><span class="head"><i class={"key step-" + index}></i><strong>{row.name}</strong><span class="share">{row.share}%</span></span>
        <span class="value">{reasonValueText(row, (value) => num(value, "기록 없음"))}</span></li>
    {/each}
    {#if reason.rest}
      <li class="rest"><span class="head"><i class="key"></i>나머지 신호 {reason.rest.signals}개<span class="share">{reason.rest.share}%</span></span></li>
    {/if}
  </ul>
</section>

<style>
  .reason { display: grid; gap: var(--space-2); }
  h4 { margin: 0; font-size: var(--font-small); color: var(--color-ink-muted); font-weight: 650; }
  /* 몫은 순위가 곧 크기라 한 색의 세 단계로 그리고, 나머지는 막대의 바탕으로 남긴다. */
  .stack { display: flex; gap: 2px; height: 10px; border-radius: 5px; overflow: hidden; background: var(--color-surface-selected); }
  .part { display: block; height: 100%; }
  .key { width: 10px; height: 10px; border-radius: 2px; flex: none; background: var(--color-surface-selected); border: 1px solid var(--color-border); }
  .key[class*="step-"] { border: 0; }
  .step-0 { background: var(--color-action); }
  .step-1 { background: color-mix(in srgb, var(--color-action) 68%, var(--color-surface)); }
  .step-2 { background: color-mix(in srgb, var(--color-action) 42%, var(--color-surface)); }
  ul { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-2); }
  li { display: grid; gap: 2px; }
  .head { display: flex; align-items: center; gap: var(--space-2); }
  .share { margin-left: auto; font-variant-numeric: tabular-nums; font-weight: 650; }
  .rest .head { color: var(--color-ink-muted); }
  .rest .share { font-weight: 400; }
  .value { padding-left: calc(10px + var(--space-2)); font-size: var(--font-small); color: var(--color-ink-muted); overflow-wrap: anywhere; }
</style>
