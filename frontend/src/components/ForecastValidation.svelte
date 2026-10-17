<script lang="ts">
  import type {Backtest} from "../forecast-settings";
  import {num} from "../format";
  let {checks=[]}:{checks?:Backtest[]}=$props();
</script>
<details><summary>과거 자료로 예측 확인</summary>
  {#if checks.length}<div class="scroll"><table><caption>첫 행은 최근 과거 검증, 다음 행은 여러 과거 시점입니다. 같은 구간의 마지막 값 유지와 비교합니다.</caption>
    <thead><tr><th>확인</th><th>가린 측정 개수</th><th>평균 절대 오차</th><th>마지막 값 유지 오차</th><th>예측 범위 내 실제값</th></tr></thead>
    <tbody>{#each checks as check,i(i)}<tr><th>{i===0?"최근 과거":"과거 시점 "+i}</th><td>{check.points}</td><td>{num(check.error)}</td><td>{num(check.naive)}</td><td>{num(check.coverage*100)}%</td></tr>{/each}</tbody>
  </table></div>{:else}<p>가려서 확인할 만큼 기록이 길지 않거나 검증 결과가 제공되지 않았습니다.</p>{/if}
  <p>과거 자료의 오차이며 앞으로의 정확도나 고장 확률이 아닙니다.</p>
</details>
<style>.scroll{max-width:100%;overflow-x:auto}table{width:100%;border-collapse:collapse}th,td{padding:var(--space-2);text-align:left;border-bottom:1px solid var(--color-border)}caption,p{color:var(--color-ink-muted);text-align:left}summary{cursor:pointer;color:var(--color-action);font-weight:650;padding-block:var(--space-3)}</style>
